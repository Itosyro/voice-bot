"""In-memory store of each user's last request, used by the "Повтор" button.

Single-replica bot (Render free tier), so a process-local dict is enough. The
entry is overwritten on every new request, so the dict stays ~one row per active
user. Lost on restart — then "Повтор" just asks the user to resend.
"""

import time
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

# Результаты по конкретному сообщению (chat_id, message_id): кнопка «Скачать»
# под СТАРЫМ результатом должна выгружать именно его, а не последний.
_results_by_message: dict[tuple[int, int], str] = {}
_RESULTS_BY_MESSAGE_CAP = 500  # не даём словарю расти бесконечно

# Транскрипты последних голосовых по chat_id, с временем — для кнопки
# «Транскрипт» и для склейки нескольких голосовых подряд в один текст.
_transcripts: dict[int, list[tuple[str, float]]] = {}
_TRANSCRIPTS_PER_CHAT = 5


def save_last(telegram_user_id: int, req: LastRequest) -> None:
    _store[telegram_user_id] = req


def get_last(telegram_user_id: int) -> LastRequest | None:
    return _store.get(telegram_user_id)


def save_last_result(chat_id: int, result_text: str) -> None:
    _results[chat_id] = result_text


def get_last_result(chat_id: int) -> str | None:
    return _results.get(chat_id)


def save_result_for_message(chat_id: int, message_id: int, result_text: str) -> None:
    if len(_results_by_message) >= _RESULTS_BY_MESSAGE_CAP:
        # FIFO-ротация: выкидываем самые старые записи.
        for key in list(_results_by_message)[: _RESULTS_BY_MESSAGE_CAP // 5]:
            _results_by_message.pop(key, None)
    _results_by_message[(chat_id, message_id)] = result_text


def get_result_for_message(chat_id: int, message_id: int) -> str | None:
    return _results_by_message.get((chat_id, message_id))


def save_last_transcript(chat_id: int, transcript: str) -> None:
    recent = _transcripts.setdefault(chat_id, [])
    recent.append((transcript, time.monotonic()))
    del recent[:-_TRANSCRIPTS_PER_CHAT]  # держим только последние N


def get_last_transcript(chat_id: int) -> str | None:
    recent = _transcripts.get(chat_id)
    return recent[-1][0] if recent else None


def get_recent_transcripts(chat_id: int, window_sec: float, limit: int = 3) -> list[str]:
    """Транскрипты голосовых, присланных за последние window_sec секунд.

    Владелец часто наговаривает одну мысль двумя-тремя голосовыми подряд —
    это позволяет склеить их в один текст без пересылки.
    """
    recent = _transcripts.get(chat_id) or []
    now = time.monotonic()
    fresh = [text for text, at in recent if now - at <= window_sec]
    return fresh[-limit:]
