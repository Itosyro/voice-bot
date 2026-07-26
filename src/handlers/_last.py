"""In-memory store of each user's last request, used by the "Повтор" button.

Single-replica bot (Render free tier), so a process-local dict is enough. The
entry is overwritten on every new request, so the dict stays ~one row per active
user. Lost on restart — then "Повтор" just asks the user to resend.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class LastRequest:
    input_type: str  # "voice" | "text"
    mode: str
    style: str | None
    target_lang: str
    db_user_id: int | None  # None = БД была недоступна, история не писалась
    media: Any = None  # aiogram Voice/Audio/VideoNote/Video object (voice path)
    is_video: bool = False
    text: str | None = None  # text path


_store: dict[int, LastRequest] = {}

# Полный текст последнего результата по chat_id — для «Скачать .txt».
# Раньше экспорт брал msg.text: у многочастного ответа выгружалась только
# последняя часть, а у файлового фолбэка текста нет вовсе.
_results: dict[int, str] = {}


def save_last(telegram_user_id: int, req: LastRequest) -> None:
    _store[telegram_user_id] = req


def get_last(telegram_user_id: int) -> LastRequest | None:
    return _store.get(telegram_user_id)


def save_last_result(chat_id: int, result_text: str) -> None:
    _results[chat_id] = result_text


def get_last_result(chat_id: int) -> str | None:
    return _results.get(chat_id)
