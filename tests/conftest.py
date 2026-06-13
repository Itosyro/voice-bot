import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/voicebot"
)
os.environ.setdefault("GROQ_API_KEY_FALLBACK", "test_key")


class FakeGroqStream:
    """Async-iterable fake for a Groq streaming response, yielding one chunk."""

    def __init__(self, text: str) -> None:
        self._text = text

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        chunk = type(
            "Chunk",
            (),
            {
                "choices": [
                    type("Choice", (), {"delta": type("Delta", (), {"content": self._text})()})()
                ]
            },
        )()
        yield chunk


def make_groq_stream_response(text: str) -> FakeGroqStream:
    return FakeGroqStream(text)
