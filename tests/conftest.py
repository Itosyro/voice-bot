import atexit
import os
import shutil
import tempfile
from pathlib import Path

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token")

# Прод (вариант Б, self-hosted) работает на SQLite — значит и тесты обязаны.
# Раньше здесь стоял Postgres-URL: IS_SQLITE/_insert вычисляются на импорте, и
# весь диалектный код (sqlite-upsert, WAL-прагмы, наивное время) не исполнялся
# ни разу — ровно те ветки, которые крутятся у владельца на сервере.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="voicebot-tests-")
atexit.register(shutil.rmtree, _TEST_DB_DIR, ignore_errors=True)
os.environ.setdefault(
    "DATABASE_URL", f"sqlite+aiosqlite:///{Path(_TEST_DB_DIR).as_posix()}/test.db"
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
                    type(
                        "Choice",
                        (),
                        {
                            "delta": type("Delta", (), {"content": self._text})(),
                            "finish_reason": "stop",
                        },
                    )()
                ]
            },
        )()
        yield chunk


def make_groq_stream_response(text: str) -> FakeGroqStream:
    return FakeGroqStream(text)
