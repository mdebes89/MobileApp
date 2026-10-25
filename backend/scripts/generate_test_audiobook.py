"""End-to-end pipeline test with a hardcoded topic.

Run:  MISTRAL_API_KEY=... python scripts/generate_test_audiobook.py --topic coffee

Requires Postgres + Redis (docker-compose up) and S3 config (or MinIO).
"""
import argparse
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Audiobook, AudiobookStatus, Job, Voice  # noqa: E402
from app.normalize import cache_key, normalize_topic  # noqa: E402
from app.session import get_engine, session_scope  # noqa: E402
from app.worker_tasks import run_generation_job  # noqa: E402


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="coffee")
    parser.add_argument("--length", type=int, default=10)
    parser.add_argument("--voice", default="male")
    parser.add_argument("--language", default="en")
    parser.add_argument("--poll", action="store_true", help="only poll status, don't run the job")
    parser.add_argument("--id", default=None, help="audiobook id to poll")
    args = parser.parse_args()

    get_engine()
    if args.poll and args.id:
        with session_scope() as session:
            ab = session.get(Audiobook, uuid.UUID(args.id))
            print(f"status={ab.status} title={ab.title!r} chapters={len(ab.chapters)}")
            for ch in ab.chapters:
                print(f"  ch{ch.position:02d} [{ch.arc_section}] {ch.title} key={ch.audio_object_key} dur={ch.duration_seconds}s")
            job = session.query(Job).filter_by(audiobook_id=ab.id).first()
            print(f"job: status={job.status} step={job.step}")
        return

    normalized = normalize_topic(args.topic)
    key = cache_key(normalized, args.length, args.voice, args.language)
    with session_scope() as session:
        ab = Audiobook(
            cache_key=key,
            topic=args.topic,
            normalized_topic=normalized,
            length_minutes=args.length,
            voice=Voice(args.voice),
            language=args.language,
            status=AudiobookStatus.QUEUED,
        )
        session.add(ab)
        session.flush()
        session.add(Job(audiobook_id=ab.id))
        session.commit()
        ab_id = str(ab.id)

    print(f"audiobook {ab_id} queued; running pipeline...")
    result = run_generation_job(ab_id)
    print(f"result: {result}")

    with session_scope() as session:
        ab = session.get(Audiobook, uuid.UUID(ab_id))
        print(f"final status={ab.status} title={ab.title!r}")
        for ch in ab.chapters:
            print(f"  ch{ch.position:02d} [{ch.arc_section}] {ch.title} key={ch.audio_object_key} dur={ch.duration_seconds}s")
        if ab.status == AudiobookStatus.READY:
            print("SUCCESS")
        else:
            print("FAILED")
            sys.exit(1)


if __name__ == "__main__":
    main()
