import asyncio

import structlog

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


async def main() -> None:
    setup_logging()
    log.info("starting_bot", log_level=settings.log_level)

    skills_db = await load_skills()

    bot = create_bot()
    dp = create_dispatcher()

    # Pass skills_db to all handlers via dispatcher workflow_data
    dp.workflow_data["skills_db"] = skills_db

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
