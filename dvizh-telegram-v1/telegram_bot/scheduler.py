from __future__ import annotations

import asyncio
import logging
from zoneinfo import ZoneInfo

from aiogram import Bot

from .bot import send_smart_occurrence
from .config import Settings
from .db import Database, utcnow
from .keyboards import energy_keyboard, focus_result_keyboard, reminder_keyboard
from .logic import checkin_is_fresh, is_quiet, smart_decision

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, bot: Bot, db: Database, settings: Settings):
        self.bot = bot
        self.db = db
        self.settings = settings
        self._stop = asyncio.Event()

    async def run(self) -> None:
        log.info("scheduler started: tick=%ss", self.settings.scheduler_tick_seconds)
        while not self._stop.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.scheduler_tick_seconds)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()

    async def tick(self) -> None:
        now = utcnow()
        for user in self.db.list_authorized_users():
            chat_id = int(user["chat_id"])
            tz_name = user["timezone"]
            local_day = now.astimezone(ZoneInfo(tz_name)).date()
            self.db.ensure_occurrences_for_day(chat_id, local_day, tz_name)

            if is_quiet(now, tz_name, user["quiet_start"], user["quiet_end"]):
                continue

            due = self.db.pending_due_occurrences(chat_id, now)
            unsent = [occ for occ in due if occ.reminder_sent_at_utc is None]
            if unsent:
                occurrence = unsent[0]
                checkin = self.db.latest_checkin(chat_id)
                if not checkin_is_fresh(checkin, now, self.settings.checkin_fresh_minutes):
                    if user["pending_occurrence_id"] is not None:
                        continue
                    self.db.set_pending_occurrence(chat_id, occurrence.id)
                    self.db.start_checkin_draft(chat_id)
                    await self.bot.send_message(
                        chat_id,
                        f"⏰ По времени: <b>{occurrence.title}</b>\n\nПеред решением — 15 секунд. Сколько сейчас заряда?",
                        parse_mode="HTML",
                        reply_markup=energy_keyboard(),
                    )
                    continue
                await send_smart_occurrence(self.bot, occurrence, checkin)
                continue

            followups = self.db.overdue_followups(chat_id, now, self.settings.followup_minutes)
            if followups:
                occurrence = followups[0]
                checkin = self.db.latest_checkin(chat_id)
                decision = smart_decision(
                    title=occurrence.title,
                    microstep=occurrence.microstep,
                    area=occurrence.area,
                    min_minutes=occurrence.min_minutes,
                    normal_minutes=occurrence.normal_minutes,
                    energy_cost=occurrence.energy_cost,
                    checkin=checkin,
                )
                await self.bot.send_message(
                    chat_id,
                    f"Ещё один пинг и дальше не трогаю.\n\n<b>{occurrence.title}</b> → {decision.action}",
                    parse_mode="HTML",
                    reply_markup=reminder_keyboard(occurrence.id, decision.minutes),
                )
                self.db.mark_followup_sent(occurrence.id, now)

        for session in self.db.focus_sessions_due_for_prompt(now):
            chat_id = int(session["chat_id"])
            user = self.db.get_user(chat_id)
            if not user:
                continue
            if is_quiet(now, user["timezone"], user["quiet_start"], user["quiet_end"]):
                continue
            await self.bot.send_message(
                chat_id,
                f"⏱ Раунд на {int(session['planned_minutes'])} мин закончился. Что получилось?",
                reply_markup=focus_result_keyboard(int(session["id"])),
            )
            self.db.mark_focus_prompt_sent(int(session["id"]))
