from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.config import settings
from src.storage.db import get_session
from src.storage.users import is_user_blocked
from src.ui.messages import NOT_ALLOWED, USER_BLOCKED

log = structlog.get_logger()


class AuthMiddleware(BaseMiddleware):
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
        if user and user.id not in settings.admin_user_ids_list:
            try:
                async with get_session() as session:
                    blocked = await is_user_blocked(session, user.id)
            except Exception as exc:
                log.warning("ban_check_db_unavailable", error=str(exc))
                blocked = False
            if blocked:
                if isinstance(event, Message):
                    await event.answer(USER_BLOCKED)
                return None

        allowed = settings.allowed_user_ids_list
        if not allowed:
            return await handler(event, data)

        if user and user.id in allowed:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer(NOT_ALLOWED)
        return None
