from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from aiogram import Bot

from .config import Settings
from .db import Database, utcnow
from .logic import is_quiet
from .weekly_router import send_event_reminder
from .weekly_store import WeeklyStore

LOG = logging.getLogger("dvizh.weekly.scheduler")


class WeeklyScheduler:
    def __init__(self, bot: Bot, db: Database, store: WeeklyStore, settings: Settings):
        self.bot = bot
        self.db = db
        self.store = store
        self.settings = settings
        self._stop = asyncio.Event()
        self.tick_seconds = max(10, min(60, int(settings.scheduler_tick_seconds)))

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        LOG.info("weekly scheduler started; tick=%ss", self.tick_seconds)
        while not self._stop.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("weekly scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick_seconds)
            except asyncio.TimeoutError:
                pass
        LOG.info("weekly scheduler stopped")

    async def tick(self) -> None:
        now = utcnow()
        for user in self.db.list_authorized_users():
            chat_id = int(user["chat_id"])
            timezone = str(user["timezone"] or self.settings.timezone)
            quiet_start = str(user["quiet_start"] or self.settings.quiet_start)
            quiet_end = str(user["quiet_end"] or self.settings.quiet_end)
            try:
                tz = ZoneInfo(timezone)
            except Exception:
                timezone = self.settings.timezone
                tz = ZoneInfo(timezone)

            local_today = now.astimezone(tz).date()
            self.store.expire_before(chat_id, local_today)
            self.store.ensure_range(chat_id, local_today, 8, timezone)

            if is_quiet(now, timezone, quiet_start, quiet_end):
                continue

            for occurrence in self.store.due_for_reminder(chat_id, now):
                if occurrence.end_at_utc < now:
                    self.store.set_occurrence_status(chat_id, occurrence.id, "skipped")
                    continue
                try:
                    await send_event_reminder(self.bot, occurrence)
                except Exception:
                    LOG.exception("failed to send schedule reminder chat=%s occurrence=%s", chat_id, occurrence.id)
                    continue
                self.store.mark_reminder_sent(chat_id, occurrence.id)
                try:
                    self.db.log_event(
                        chat_id,
                        "schedule_reminder_sent",
                        {"schedule_occurrence_id": occurrence.id, "schedule_item_id": occurrence.schedule_item_id},
                    )
                except Exception:
                    LOG.exception("failed to log schedule reminder")
