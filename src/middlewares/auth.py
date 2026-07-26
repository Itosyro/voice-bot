import time
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.config import settings
from src.storage.db import get_session
from src.storage.users import is_user_blocked
from src.ui.messages import NOT_ALLOWED, USER_BLOCKED

log = structlog.get_logger()

BAN_CACHE_TTL = 60.0  # сек; бан вступает в силу максимум через минуту


class AuthMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._ban_cache: dict[int, tuple[bool, float]] = {}

    def _cached_ban(self, user_id: int) -> bool | None:
        """Закэшированный статус бана или None, если кэш пуст/протух."""
        entry = self._ban_cache.get(user_id)
        if entry is None:
            return None
        blocked, at = entry
        if time.monotonic() - at > BAN_CACHE_TTL:
            self._ban_cache.pop(user_id, None)
            return None
        return blocked

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")

        # Dynamic ban (DB flag) — admins can never lock themselves out.
        # Мёртвая БД не должна глушить бота: при ошибке пропускаем проверку бана
        # (fail-open) — реальный доступ всё равно ограничен ALLOWED_USER_IDS.
        # Результат кэшируется на BAN_CACHE_TTL сек: раньше КАЖДЫЙ апдейт
        # (включая тапы по кнопкам) открывал вторую сессию БД (критик Б2).
        if user and user.id not in settings.admin_user_ids_list:
            blocked = self._cached_ban(user.id)
            if blocked is None:
                try:
                    async with get_session() as session:
                        blocked = await is_user_blocked(session, user.id)
                except Exception as exc:
                    log.warning("ban_check_db_unavailable", error=str(exc))
                    blocked = False
                self._ban_cache[user.id] = (blocked, time.monotonic())
            if blocked:
                if isinstance(event, Message):
                    await event.answer(USER_BLOCKED)
                elif isinstance(event, CallbackQuery):
                    await event.answer(USER_BLOCKED, show_alert=False)
                return None

        allowed = settings.allowed_user_ids_list
        if not allowed:
            return await handler(event, data)

        if user and user.id in allowed:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer(NOT_ALLOWED)
        elif isinstance(event, CallbackQuery):
            await event.answer(NOT_ALLOWED, show_alert=False)
        return None
