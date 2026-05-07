from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_transcription_idx = 0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telegram
    telegram_bot_token: str
    allowed_user_ids: str = ""
    admin_user_ids: str = ""

    # Webhook (Render deploy)
    webhook_url: str | None = None
    webhook_secret: str | None = None

    # Groq keys
    groq_api_key_polish: str | None = None
    groq_api_key_prompt: str | None = None
    groq_api_key_humanizer: str | None = None
    groq_api_key_translator: str | None = None
    groq_api_key_fallback: str | None = None

    # Models
    llm_model_default: str = "llama-3.3-70b-versatile"
    llm_model_fast: str = "llama-3.1-8b-instant"
    llm_model_strict: str = "openai/gpt-oss-120b"
    whisper_model: str = "whisper-large-v3-turbo"

    # Database
    database_url: str

    @model_validator(mode="after")
    def fix_database_url(self) -> "Settings":
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            self.database_url = url
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            self.database_url = url
        return self

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
            "summary": self.groq_api_key_fallback,
        }
        key = key_map.get(mode) or self.groq_api_key_fallback
        if not key:
            raise RuntimeError(f"No Groq API key configured for mode '{mode}'")
        return key

    def get_all_groq_keys(self) -> list[str]:
        """Return all unique configured Groq API keys."""
        keys = [
            self.groq_api_key_polish,
            self.groq_api_key_prompt,
            self.groq_api_key_humanizer,
            self.groq_api_key_translator,
            self.groq_api_key_fallback,
        ]
        seen: set[str] = set()
        result: list[str] = []
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                result.append(k)
        return result

    def get_transcription_key(self) -> str:
        """Round-robin key for transcription to distribute load across accounts."""
        global _transcription_idx
        keys = self.get_all_groq_keys()
        if not keys:
            raise RuntimeError("No Groq API keys configured")
        key = keys[_transcription_idx % len(keys)]
        _transcription_idx += 1
        return key


settings = Settings()  # type: ignore[call-arg]
