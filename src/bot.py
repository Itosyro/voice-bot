import contextlib

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from src.config import settings
from src.handlers import admin, callbacks, modes, start, text, voice
from src.handlers import settings as settings_handler
from src.middlewares.auth import AuthMiddleware
from src.middlewares.db_session import DbSessionMiddleware
from src.middlewares.rate_limit import RateLimitMiddleware

log = structlog.get_logger()


def create_bot() -> Bot:
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares (order matters)
    dp.message.middleware(AuthMiddleware())
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(DbSessionMiddleware())

    # Routers
    dp.include_router(start.router)
    dp.include_router(modes.router)
    dp.include_router(settings_handler.router)
    dp.include_router(admin.router)
    dp.include_router(callbacks.router)
    dp.include_router(voice.router)
    dp.include_router(text.router)

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        log.error("unhandled_error", error=str(event.exception), update=str(event.update))
        if event.update and event.update.callback_query:
            with contextlib.suppress(Exception):
                await event.update.callback_query.answer("Ошибка. Попробуй ещё раз.")
        return True

    return dp
