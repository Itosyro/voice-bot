import asyncio
import os

import structlog
from aiohttp import web

from src.bot import create_bot, create_dispatcher
from src.config import settings
from src.logging_config import setup_logging
from src.services.skills_db import SkillsDB
from src.storage.db import get_session

log = structlog.get_logger()


async def load_skills() -> SkillsDB:
    """Load skills from database into memory for BM25 search."""
    async with get_session() as session:
        skills_db = await SkillsDB.load_from_db(session)
    log.info("skills_loaded", count=len(skills_db.skills))
    return skills_db


async def health_handler(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def run_health_server() -> None:
    """Run a minimal HTTP health-check server for Render."""
    port = int(os.environ.get("PORT", "10000"))
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("health_server_started", port=port)


async def main() -> None:
    setup_logging()
    log.info("starting_bot", log_level=settings.log_level)

    skills_db = await load_skills()

    bot = create_bot()
    dp = create_dispatcher()

    # Pass skills_db to all handlers via dispatcher workflow_data
    dp.workflow_data["skills_db"] = skills_db

    # Start health server for Render (if PORT env is set)
    if os.environ.get("PORT"):
        await run_health_server()

    try:
        # Ensure no webhook is registered - a leftover webhook from a previous
        # deploy makes Telegram reject getUpdates with TelegramConflictError.
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
