"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("google_sub", sa.String(320), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=True)

    op.create_table(
        "entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.String(100), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_entitlements_user_id", "entitlements", ["user_id"])

    op.create_enum("voice", ["male", "female"])
    op.create_enum("audiobook_status", ["queued", "generating", "ready", "failed"])
    op.create_enum("job_status", ["pending", "running", "done", "failed"])

    op.create_table(
        "audiobooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cache_key", sa.String(500), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("normalized_topic", sa.String(200), nullable=False),
        sa.Column("title", sa.String(300), nullable=False, server_default=sa.text("''")),
        sa.Column("length_minutes", sa.Integer(), nullable=False),
        sa.Column("voice", sa.Enum("male", "female", name="voice"), nullable=False),
        sa.Column("language", sa.String(20), nullable=False, server_default=sa.text("'en'")),
        sa.Column("status", sa.Enum("queued", "generating", "ready", "failed", name="audiobook_status"), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("script_markdown", sa.Text(), nullable=True),
        sa.Column("script_object_key", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("generation_meta", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_audiobooks_cache_key", "audiobooks", ["cache_key"])
    op.create_index("ix_audiobooks_normalized_topic", "audiobooks", ["normalized_topic"])
    op.create_index("ix_audiobooks_cache_key_status", "audiobooks", ["cache_key", "status"])
    op.create_index("ix_audiobooks_requested_by_id", "audiobooks", ["requested_by_id"])

    op.create_table(
        "chapters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("audiobook_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audiobooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("arc_section", sa.String(50), nullable=False, server_default=sa.text("''")),
        sa.Column("text", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("audio_object_key", sa.String(500), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
    )
    op.create_index("ix_chapters_audiobook_id", "chapters", ["audiobook_id"])

    op.create_table(
        "user_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fcm_token", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_devices_user_id", "user_devices", ["user_id"])
    op.create_index("ix_user_devices_fcm_token", "user_devices", ["fcm_token"])

    op.create_table(
        "playback_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audiobook_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audiobooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("position_seconds", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_playback_progress_user_id", "playback_progress", ["user_id"])
    op.create_index("ix_playback_progress_audiobook_id", "playback_progress", ["audiobook_id"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("audiobook_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("audiobooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "done", "failed", name="job_status"), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("step", sa.String(50), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_jobs_audiobook_id", "jobs", ["audiobook_id"])


def downgrade() -> None:
    op.drop_table("jobs")
    op.drop_table("playback_progress")
    op.drop_table("user_devices")
    op.drop_table("chapters")
    op.drop_table("audiobooks")
    op.drop_table("entitlements")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS audiobook_status")
    op.execute("DROP TYPE IF EXISTS voice")
