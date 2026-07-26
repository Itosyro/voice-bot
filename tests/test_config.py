from src.config import Settings


def test_settings_loads_required_fields(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    s = Settings()
    assert s.telegram_bot_token == "x"
    # llama-модели деприкейтнуты Groq (июнь 2026) — дефолт мигрирован на gpt-oss.
    assert s.llm_model_default == "openai/gpt-oss-120b"
    assert "qwen/qwen3.6-27b" in s.llm_model_fallbacks_list


def test_get_groq_key_uses_fallback(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("GROQ_API_KEY_FALLBACK", "fallback")
    s = Settings()
    assert s.get_groq_key("polish") == "fallback"


def test_allowed_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123, 456, 789")
    s = Settings()
    assert s.allowed_user_ids_list == [123, 456, 789]


def test_allowed_user_ids_empty(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    s = Settings()
    assert s.allowed_user_ids_list == []
