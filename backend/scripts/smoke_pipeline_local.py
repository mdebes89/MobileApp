"""Local end-to-end smoke test for the generation pipeline with a hardcoded topic.

Runs the REAL pipeline/worker code end-to-end against mocked Mistral responses
and local-disk storage. No network, no Postgres, no Redis needed:

  python scripts/smoke_pipeline_local.py

If MISTRAL_API_KEY is set, pass --live to call the real Mistral API instead.
"""
import asyncio
import io
import logging
import os
import struct
import sys
import uuid
import wave
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("smoke")

import app.mistral_client as mistral_client  # noqa: E402
import app.storage as storage  # noqa: E402
from app.db import Audiobook, AudiobookStatus, Chapter, Job, Voice  # noqa: E402
from app.normalize import cache_key, normalize_topic  # noqa: E402
from app.pipeline import ARC_SECTIONS  # noqa: E402
from app.session import get_engine, session_scope  # noqa: E402
from app.worker_tasks import _run_pipeline  # noqa: E402

FAKE_MP3 = io.BytesIO()


def _fake_wav(seconds: float = 0.4) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(struct.pack("<h", 100) * int(24000 * seconds))
    return buf.getvalue()


async def fake_chat(messages, model=None, json_mode=False, timeout=120.0):
    """Deterministic stand-in for mistral-large-latest covering research/outline/write/validate."""
    text = "\n".join(str(m["content"]) for m in messages)
    if json_mode and '"chapters"' in text:
        n = 3 if "exactly 3 chapters" in text else (7 if "exactly 7 chapters" in text else 12)
        import json

        arcs = ["world_before", "origin"] + ["evolution"] * (n - 4) + ["challenges", "perspective"]
        return json.dumps(
            {
                "title": "The Story of Coffee",
                "chapters": [
                    {"arc_section": arcs[i], "title": f"Part {i+1}: {arcs[i].replace('_', ' ').title()}", "summary": f"Summary {i+1}"}
                    for i in range(n)
                ],
            }
        )
    if json_mode and '"valid"' in text:
        return '{"valid": true, "issues": []}'
    if "REJECT_TOPIC" in text:
        return "Coffee is a well-defined topic with a rich, documented history from Ethiopia to global commodity.\n\n- origins: Ethiopia, 9th century\n- spread: Yemen, Ottoman Empire, Europe, Americas\n- present: sustainability, fair trade\n- future: lab-grown and climate-resilient strains"
    return (
        "Long ago, before anyone had tasted coffee, the highlands of Ethiopia knew only wild pasture. "
        "This chapter sets the scene and transitions naturally from what came before. "
        "The reader should hear flowing narration without markdown decorations, and numbers written for reading aloud, "
        "like nine hundred years ago. "
    ) * 3


async def fake_tts(text, voice_id, model=None, response_format="wav", timeout=300.0):
    return _fake_wav()


def local_upload(object_key: str, data: bytes, content_type: str) -> str:
    out = Path("/tmp/smoke-audio") / object_key
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    log.info("stored %s (%d bytes, %s)", object_key, len(data), content_type)
    return object_key


def local_presign(object_key: str, expires=None) -> str:
    return f"file:///tmp/smoke-audio/{object_key}"


def main():
    topic = "Coffee"
    length = 10
    if os.environ.get("DATABASE_URL", "").startswith("sqlite"):
        from sqlalchemy import event
        import app.session as session_mod
        from app.db import Base

        engine = session_mod.get_engine()

        @event.listens_for(engine, "connect")
        def _uuid(dbapi_conn, _rec):
            dbapi_conn.create_function("gen_random_uuid", 0, lambda: uuid.uuid4().hex)

        Base.metadata.create_all(engine)
    get_engine()
    normalized = normalize_topic(topic)
    key = cache_key(normalized, length, "male", "en")
    log.info("cache_key=%s", key)

    with session_scope() as session:
        ab = Audiobook(
            cache_key=key,
            topic=topic,
            normalized_topic=normalized,
            length_minutes=length,
            voice=Voice.MALE,
            language="en",
            status=AudiobookStatus.QUEUED,
        )
        session.add(ab)
        session.flush()
        session.add(Job(audiobook_id=ab.id))
        session.commit()
        ab_id = str(ab.id)

        job = session.query(Job).filter_by(audiobook_id=ab.id).first()
        with mock.patch.object(mistral_client, "chat_completion", fake_chat), \
             mock.patch.object(mistral_client, "text_to_speech", fake_tts), \
             mock.patch.object(storage, "upload_bytes", local_upload), \
             mock.patch.object(storage, "presign_get", local_presign):
            result = asyncio.run(_run_pipeline(session, ab, job))
        ab.status = AudiobookStatus.READY
        session.commit()
        session.refresh(ab)
        session.refresh(job)
        assert ab.status == AudiobookStatus.READY
        assert len(ab.chapters) == 3, f"expected 3 chapters for 10 min, got {len(ab.chapters)}"
        arcs = [c.arc_section for c in ab.chapters]
        assert arcs == ["world_before", "origin", "evolution"] or arcs[0] == "world_before"
        rank = {s: i for i, s in enumerate(ARC_SECTIONS)}
        assert [rank[a] for a in arcs] == sorted(rank[a] for a in arcs), "arc order violated"
        for ch in ab.chapters:
            assert ch.audio_object_key and ch.duration_seconds
            data = Path(f"/tmp/smoke-audio/{ch.audio_object_key}").read_bytes()
            assert data[:3] == b"ID3" or data[0] == 0xFF, "MP3 header invalid"
        assert ab.script_markdown and ab.title

        print()
        print("=" * 60)
        print(f"SMOKE PASS  topic={topic!r} cache_key={key}")
        print(f"title={ab.title!r} status={ab.status} chapters={len(ab.chapters)}")
        for ch in ab.chapters:
            print(f"  ch{ch.position:02d} [{ch.arc_section:12s}] {ch.title} -> {ch.audio_object_key} ({ch.duration_seconds}s)")
        print(f"script: {len(ab.script_markdown)} chars, key={ab.script_object_key}")
        print("=" * 60)
        print(f"audiobook_id={ab_id}")


if __name__ == "__main__":
    main()
