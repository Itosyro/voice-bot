from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import settings
from src.handlers import admin, callbacks, modes, start, text, voice
from src.handlers import settings as settings_handler
from src.middlewares.auth import AuthMiddleware
from src.middlewares.db_session import DbSessionMiddleware
from src.middlewares.rate_limit import RateLimitMiddleware


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

    return dp
