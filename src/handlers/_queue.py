"""Per-user последовательная обработка + защита от даблтапов.

Один пользователь = один прогон за раз: 5 голосовых подряд раньше запускали
5 конкурирующих пайплайнов, дерущихся за пул БД и лимиты Groq. Замок в памяти
процесса (бот — одна реплика).
"""

import asyncio

_locks: dict[int, asyncio.Lock] = {}


def user_lock(telegram_user_id: int) -> asyncio.Lock:
    if telegram_user_id not in _locks:
        _locks[telegram_user_id] = asyncio.Lock()
    return _locks[telegram_user_id]


def is_busy(telegram_user_id: int) -> bool:
    """True, если у пользователя прямо сейчас идёт обработка."""
    lock = _locks.get(telegram_user_id)
    return lock is not None and lock.locked()


def cleanup_idle_locks() -> None:
    """Выкидываем свободные замки, чтобы dict не рос вечно (зовётся из cleanup-цикла)."""
    for uid in [uid for uid, lock in _locks.items() if not lock.locked()]:
        _locks.pop(uid, None)
