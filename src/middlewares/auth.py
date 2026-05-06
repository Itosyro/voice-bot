from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.config import settings
from src.ui.messages import NOT_ALLOWED


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        allowed = settings.allowed_user_ids_list
        if not allowed:
            return await handler(event, data)

        user = data.get("event_from_user")
        if user and user.id in allowed:
            return await handler(event, data)

        if isinstance(event, Message):
            await event.answer(NOT_ALLOWED)
        return None
