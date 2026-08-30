from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from .config import Settings
from .db import Database, utcnow
from .keyboards import kb
from .logic import is_quiet
from .training_store import TrainingStore

LOG = logging.getLogger("dvizh.training.scheduler")
STATUS_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


class TrainingScheduler:
    def __init__(self, bot: Bot, db: Database, store: TrainingStore, settings: Settings):
        self.bot = bot
        self.db = db
        self.store = store
        self.settings = settings
        self._stop = asyncio.Event()
        self.tick_seconds = max(20, min(60, int(settings.scheduler_tick_seconds)))

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        LOG.info("training scheduler started; tick=%ss", self.tick_seconds)
        while not self._stop.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("training scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick_seconds)
            except asyncio.TimeoutError:
                pass
        LOG.info("training scheduler stopped")

    async def tick(self) -> None:
        now = utcnow()
        for user in self.db.list_authorized_users():
            chat_id = int(user["chat_id"])
            timezone_name = str(user["timezone"] or self.settings.timezone)
            quiet_start = str(user["quiet_start"] or self.settings.quiet_start)
            quiet_end = str(user["quiet_end"] or self.settings.quiet_end)
            try:
                tz = ZoneInfo(timezone_name)
            except Exception:
                timezone_name = self.settings.timezone
                tz = ZoneInfo(timezone_name)
            if is_quiet(now, timezone_name, quiet_start, quiet_end):
                continue

            local_now = now.astimezone(tz)
            today = local_now.date()
            self.store.sync_slots_from_schedule(chat_id)
            upcoming = [row for row in self.store.upcoming_training(chat_id, today, 1) if row["status"] == "pending"]
            if not upcoming:
                continue

            readiness = self.store.readiness_for_day(chat_id, today)
            prompt_key = f"readiness-prompt:{today.isoformat()}"
            prompt_at = datetime.combine(today, time(10, 0), tzinfo=tz)
            first_start = min(datetime.fromisoformat(row["startAt"]).astimezone(tz) for row in upcoming)
            if first_start - timedelta(hours=3) < prompt_at:
                prompt_at = max(datetime.combine(today, time(8, 0), tzinfo=tz), first_start - timedelta(hours=3))
            if not readiness and local_now >= prompt_at and not self.store.notification_sent(chat_id, prompt_key):
                try:
                    await self.bot.send_message(
                        chat_id,
                        "🧠 Сегодня есть тренировка или волейбол. Пройди минутную готовность — ДВИЖ скажет, давить, облегчить или восстановиться.",
                        reply_markup=kb([[('🧠 Пройти готовность', 'training:ready')], [('🏋️ Открыть тренировки', 'menu:training')]]),
                    )
                    self.store.mark_notification(chat_id, prompt_key)
                except Exception:
                    LOG.exception("failed readiness prompt chat=%s", chat_id)

            for event in upcoming:
                start = datetime.fromisoformat(event["startAt"]).astimezone(tz)
                delta = start - local_now
                if delta < timedelta(minutes=-5) or delta > timedelta(minutes=95):
                    continue
                event_key = f"pre-event:{event['occurrenceId']}"
                if self.store.notification_sent(chat_id, event_key):
                    continue
                try:
                    if not readiness:
                        text = f"⏳ Скоро: <b>{event['title']}</b>. Готовность ещё не отмечена — лучше проверить до начала."
                        markup = kb([[('🧠 Проверить готовность', 'training:ready')]])
                    else:
                        result = readiness["result"]
                        icon = STATUS_ICON.get(str(result.get("status")), "🟡")
                        if event["kind"] == "volleyball":
                            recommendation = str(result.get("volleyball_text") or "Проверь самочувствие.")
                        else:
                            recommendation = str(result.get("strength_text") or "Проверь самочувствие.")
                        text = (
                            f"{icon} Скоро: <b>{event['title']}</b>\n"
                            f"Готовность {int(result.get('score') or 0)}/100. {recommendation}\n"
                            f"Потолок сегодня: <b>RPE {int(result.get('rpe_cap') or 0)}/10</b>."
                        )
                        markup = kb([[('🏋️ Дашборд', 'menu:training'), ('🧠 Обновить', 'training:ready')]])
                    await self.bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
                    self.store.mark_notification(chat_id, event_key)
                except Exception:
                    LOG.exception("failed pre-event advice chat=%s occurrence=%s", chat_id, event["occurrenceId"])
