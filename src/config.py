from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telegram
    telegram_bot_token: str
    allowed_user_ids: str = ""
    admin_user_ids: str = ""

    # Groq keys
    groq_api_key_polish: str | None = None
    groq_api_key_prompt: str | None = None
    groq_api_key_humanizer: str | None = None
    groq_api_key_translator: str | None = None
    groq_api_key_fallback: str | None = None

    # Models
    llm_model_default: str = "llama-3.3-70b-versatile"
    llm_model_fast: str = "llama-3.1-8b-instant"
    llm_model_strict: str = "llama-3.3-70b-versatile"
    whisper_model: str = "whisper-large-v3-turbo"

    # Database
    database_url: str

    # Limits
    max_voice_duration_sec: int = 600
    max_text_length: int = 10000
    rate_limit_per_user_per_min: int = 20

    enable_transcription_cache: bool = True
    skills_auto_sync_on_startup: bool = True
    skills_sync_interval_hours: int = 168

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "text"] = "json"

    @property
    def allowed_user_ids_list(self) -> list[int]:
        if not self.allowed_user_ids:
            return []
        return [int(x.strip()) for x in self.allowed_user_ids.split(",") if x.strip()]

    @property
    def admin_user_ids_list(self) -> list[int]:
        if not self.admin_user_ids:
            return []
        return [int(x.strip()) for x in self.admin_user_ids.split(",") if x.strip()]

    def get_groq_key(self, mode: str) -> str:
        key_map: dict[str, str | None] = {
            "polish": self.groq_api_key_polish,
            "prompt": self.groq_api_key_prompt,
            "humanizer": self.groq_api_key_humanizer,
            "translator": self.groq_api_key_translator,
        }
        key = key_map.get(mode) or self.groq_api_key_fallback
        if not key:
            raise RuntimeError(f"No Groq API key configured for mode '{mode}'")
        return key


settings = Settings()  # type: ignore[call-arg]
