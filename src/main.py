import asyncio
import contextlib
import os

import aiohttp
import structlog
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from src.bot import create_bot, create_dispatcher
from src.config import settings
from src.logging_config import setup_logging
from src.services.skills_db import SkillsDB
from src.storage.cleanup import cleanup_old_records
from src.storage.db import engine, get_session

log = structlog.get_logger()

SELF_PING_INTERVAL_SEC = 600
SELF_PING_INITIAL_DELAY_SEC = 60


async def load_skills() -> SkillsDB:
    """Load skills from database into memory for BM25 search."""
    async with get_session() as session:
        skills_db = await SkillsDB.load_from_db(session)
    log.info("skills_loaded", count=len(skills_db.skills))
    return skills_db


async def health_handler(_request: web.Request) -> web.Response:
    return web.Response(text="ok")


async def run_health_server() -> web.AppRunner:
    """Run a minimal HTTP health-check server for Render (polling mode)."""
    port = int(os.environ.get("PORT", "10000"))
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("health_server_started", port=port)
    return runner


async def _self_ping(url: str) -> None:
    """Ping own /health endpoint every 10 min to prevent Render from sleeping."""
    await asyncio.sleep(SELF_PING_INITIAL_DELAY_SEC)
    target = f"{url.rstrip('/')}/health"
    while True:
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(target, timeout=aiohttp.ClientTimeout(total=10)),
            ):
                pass
            log.info("self_ping_ok", url=target)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("self_ping_failed", error=str(exc), url=target)
        await asyncio.sleep(SELF_PING_INTERVAL_SEC)


async def _cleanup_loop() -> None:
    """Periodically delete stale rows from transcription_cache and request_history."""
    await asyncio.sleep(settings.cleanup_initial_delay_sec)
    interval_sec = max(60, settings.cleanup_interval_hours * 3600)
    while True:
        try:
            async with get_session() as session:
                transcripts, history = await cleanup_old_records(
                    session,
                    transcription_ttl_days=settings.transcription_cache_ttl_days,
                    history_ttl_days=settings.request_history_ttl_days,
                )
            log.info(
                "cleanup_run",
                transcripts_deleted=transcripts,
                history_deleted=history,
                next_in_sec=interval_sec,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("cleanup_failed", error=str(exc))
        await asyncio.sleep(interval_sec)


async def run_webhook(bot: Bot, dp: Dispatcher) -> None:
    """Run aiohttp server with aiogram webhook handler + self-ping + cleanup."""
    assert settings.webhook_url is not None
    port = int(os.environ.get("PORT", "10000"))
    webhook_path = f"/webhook/{settings.telegram_bot_token}"
    webhook_full_url = f"{settings.webhook_url.rstrip('/')}{webhook_path}"

    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)

    handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret,
    )
    handler.register(app, path=webhook_path)
    setup_application(app, dp, bot=bot)

    await bot.set_webhook(
        url=webhook_full_url,
        secret_token=settings.webhook_secret,
        drop_pending_updates=True,
    )
    log.info("webhook_set", url=webhook_full_url)

    ping_task = asyncio.create_task(_self_ping(settings.webhook_url))
    cleanup_task = asyncio.create_task(_cleanup_loop())

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("webhook_server_started", port=port)

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        for task in (ping_task, cleanup_task):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        try:
            await bot.delete_webhook(drop_pending_updates=False)
            log.info("webhook_deleted")
        except Exception as exc:
            log.warning("webhook_delete_failed", error=str(exc))
        await runner.cleanup()


async def main() -> None:
    setup_logging()
    log.info("starting_bot", log_level=settings.log_level)

    skills_db = await load_skills()

    bot = create_bot()
    dp = create_dispatcher()

    # Pass skills_db to all handlers via dispatcher workflow_data
    dp.workflow_data["skills_db"] = skills_db

    if settings.webhook_url:
        log.info("mode", mode="webhook")
        try:
            await run_webhook(bot, dp)
        finally:
            await bot.session.close()
            await engine.dispose()
            log.info("shutdown_complete")
    else:
        log.info("mode", mode="polling")
        health_runner = None
        if os.environ.get("PORT"):
            health_runner = await run_health_server()

        cleanup_task = asyncio.create_task(_cleanup_loop())

        try:
            # Ensure no webhook is registered - a leftover webhook from a previous
            # deploy makes Telegram reject getUpdates with TelegramConflictError.
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot)
        finally:
            cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await cleanup_task
            await bot.session.close()
            if health_runner:
                await health_runner.cleanup()
            await engine.dispose()
            log.info("shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
