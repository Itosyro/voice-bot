from src.config import Settings


def test_settings_loads_required_fields(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://x")
    s = Settings()
    assert s.telegram_bot_token == "x"
    assert s.llm_model_default == "llama-3.3-70b-versatile"


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
