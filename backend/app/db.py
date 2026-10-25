from datetime import datetime
import enum

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Voice(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"


class AudiobookStatus(str, enum.Enum):
    QUEUED = "queued"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    google_sub: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    entitlements: Mapped[list["Entitlement"]] = relationship(back_populates="user")
    devices: Mapped[list["UserDevice"]] = relationship(back_populates="user")
    requested: Mapped[list["Audiobook"]] = relationship(back_populates="requested_by")
    progress: Mapped[list["PlaybackProgress"]] = relationship(back_populates="user")


class Entitlement(Base):
    __tablename__ = "entitlements"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="entitlements")


class UserDevice(Base):
    __tablename__ = "user_devices"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fcm_token: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="devices")


class Audiobook(Base):
    __tablename__ = "audiobooks"
    __table_args__ = (
        Index("ix_audiobooks_cache_key_status", "cache_key", "status"),
        Index("ix_audiobooks_topic_trgm", "topic"),
    )

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    cache_key: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_topic: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    length_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    voice: Mapped[Voice] = mapped_column(Enum(Voice, name="voice"), nullable=False)
    language: Mapped[str] = mapped_column(String(20), nullable=False, default="en")
    status: Mapped[AudiobookStatus] = mapped_column(
        Enum(AudiobookStatus, name="audiobook_status"), nullable=False, default=AudiobookStatus.QUEUED
    )
    script_markdown: Mapped[str | None] = mapped_column(Text)
    script_object_key: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)
    requested_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    generation_meta: Mapped[dict | None] = mapped_column(JSONB)

    requested_by: Mapped[User | None] = relationship(back_populates="requested")
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="audiobook", order_by="Chapter.position", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    audiobook_id: Mapped[UUID] = mapped_column(ForeignKey("audiobooks.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    arc_section: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audio_object_key: Mapped[str | None] = mapped_column(String(500))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    audiobook: Mapped[Audiobook] = relationship(back_populates="chapters")


class PlaybackProgress(Base):
    __tablename__ = "playback_progress"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    audiobook_id: Mapped[UUID] = mapped_column(ForeignKey("audiobooks.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="progress")
    audiobook: Mapped[Audiobook] = relationship()


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    audiobook_id: Mapped[UUID] = mapped_column(ForeignKey("audiobooks.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, name="job_status"), nullable=False, default=JobStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step: Mapped[str | None] = mapped_column(String(50))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
