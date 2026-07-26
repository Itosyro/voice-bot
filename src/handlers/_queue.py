"""Per-user последовательная обработка + защита от даблтапов.

Один пользователь = один прогон за раз: 5 голосовых подряд раньше запускали
5 конкурирующих пайплайнов, дерущихся за пул БД и лимиты Groq. Замок в памяти
процесса (бот — одна реплика).

Замки НЕ вычищаются по таймеру специально: у ожидающего в очереди сообщения
уже есть ссылка на объект замка, и удаление его из словаря создало бы
«осиротевший» замок — новое сообщение получило бы другой объект, и два
пайплайна одного юзера пошли бы параллельно. Полсотни asyncio.Lock — это
несколько килобайт, чистить нечего.
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


async def acquire_or_none(telegram_user_id: int) -> asyncio.Lock | None:
    """Захватить замок без ожидания; None — пользователь уже занят.

    Проверка и захват идут подряд без единого await между ними: свободный
    asyncio.Lock захватывается синхронно, управление не отдаётся. Раньше между
    `is_busy()` и `async with lock` стоял `callback.answer()` (сетевой вызов) —
    два быстрых тапа успевали пройти проверку оба и запускали двойной прогон.
    """
    lock = user_lock(telegram_user_id)
    if lock.locked():
        return None
    await lock.acquire()
    return lock
