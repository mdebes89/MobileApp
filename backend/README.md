# History Audiobooks — Backend

FastAPI backend (Python 3.12) for a commercial Android app that generates streamable,
AI-narrated history audiobooks from a topic + filters, with a dedup catalog cache.

## Architecture

```
POST /audiobooks ──► cache-key lookup ──HIT──► 200 + record (never regenerate)
                          │
                          MISS (entitlement required)
                          ▼
                 queued record ─► RQ (Redis) ─► generation worker
                                                  research → outline → write
                                                  → validate → TTS → finalize
PostgreSQL (users, entitlements, audiobooks, chapters, jobs, devices, progress)
S3/R2      (chapter MP3s + full script markdown, presigned GET URLs)
FCM        (push notification to the requesting user when ready)
```

- **Cache key**: `normalize_topic(topic) + length + voice + language`. Any request matching
  a `ready` audiobook returns it immediately; `queued`/`generating` records are also reused
  (no duplicate jobs for the same key).
- **Entitlement**: Google ID token (Bearer) is verified; a NEW generation requires an active
  subscription entitlement. Streaming the existing catalog is free.
- **Pipeline** (`app/worker_tasks.py` + `app/pipeline.py`), resumable per step:
  1. **research** — web-search-grounded facts + topic-reject gate
  2. **outline** — mandatory arc: world_before → origin → evolution → challenges → perspective
     (3-4 / 7-8 / 12-16 chapters for 10/30/60 min; word budget split at 150 wpm)
  3. **write** — narration-ready spoken prose, natural transitions
  4. **validate** — separate pass: relevance incl. indirect dependencies, strict arc order,
     no placeholders/missing paragraphs, no defamation; failing chapters regenerate
  5. **tts** — Voxtral TTS (`voxtral-mini-tts-3-0`), chunked <5000 chars on paragraph
     boundaries, WAV concat, resample 44.1 kHz 16-bit mono, MP3 encode, header verified
  6. **finalize** — script markdown uploaded, status `ready`, FCM push
- **Mistral clients** follow the official API schemas:
  chat `POST /v1/chat/completions` (`messages`, `response_format`) and
  TTS `POST /v1/audio/speech` (`model`, `input`, `voice_id`, `response_format` → base64 `audio_data`).
- **Rate limiting**: Redis fixed-window limiter around every Mistral call (`MISTRAL_RPM_LIMIT`).
- **File naming**: `<topic>-chapter-NN-<title-kebab>.mp3` (two-digit sequence).

## Local run (docker-compose: Postgres + Redis + MinIO + API + worker)

```bash
cp .env.example .env         # fill in at least MISTRAL_API_KEY
docker compose up --build    # runs migrations, API on :8000, worker, MinIO on :9000
```

Without Docker (dev):

```bash
pip install -r requirements.txt  # or: pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload           # API
python -m app.worker                    # generation worker
```

## Tests

```bash
python -m pytest tests/ -q              # 55 tests incl. cache-key normalization + entitlement checks
DATABASE_URL=sqlite:////tmp/smoke.db python scripts/smoke_pipeline_local.py   # e2e pipeline smoke (mocked Mistral)
MISTRAL_API_KEY=... python scripts/generate_test_audiobook.py --topic coffee  # real API e2e
```

## API summary

| Endpoint | Description |
| --- | --- |
| `POST /audiobooks` | Create/request: cache hit → 200 with signed chapter URLs; miss → 202-style queued record. Headers: `Authorization: Bearer <google-id-token>`, optional `X-Device-Token` (FCM). Body: `{topic, length_minutes, voice, language}` |
| `GET /audiobooks/{id}` | Status polling (`queued\|generating\|ready\|failed`) + chapter list with presigned URLs when ready |
| `GET /audiobooks?topic=` | Shared catalog with topic search (free, no auth) |
| `GET /me/entitlement` | Active subscription check |
| `POST /me/device` | Register FCM token |
| `POST/GET /me/progress?audiobook_id=` | Playback position resume |

## Seeding a pre-existing catalog

```bash
# by filename convention: <topic>-chapter-NN-<title>.mp3
python scripts/seed_catalog.py --dir ./seed_catalog

# or with full metadata control
python scripts/seed_catalog.py --dir ./seed_catalog --manifest seed_manifest.json
```

## Deploy (Render/Fly.io)

- Service 1 (API): `uvicorn app.main:app --host 0.0.0.0 --port $PORT`; run `alembic upgrade head` on release.
- Service 2 (worker): `python -m app.worker` (worker process).
- Managed Postgres + Redis; S3/R2 bucket with access keys set via environment.
- Secrets (`MISTRAL_API_KEY`, DB creds, S3 keys, FCM JSON, `GOOGLE_CLIENT_IDS`) come from
  environment variables only — never committed. See `.env.example`.

## Notes

- Audio chunking, WAV concat/resample and MP3 encode are pure-Python (`wave`/`audioop`/`lameenc`),
  so the image needs no ffmpeg.
- `audioop` is deprecated in 3.12 (removal in 3.13); swap to `audioop-lts` when upgrading Python.
