import asyncio
import os

import structlog
from aiohttp import web

from src.bot import create_bot, create_dispatcher
from src.config import settings
from src.logging_config import setup_logging
from src.services.skills_db import SkillsDB
from src.storage.db import engine, get_session

log = structlog.get_logger()


async def load_skills() -> SkillsDB:
    """Load skills from database into memory for BM25 search."""
    async with get_session() as session:
        skills_db = await SkillsDB.load_from_db(session)
    log.info("skills_loaded", count=len(skills_db.skills))
    return skills_db


async def _health(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def run_health_server() -> web.AppRunner:
    """Run a minimal HTTP health-check server for Render."""
    port = int(os.environ.get("PORT", "10000"))
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("health_server_started", port=port)
    return runner


async def main() -> None:
    setup_logging()
    log.info("starting_bot", log_level=settings.log_level)

    skills_db = await load_skills()

    bot = create_bot()
    dp = create_dispatcher()

    dp.workflow_data["skills_db"] = skills_db

    health_runner = None
    if os.environ.get("PORT"):
        health_runner = await run_health_server()

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        if health_runner:
            await health_runner.cleanup()
        await engine.dispose()
        log.info("shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
