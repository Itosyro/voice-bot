"""Resilient user-settings access: DB first, in-memory fallback when DB is down.

Бесплатные Postgres-тарифы (Supabase/Neon) периодически «умирают» (пауза
проекта, истёкший срок). Без этого слоя мёртвая БД означала: кнопки выбора
режима молча не работают, а каждое сообщение падает до вызова LLM. Теперь бот
продолжает работать на настройках из памяти процесса; история/кэш просто
не пишутся, пока БД не вернётся.
"""

import contextlib
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.users import get_or_create_user, update_user_settings

log = structlog.get_logger()


@dataclass
class MemorySettings:
    default_mode: str | None = None
    default_style: str | None = None
    target_lang: str = "en"
    synced: bool = True  # False = записано только в память, БД была недоступна


# Живёт в памяти процесса; при рестарте пропадает (тогда настройки снова из БД).
_store: dict[int, MemorySettings] = {}


@dataclass
class UserContext:
    """Настройки пользователя для обработки запроса (из БД или из памяти)."""

    telegram_user_id: int
    db_user_id: int | None  # None = БД недоступна, историю не сохраняем
    default_mode: str | None = None
    default_style: str | None = None
    target_lang: str = "en"
    total_requests: int = 0
    from_db: bool = True


def _mem(telegram_user_id: int) -> MemorySettings:
    if telegram_user_id not in _store:
        _store[telegram_user_id] = MemorySettings()
    return _store[telegram_user_id]


async def load_user_context(
    session: AsyncSession,
    telegram_user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    language_code: str | None = None,
) -> UserContext:
    """Load mode/style/lang for a user; survive a dead DB via the memory store."""
    try:
        user = await get_or_create_user(
            session,
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            language_code=language_code,
        )
    except Exception as exc:
        log.warning(
            "db_unavailable_using_memory", telegram_user_id=telegram_user_id, error=str(exc)
        )
        mem = _store.get(telegram_user_id)
        return UserContext(
            telegram_user_id=telegram_user_id,
            db_user_id=None,
            default_mode=mem.default_mode if mem else None,
            default_style=mem.default_style if mem else None,
            target_lang=mem.target_lang if mem else "en",
            from_db=False,
        )

    mem = _store.get(telegram_user_id)
    if mem and not mem.synced:
        # Пока БД лежала, юзер менял настройки — память новее. Досинхронизируем.
        try:
            await update_user_settings(
                session,
                telegram_user_id=telegram_user_id,
                default_mode=mem.default_mode,
                default_style=mem.default_style,
                target_lang=mem.target_lang,
            )
            mem.synced = True
            log.info("memory_settings_resynced", telegram_user_id=telegram_user_id)
        except Exception as exc:
            log.warning("memory_resync_failed", error=str(exc))
        return UserContext(
            telegram_user_id=telegram_user_id,
            db_user_id=user.id,
            default_mode=mem.default_mode,
            default_style=mem.default_style,
            target_lang=mem.target_lang,
            total_requests=user.total_requests,
            from_db=False,
        )

    return UserContext(
        telegram_user_id=telegram_user_id,
        db_user_id=user.id,
        default_mode=user.default_mode,
        default_style=user.default_style,
        target_lang=user.target_lang or "en",
        total_requests=user.total_requests,
    )


async def save_user_settings(
    session: AsyncSession,
    telegram_user_id: int,
    *,
    default_mode: str | None = None,
    default_style: str | None = None,
    target_lang: str | None = None,
    reset: bool = False,
) -> bool:
    """Persist settings to DB and mirror them in memory.

    Returns True if the DB write worked, False if only the memory store got it.
    Кнопки выбора режима зовут это вместо прямого update_user_settings — выбор
    юзера не должен молча теряться из-за мёртвой БД. reset=True очищает
    режим/стиль (кнопка «Сброс»).
    """
    mem = _mem(telegram_user_id)
    if reset:
        mem.default_mode = None
        mem.default_style = None
    if default_mode is not None:
        mem.default_mode = default_mode
    if default_style is not None:
        mem.default_style = default_style
    if target_lang is not None:
        mem.target_lang = target_lang

    kwargs: dict[str, str | int | bool | None] = {}
    if reset:
        kwargs["default_mode"] = None
        kwargs["default_style"] = None
    if default_mode is not None:
        kwargs["default_mode"] = default_mode
    if default_style is not None:
        kwargs["default_style"] = default_style
    if target_lang is not None:
        kwargs["target_lang"] = target_lang

    try:
        # get_or_create: UPDATE по несуществующему юзеру молча обновил бы 0 строк.
        await get_or_create_user(session, telegram_user_id=telegram_user_id)
        await update_user_settings(session, telegram_user_id=telegram_user_id, **kwargs)
        await session.commit()
        mem.synced = True
        return True
    except Exception as exc:
        log.warning(
            "settings_saved_to_memory_only", telegram_user_id=telegram_user_id, error=str(exc)
        )
        mem.synced = False
        # Рулбэк на мёртвом коннекте может тоже падать — глушим.
        with contextlib.suppress(Exception):
            await session.rollback()
        return False


def reset_memory_store() -> None:
    """For tests."""
    _store.clear()
