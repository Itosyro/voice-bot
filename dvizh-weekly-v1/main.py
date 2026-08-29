from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from . import bot as bot_handlers
from . import settings_router
from . import weekly_router
from .config import Settings
from .db import Database
from .scheduler import Scheduler
from .weekly_scheduler import WeeklyScheduler
from .weekly_store import WeeklyStore


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    db = Database(settings.database_path)
    weekly_store = WeeklyStore(settings.database_path)
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    settings_router.configure(db, settings)
    weekly_router.configure(db, settings, weekly_store)
    bot_handlers.configure(db, settings)

    dp.include_router(settings_router.router)
    dp.include_router(weekly_router.router)
    dp.include_router(bot_handlers.router)

    scheduler = Scheduler(bot, db, settings)
    weekly_scheduler = WeeklyScheduler(bot, db, weekly_store, settings)
    scheduler_task = asyncio.create_task(scheduler.run(), name="dvizh-scheduler")
    weekly_task = asyncio.create_task(weekly_scheduler.run(), name="dvizh-weekly-scheduler")

    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        scheduler.stop()
        weekly_scheduler.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_stop)
        except NotImplementedError:
            pass

    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        request_stop()
        scheduler_task.cancel()
        weekly_task.cancel()
        await asyncio.gather(scheduler_task, weekly_task, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
