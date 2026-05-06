import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/voicebot"
)
os.environ.setdefault("GROQ_API_KEY_FALLBACK", "test_key")
