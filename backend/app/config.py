from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "History Audiobooks"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/audiobooks"
    redis_url: str = "redis://localhost:6379/0"

    mistral_api_key: str = ""
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_chat_model: str = "mistral-large-latest"
    mistral_tts_model: str = "voxtral-mini-tts-3-0"
    mistral_tts_voice_male: str = "en_paul_neutral"
    mistral_tts_voice_female: str = "voice_478"
    mistral_tts_chunk_chars: int = 4500

    mistral_rpm_limit: int = 30
    mistral_rpm_window: int = 60

    google_client_ids: str = ""
    google_iam_service_account_info: str = ""
    google_iam_service_account_email: str = ""

    s3_endpoint_url: str = ""
    aws_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_presign_expiry_seconds: int = 3600

    fcm_enabled: bool = False
    fcm_credentials_json: str = ""

    catalog_seed_dir: str = ""

    @property
    def google_client_id_list(self) -> list[str]:
        return [cid.strip() for cid in self.google_client_ids.split(",") if cid.strip()]

    def tts_voice_id(self, voice: str) -> str:
        return self.mistral_tts_voice_male if voice == "male" else self.mistral_tts_voice_female


@lru_cache
def get_settings() -> Settings:
    return Settings()
