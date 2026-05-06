import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.config import settings
from src.ui.messages import RATE_LIMIT_ERROR

_CLEANUP_INTERVAL = 300  # seconds


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._user_requests: dict[int, list[float]] = defaultdict(list)
        self._last_cleanup: float = time.monotonic()

    def _maybe_cleanup(self, now: float) -> None:
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        stale = [uid for uid, ts in self._user_requests.items() if not ts or now - ts[-1] > 120]
        for uid in stale:
            del self._user_requests[uid]

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
        self._maybe_cleanup(now)

        user_id = user.id
        window = 60.0
        limit = settings.rate_limit_per_user_per_min

        self._user_requests[user_id] = [t for t in self._user_requests[user_id] if now - t < window]

        if len(self._user_requests[user_id]) >= limit:
            if isinstance(event, Message):
                await event.answer(RATE_LIMIT_ERROR)
            return None

        self._user_requests[user_id].append(now)
        return await handler(event, data)
