import logging
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, storage, worker_tasks
from app.db import Audiobook, AudiobookStatus, Job, PlaybackProgress, UserDevice
from app.normalize import cache_key, normalize_topic
from app.schemas import (
    AudiobookCreatedOut,
    AudiobookOut,
    CatalogEntry,
    CatalogResponse,
    ChapterOut,
    CreateAudiobookRequest,
    DeviceTokenRequest,
    EntitlementOut,
    ProgressRequest,
)
from app.session import get_session_factory

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="History Audiobooks", version="0.1.0")

VALID_LENGTHS = {10, 30, 60}
VALID_VOICES = {"male", "female"}


def db_session():
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def current_user(session: Session, authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        claims = auth.verify_google_id_token(token)
    except auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return auth.get_or_create_user(session, claims)


def _chapter_out(ch, presign: bool) -> ChapterOut:
    url = storage.presign_get(ch.audio_object_key) if (presign and ch.audio_object_key) else None
    return ChapterOut(
        position=ch.position,
        title=ch.title,
        arc_section=ch.arc_section,
        duration_seconds=ch.duration_seconds,
        audio_url=url,
    )


def _audiobook_out(ab: Audiobook, presign: bool) -> AudiobookOut:
    chapters = [_chapter_out(c, presign) for c in ab.chapters]
    return AudiobookOut(
        id=str(ab.id),
        title=ab.title or ab.topic.title(),
        topic=ab.topic,
        normalized_topic=ab.normalized_topic,
        length_minutes=ab.length_minutes,
        voice=ab.voice.value,
        language=ab.language,
        status=ab.status.value,
        error_message=ab.error_message,
        chapters=chapters,
    )


@app.post("/audiobooks", status_code=200, response_model=AudiobookCreatedOut)
def create_audiobook(
    body: CreateAudiobookRequest,
    session: Session = Depends(db_session),
    authorization: str = Header(default=""),
    x_device_token: str = Header(default=""),
):
    if body.length_minutes not in VALID_LENGTHS:
        raise HTTPException(status_code=422, detail="length_minutes must be 10, 30, or 60")
    if body.voice not in VALID_VOICES:
        raise HTTPException(status_code=422, detail='voice must be "male" or "female"')

    user = current_user(session, authorization)
    session.commit()

    # Entitlement gate: generating a NEW audiobook requires an active subscription.
    # Serving an existing catalog item (cache hit) is free.
    normalized = normalize_topic(body.topic)
    if not normalized:
        raise HTTPException(status_code=422, detail="topic must contain meaningful words")
    key = cache_key(normalized, body.length_minutes, body.voice, body.language)

    existing = session.scalar(
        select(Audiobook)
        .where(Audiobook.cache_key == key, Audiobook.status == AudiobookStatus.READY)
        .order_by(Audiobook.created_at.desc())
    )
    if existing is not None:
        out = _audiobook_out(existing, presign=True)
        return AudiobookCreatedOut(**out.model_dump(), cached=True)

    try:
        auth.require_entitlement(session, user)
    except auth.EntitlementError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    # A generation may already be in flight for this cache key.
    in_flight = session.scalar(
        select(Audiobook)
        .where(
            Audiobook.cache_key == key,
            Audiobook.status.in_([AudiobookStatus.QUEUED, AudiobookStatus.GENERATING]),
        )
        .order_by(Audiobook.created_at.desc())
    )
    if in_flight is not None:
        out = _audiobook_out(in_flight, presign=False)
        return AudiobookCreatedOut(**out.model_dump(), cached=False)

    ab = Audiobook(
        cache_key=key,
        topic=body.topic.strip(),
        normalized_topic=normalized,
        length_minutes=body.length_minutes,
        voice=body.voice,
        language=body.language,
        status=AudiobookStatus.QUEUED,
        requested_by_id=user.id,
    )
    session.add(ab)
    session.flush()
    job = Job(audiobook_id=ab.id)
    session.add(job)
    session.commit()

    worker_tasks.enqueue_generation(str(ab.id), str(user.id))
    if x_device_token:
        existing_dev = session.scalar(
            select(UserDevice).where(UserDevice.user_id == user.id, UserDevice.fcm_token == x_device_token)
        )
        if existing_dev is None:
            session.add(UserDevice(user_id=user.id, fcm_token=x_device_token))
            session.commit()

    out = _audiobook_out(ab, presign=False)
    return AudiobookCreatedOut(**out.model_dump(), cached=False)


@app.get("/audiobooks", response_model=CatalogResponse)
def list_catalog(
    topic: str | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(db_session),
):
    stmt = select(Audiobook).where(Audiobook.status == AudiobookStatus.READY)
    if topic:
        normalized = normalize_topic(topic)
        stmt = stmt.where(Audiobook.normalized_topic.ilike(f"%{normalized}%"))
    total = len(session.scalars(stmt).all())
    rows = session.scalars(stmt.order_by(Audiobook.created_at.desc()).offset(offset).limit(limit)).all()
    entries = [
        CatalogEntry(
            id=str(a.id),
            title=a.title or a.topic.title(),
            topic=a.topic,
            normalized_topic=a.normalized_topic,
            length_minutes=a.length_minutes,
            voice=a.voice.value,
            language=a.language,
            status=a.status.value,
            chapter_count=len(a.chapters),
        )
        for a in rows
    ]
    return CatalogResponse(results=entries, total=total)


@app.get("/audiobooks/{audiobook_id}", response_model=AudiobookOut)
def get_audiobook(audiobook_id: UUID, session: Session = Depends(db_session)):
    ab = session.get(Audiobook, audiobook_id)
    if ab is None:
        raise HTTPException(status_code=404, detail="audiobook not found")
    return _audiobook_out(ab, presign=ab.status == AudiobookStatus.READY)


@app.get("/me/entitlement", response_model=EntitlementOut)
def my_entitlement(session: Session = Depends(db_session), authorization: str = Header(default="")):
    user = current_user(session, authorization)
    session.commit()
    try:
        ent = auth.require_entitlement(session, user)
        return EntitlementOut(active=True, product_id=ent.product_id, expires_at=str(ent.expires_at))
    except auth.EntitlementError:
        return EntitlementOut(active=False)


@app.post("/me/device")
def register_device(body: DeviceTokenRequest, session: Session = Depends(db_session), authorization: str = Header(default="")):
    user = current_user(session, authorization)
    session.commit()
    existing = session.scalar(select(UserDevice).where(UserDevice.user_id == user.id, UserDevice.fcm_token == body.fcm_token))
    if existing is None:
        session.add(UserDevice(user_id=user.id, fcm_token=body.fcm_token))
        session.commit()
    return {"ok": True}


@app.post("/me/progress")
def save_progress(
    body: ProgressRequest,
    audiobook_id: UUID = Query(...),
    session: Session = Depends(db_session),
    authorization: str = Header(default=""),
):
    user = current_user(session, authorization)
    session.commit()
    progress = session.scalar(
        select(PlaybackProgress).where(PlaybackProgress.user_id == user.id, PlaybackProgress.audiobook_id == audiobook_id)
    )
    if progress is None:
        progress = PlaybackProgress(user_id=user.id, audiobook_id=audiobook_id)
        session.add(progress)
    progress.chapter_position = body.chapter_position
    progress.position_seconds = body.position_seconds
    session.commit()
    return {"ok": True}


@app.get("/me/progress")
def get_progress(audiobook_id: UUID = Query(...), session: Session = Depends(db_session), authorization: str = Header(default="")):
    user = current_user(session, authorization)
    session.commit()
    progress = session.scalar(
        select(PlaybackProgress).where(PlaybackProgress.user_id == user.id, PlaybackProgress.audiobook_id == audiobook_id)
    )
    if progress is None:
        return {"chapter_position": 0, "position_seconds": 0}
    return {"chapter_position": progress.chapter_position, "position_seconds": progress.position_seconds}


@app.get("/health")
def health():
    return {"status": "ok"}
