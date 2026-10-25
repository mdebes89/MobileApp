"""Resumable generation job tasks. Each pipeline step persists progress so a
crashed/restarted job can resume from the last completed step."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from redis import Redis
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mistral_client, notifications, pipeline, storage
from app.config import get_settings
from app.db import Audiobook, AudiobookStatus, Chapter, Job, JobStatus, UserDevice
from app.pipeline import Outline, OutlineChapter
from app.session import get_engine, session_scope

log = logging.getLogger(__name__)

MAX_CHAPTER_ATTEMPTS = 2


def get_generation_queue() -> Queue:
    settings = get_settings()
    return Queue("generation", connection=Redis.from_url(settings.redis_url))


def enqueue_generation(audiobook_id: str, user_id: str | None) -> None:
    queue = get_generation_queue()
    queue.enqueue(
        "app.worker_tasks.run_generation_job",
        audiobook_id,
        user_id,
        job_timeout=7200,
        failure_ttl=86400,
        result_ttl=86400,
    )


def _utcnow():
    return datetime.now(timezone.utc)


def _set_step(session: Session, job: Job, step: str) -> None:
    job.step = step
    job.updated_at = _utcnow()
    session.commit()


def _outline_from_meta(outline_data: dict) -> Outline:
    outline = Outline(title=outline_data["title"])
    outline.chapters = [
        OutlineChapter(
            position=c["position"],
            arc_section=c["arc_section"],
            title=c["title"],
            summary=c.get("summary", ""),
            target_words=c.get("target_words", 0),
        )
        for c in outline_data["chapters"]
    ]
    return outline


def run_generation_job(audiobook_id: str, user_id: str | None = None) -> dict[str, Any]:
    """Main entrypoint called by the RQ worker."""
    engine = get_engine()
    with session_scope(engine) as session:
        ab = session.get(Audiobook, uuid.UUID(audiobook_id))
        if ab is None:
            raise RuntimeError(f"audiobook {audiobook_id} not found")
        job = session.scalar(select(Job).where(Job.audiobook_id == ab.id).order_by(Job.created_at.desc()))
        if job is None:
            job = Job(audiobook_id=ab.id)
            session.add(job)
            session.flush()
        if job.status == JobStatus.DONE:
            return {"status": "already_done"}

        job.status = JobStatus.RUNNING
        job.attempts += 1
        ab.status = AudiobookStatus.GENERATING
        session.commit()
        try:
            result = asyncio.run(_run_pipeline(session, ab, job))
            job.status = JobStatus.DONE
            job.step = "done"
            ab.status = AudiobookStatus.READY
            session.commit()
            _notify_ready(session, ab, user_id)
            return result
        except Exception:
            session.rollback()
            log.exception("generation failed for audiobook %s", audiobook_id)
            job = session.scalar(
                select(Job).where(Job.audiobook_id == uuid.UUID(audiobook_id)).order_by(Job.created_at.desc())
            )
            ab = session.get(Audiobook, uuid.UUID(audiobook_id))
            if job is not None:
                job.status = JobStatus.FAILED
                job.last_error = "generation failed"
            ab.status = AudiobookStatus.FAILED
            session.commit()
            raise


async def _run_pipeline(session: Session, ab: Audiobook, job: Job) -> dict[str, Any]:
    meta: dict[str, Any] = dict(ab.generation_meta or {})

    # Step a: RESEARCH (resumable - cached in generation_meta)
    _set_step(session, job, "research")
    research = meta.get("research")
    if not research:
        research = await pipeline.research_topic(ab.topic, ab.language)
        meta["research"] = research
        _save_meta(session, ab, meta)

    # Step b: OUTLINE (resumable)
    _set_step(session, job, "outline")
    outline_data = meta.get("outline")
    if not outline_data:
        outline = await pipeline.build_outline(ab.topic, research, ab.length_minutes, ab.language)
        outline_data = {
            "title": outline.title,
            "chapters": [
                {
                    "position": c.position,
                    "arc_section": c.arc_section,
                    "title": c.title,
                    "summary": c.summary,
                    "target_words": c.target_words,
                }
                for c in outline.chapters
            ],
        }
        meta["outline"] = outline_data
        _save_meta(session, ab, meta)
    ab.title = outline_data["title"]
    outline = _outline_from_meta(outline_data)

    # Steps c+e: WRITE + VALIDATE + TTS per chapter (each chapter persisted on completion)
    existing = {c.position: c for c in session.query(Chapter).where(Chapter.audiobook_id == ab.id).all()}
    prev_title = None
    for spec in outline.chapters:
        done = existing.get(spec.position)
        if done is not None:
            prev_title = done.title
            continue

        _set_step(session, job, f"write:{spec.position}")
        text = await pipeline.write_chapter(ab.topic, outline, spec, prev_title, ab.language)

        _set_step(session, job, f"validate:{spec.position}")
        verdict = await pipeline.validate_chapter(ab.topic, outline, spec, text, ab.language)
        if not verdict["valid"] or pipeline.has_placeholder_text(text):
            log.warning("chapter %d failed validation: %s", spec.position, verdict["issues"])
            for attempt in range(MAX_CHAPTER_ATTEMPTS - 1):
                text = await pipeline.write_chapter(ab.topic, outline, spec, prev_title, ab.language)
                verdict = await pipeline.validate_chapter(ab.topic, outline, spec, text, ab.language)
                if verdict["valid"] and not pipeline.has_placeholder_text(text):
                    break
            else:
                raise ValueError(f"chapter {spec.position} failed validation repeatedly: {verdict['issues']}")

        _set_step(session, job, f"tts:{spec.position}")
        mp3, duration = await pipeline.synthesize_chapter_audio(text, ab.voice.value, ab.language)
        object_key = pipeline.chapter_object_key(ab.normalized_topic, spec.position, spec.title)
        storage.upload_bytes(object_key, mp3, "audio/mpeg")

        session.add(
            Chapter(
                audiobook_id=ab.id,
                position=spec.position,
                title=spec.title,
                arc_section=spec.arc_section,
                text=text,
                audio_object_key=object_key,
                duration_seconds=duration,
            )
        )
        session.commit()
        prev_title = spec.title

    # Step f: FINALIZE - full script markdown
    _set_step(session, job, "finalize")
    session.refresh(ab)
    script = _build_script_markdown(ab)
    script_key = f"{ab.normalized_topic.replace(' ', '-')}-script.md"
    storage.upload_bytes(script_key, script.encode("utf-8"), "text/markdown")
    ab.script_markdown = script
    ab.script_object_key = script_key
    return {"chapters": len(outline.chapters)}


def _save_meta(session: Session, ab: Audiobook, meta: dict) -> None:
    ab.generation_meta = meta
    session.commit()


def _build_script_markdown(ab: Audiobook) -> str:
    lines = [
        f"# {ab.title or ab.topic.title()}",
        "",
        f"*Topic: {ab.topic} — {ab.length_minutes} minutes, {ab.voice.value} voice, {ab.language}*",
        "",
    ]
    for ch in ab.chapters:
        lines.append(f"## Chapter {ch.position + 1}: {ch.title}")
        lines.append("")
        lines.append(ch.text)
        lines.append("")
    return "\n".join(lines)


def _notify_ready(session: Session, ab: Audiobook, user_id: str | None) -> None:
    if not user_id:
        return
    try:
        uid = uuid.UUID(user_id)
        devices = session.scalars(select(UserDevice).where(UserDevice.user_id == uid)).all()
        for dev in devices:
            notifications.push_audiobook_ready(dev.fcm_token, str(ab.id), ab.title or ab.topic)
    except Exception:
        log.exception("notification step failed for audiobook %s", ab.id)
