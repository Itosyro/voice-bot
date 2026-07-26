import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types.error_event import ErrorEvent

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

    # Middlewares (order matters). Auth + rate-limit стоят и на callback_query:
    # иначе забаненный юзер жмёт кнопки (в т.ч. «Повтор» = прогон LLM), а спам
    # кнопками не троттлится.
    dp.message.middleware(AuthMiddleware())
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(DbSessionMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
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
        """Last-resort net: любой необработанный хендлером эксепшн (например,
        мёртвая БД в админ-командах) логируется и не роняет polling. Юзеру
        отвечаем, чтобы бот не выглядел «молчащим»."""
        log.exception("unhandled_update_error", exc_info=event.exception)
        try:
            update = event.update
            if update.message:
                await update.message.answer("⚠ Внутренняя ошибка. Попробуй ещё раз чуть позже.")
            elif update.callback_query:
                await update.callback_query.answer("⚠ Ошибка. Попробуй ещё раз.", show_alert=False)
        except Exception:  # ответ тоже может не уйти (напр., нет прав) — не важно
            pass
        return True

    return dp
