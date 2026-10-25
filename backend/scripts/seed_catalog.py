"""Seed script: ingest a pre-existing catalog of audiobook files from a folder.

Expected folder layout (CATALOG_SEED_DIR):
  <topic>-chapter-01-<title>.mp3        (audio chapters, two-digit sequence)
  <topic>-script.md                      (optional full script)

Each filename must also encode metadata; use --manifest for full control:
  seed_manifest.json: [
    {"topic": "coffee", "length_minutes": 10, "voice": "male", "language": "en",
     "title": "Coffee: A World History", "chapters": [
        {"file": "coffee-chapter-01-the-world-before-coffee.mp3",
         "title": "The World Before Coffee", "arc_section": "world_before",
         "duration_seconds": 120}
     ]}
  ]
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import storage  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Audiobook, AudiobookStatus, Chapter, Voice  # noqa: E402
from app.normalize import cache_key, normalize_topic  # noqa: E402
from app.session import session_scope, get_engine  # noqa: E402

log = logging.getLogger(__name__)

CHAPTER_RE = re.compile(r"^(?P<topic>.+?)-chapter-(?P<pos>\d{2})-(?P<title>.+)\.(mp3|wav)$")

ARC_BY_HINT = [
    (re.compile(r"before|world-before", re.I), "world_before"),
    (re.compile(r"origin|birth", re.I), "origin"),
    (re.compile(r"evolution|era|spread|age", re.I), "evolution"),
    (re.compile(r"challenge|modern|today", re.I), "challenges"),
    (re.compile(r"future|perspective|tomorrow", re.I), "perspective"),
]


def guess_arc(title: str) -> str:
    for pattern, arc in ARC_BY_HINT:
        if pattern.search(title):
            return arc
    return "evolution"


def seed_from_manifest(session, manifest_path: Path, seed_dir: Path) -> int:
    manifest = json.loads(manifest_path.read_text())
    count = 0
    for entry in manifest:
        normalized = normalize_topic(entry["topic"])
        key = cache_key(normalized, entry["length_minutes"], entry["voice"], entry["language"])
        existing = session.query(Audiobook).filter_by(cache_key=key, status=AudiobookStatus.READY).first()
        if existing:
            log.info("skip existing: %s", key)
            continue
        ab = Audiobook(
            cache_key=key,
            topic=entry["topic"],
            normalized_topic=normalized,
            title=entry.get("title") or entry["topic"].title(),
            length_minutes=entry["length_minutes"],
            voice=Voice(entry["voice"]),
            language=entry.get("language", "en"),
            status=AudiobookStatus.READY,
        )
        session.add(ab)
        session.flush()
        for ch in entry.get("chapters", []):
            file_path = seed_dir / ch["file"]
            if not file_path.exists():
                log.warning("missing file: %s", file_path)
                continue
            object_key = f"{normalized.replace(' ', '-')}-chapter-{ch['position']:02d}-{ch['title'].lower().replace(' ', '-')}.mp3"
            storage.upload_bytes(object_key, file_path.read_bytes(), "audio/mpeg")
            session.add(
                Chapter(
                    audiobook_id=ab.id,
                    position=ch["position"],
                    title=ch["title"],
                    arc_section=ch.get("arc_section", guess_arc(ch["title"])),
                    text=ch.get("text", ""),
                    audio_object_key=object_key,
                    duration_seconds=ch.get("duration_seconds"),
                )
            )
        count += 1
    session.commit()
    return count


def seed_from_filenames(session, seed_dir: Path, defaults: dict) -> int:
    """Fallback: derive catalog entries from <topic>-chapter-NN-title.mp3 filenames."""
    groups: dict[str, list[tuple[int, str, Path]]] = {}
    for f in sorted(seed_dir.glob("*-chapter-*.mp3")):
        m = CHAPTER_RE.match(f.name)
        if not m:
            log.warning("unrecognized file pattern: %s", f.name)
            continue
        topic = m.group("topic").replace("-", " ")
        groups.setdefault(topic, []).append((int(m.group("pos")), m.group("title").replace("-", " "), f))

    count = 0
    for topic, chapters in groups.items():
        normalized = normalize_topic(topic)
        if not normalized:
            continue
        key = cache_key(normalized, defaults["length_minutes"], defaults["voice"], defaults["language"])
        if session.query(Audiobook).filter_by(cache_key=key, status=AudiobookStatus.READY).first():
            log.info("skip existing: %s", key)
            continue
        ab = Audiobook(
            cache_key=key,
            topic=topic,
            normalized_topic=normalized,
            title=topic.title(),
            length_minutes=defaults["length_minutes"],
            voice=Voice(defaults["voice"]),
            language=defaults["language"],
            status=AudiobookStatus.READY,
        )
        session.add(ab)
        session.flush()
        for pos, title, path in chapters:
            object_key = f"{normalized.replace(' ', '-')}-chapter-{pos:02d}-{title.lower().replace(' ', '-')}.mp3"
            storage.upload_bytes(object_key, path.read_bytes(), "audio/mpeg")
            session.add(
                Chapter(
                    audiobook_id=ab.id,
                    position=pos - 1,
                    title=title.title(),
                    arc_section=guess_arc(title),
                    text="",
                    audio_object_key=object_key,
                )
            )
        count += 1
    session.commit()
    return count


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=get_settings().catalog_seed_dir, help="catalog folder")
    parser.add_argument("--manifest", default=None, help="seed_manifest.json for full metadata")
    parser.add_argument("--length", type=int, default=10)
    parser.add_argument("--voice", default="male")
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    seed_dir = Path(args.dir)
    if not seed_dir.is_dir():
        log.error("seed dir not found: %s", seed_dir)
        sys.exit(1)

    get_engine()
    with session_scope() as session:
        if args.manifest:
            n = seed_from_manifest(session, Path(args.manifest), seed_dir)
        else:
            n = seed_from_filenames(
                session, seed_dir, {"length_minutes": args.length, "voice": args.voice, "language": args.language}
            )
    log.info("seeded %d audiobooks", n)


if __name__ == "__main__":
    main()
