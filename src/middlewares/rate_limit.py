import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.config import settings
from src.ui.messages import RATE_LIMIT_ERROR


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._user_requests: dict[int, list[float]] = defaultdict(list)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        now = time.monotonic()
        user_id = user.id
        window = 60.0
        limit = settings.rate_limit_per_user_per_min

        # Clean old entries; drop the key entirely when a user goes idle so the
        # dict cannot grow unbounded with one entry per user_id ever seen.
        recent = [t for t in self._user_requests[user_id] if now - t < window]
        if not recent:
            self._user_requests.pop(user_id, None)
        else:
            self._user_requests[user_id] = recent

        if len(recent) >= limit:
            if isinstance(event, Message):
                await event.answer(RATE_LIMIT_ERROR)
            return None

        self._user_requests[user_id].append(now)
        return await handler(event, data)
