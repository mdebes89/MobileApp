from pydantic import BaseModel, Field


class CreateAudiobookRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    length_minutes: int = Field(ge=10, le=60)
    voice: str
    language: str = "en"


class ChapterOut(BaseModel):
    position: int
    title: str
    arc_section: str
    duration_seconds: int | None = None
    audio_url: str | None = None


class AudiobookOut(BaseModel):
    id: str
    title: str
    topic: str
    normalized_topic: str
    length_minutes: int
    voice: str
    language: str
    status: str
    error_message: str | None = None
    chapters: list[ChapterOut] = []


class AudiobookCreatedOut(AudiobookOut):
    cached: bool = False


class CatalogEntry(BaseModel):
    id: str
    title: str
    topic: str
    normalized_topic: str
    length_minutes: int
    voice: str
    language: str
    status: str
    chapter_count: int = 0


class CatalogResponse(BaseModel):
    results: list[CatalogEntry]
    total: int


class DeviceTokenRequest(BaseModel):
    fcm_token: str = Field(min_length=10, max_length=500)


class ProgressRequest(BaseModel):
    chapter_position: int = Field(ge=0)
    position_seconds: int = Field(ge=0)


class EntitlementOut(BaseModel):
    active: bool
    product_id: str | None = None
    expires_at: str | None = None
