from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.config import settings
from src.storage.db import get_session
from src.storage.users import is_user_blocked
from src.ui.messages import NOT_ALLOWED, USER_BLOCKED


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")

        # Dynamic ban (DB flag) — admins can never lock themselves out.
        if user and user.id not in settings.admin_user_ids_list:
            async with get_session() as session:
                if await is_user_blocked(session, user.id):
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
