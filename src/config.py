from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telegram
    telegram_bot_token: str
    allowed_user_ids: str = ""
    admin_user_ids: str = ""

    # Webhook (Render deploy) — если не задан webhook_url, используется long-polling
    webhook_url: str | None = None
    webhook_secret: str | None = None

    # Groq keys
    groq_api_key_polish: str | None = None
    groq_api_key_prompt: str | None = None
    groq_api_key_humanizer: str | None = None
    groq_api_key_translator: str | None = None
    groq_api_key_summary: str | None = None
    groq_api_key_fallback: str | None = None

    # Models
    llm_model_default: str = "llama-3.3-70b-versatile"
    llm_model_fast: str = "llama-3.1-8b-instant"
    llm_model_strict: str = "openai/gpt-oss-120b"
    # large-v3 (НЕ turbo) — выбран осознанно: качество распознавания важнее скорости.
    # turbo быстрее, но заметно хуже на сложной речи/акцентах/матах. Не менять на turbo.
    whisper_model: str = "whisper-large-v3"

    # Database
    database_url: str

    # Limits
    max_voice_duration_sec: int = 3600  # 1 hour absolute cap (chunked beyond chunk_threshold)
    chunk_threshold_sec: int = 600  # voices longer than this go through chunked pipeline
    chunk_duration_sec: int = 300  # size of a single audio chunk (5 min)
    chunk_throttle_sec: float = 1.5  # pause between Groq calls to avoid rate limit
    max_voice_file_mb: int = 20
    max_text_length: int = 10000
    rate_limit_per_user_per_min: int = 20

    enable_transcription_cache: bool = True
    skills_auto_sync_on_startup: bool = True
    skills_sync_interval_hours: int = 168

    # Retention / cleanup (фоновая задача удаляет старые строки из БД)
    transcription_cache_ttl_days: int = 1  # удалять кэш транскриптов старше N дней (0 — выкл.)
    request_history_ttl_days: int = 30  # удалять историю запросов старше N дней (0 — выкл.)
    cleanup_interval_hours: int = 24  # как часто запускать cleanup
    cleanup_initial_delay_sec: int = 300  # пауза перед первым запуском после старта

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
            "summary": self.groq_api_key_summary,
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
            self.groq_api_key_summary,
            self.groq_api_key_fallback,
        ]
        seen: set[str] = set()
        result: list[str] = []
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                result.append(k)
        return result


settings = Settings()  # type: ignore[call-arg]
