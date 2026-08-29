from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from .config import Settings
from .db import Database, iso, utcnow
from .keyboards import kb, main_menu
from .logic import local_to_utc

router = Router(name="dvizh-settings")
DB: Database
SETTINGS: Settings
STATUS_PATH = Path("/var/lib/dvizh/bridge-status.json")
SYNC_SIGNAL_PATH = Path("/var/lib/dvizh/bridge-sync-now")


def configure(db: Database, settings: Settings) -> None:
    global DB, SETTINGS
    DB = db
    SETTINGS = settings


def _authorized_chat(message: Message) -> int | None:
    if message.chat and DB.is_authorized(message.chat.id):
        return message.chat.id
    return None


def _settings_keyboard():
    return kb([
        [("🕒 Москва", "settings:tz:Europe/Moscow"), ("🇸🇪 Стокгольм", "settings:tz:Europe/Stockholm")],
        [("🌙 Тишина 23–09", "settings:quiet:23:00:09:00"), ("🔕 Без тишины", "settings:quiet:00:00:00:00")],
        [("🔄 Синхронизировать", "settings:sync"), ("⬅️ Главное меню", "settings:menu")],
    ])


def _bridge_line() -> str:
    try:
        payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return "Связь с веб-ДВИЖем: ещё не проверена"
    if payload.get("ok"):
        changed = "обновлено" if payload.get("changed") else "без новых изменений"
        return f"Связь с веб-ДВИЖем: ✅ {changed}"
    if payload.get("waiting"):
        return "Связь с веб-ДВИЖем: ⏳ ждёт первого открытия приложения"
    return "Связь с веб-ДВИЖем: ⚠️ временная ошибка"


async def _show_settings(message: Message) -> None:
    chat_id = message.chat.id
    user = DB.get_user(chat_id)
    if not user:
        await message.answer("Сначала привяжи бот.")
        return
    await message.answer(
        "⚙️ <b>Настройки ДВИЖа</b>\n\n"
        f"Часовой пояс: <code>{user['timezone']}</code>\n"
        f"Тихие часы: <code>{user['quiet_start']}–{user['quiet_end']}</code>\n"
        f"{_bridge_line()}\n\n"
        "Можно также написать:\n"
        "<code>/timezone Europe/Moscow</code>\n"
        "<code>/quiet 23:00 09:00</code>",
        parse_mode="HTML",
        reply_markup=_settings_keyboard(),
    )


def _reschedule_pending(chat_id: int, timezone_name: str) -> None:
    with DB.conn() as db:
        rows = db.execute(
            """
            SELECT o.id,o.due_date_local,r.time_local
            FROM occurrences o
            JOIN recurring_tasks r ON r.id=o.recurring_task_id
            WHERE o.chat_id=? AND o.status='pending'
            """,
            (chat_id,),
        ).fetchall()
        for row in rows:
            try:
                local_day = date.fromisoformat(row["due_date_local"])
                scheduled = local_to_utc(local_day, row["time_local"], timezone_name)
            except Exception:
                continue
            db.execute(
                "UPDATE occurrences SET scheduled_at_utc=?,snoozed_until_utc=NULL WHERE id=?",
                (iso(scheduled), int(row["id"])),
            )


def _set_timezone(chat_id: int, timezone_name: str) -> None:
    ZoneInfo(timezone_name)
    with DB.conn() as db:
        db.execute(
            "UPDATE users SET timezone=?,updated_at_utc=? WHERE chat_id=?",
            (timezone_name, iso(utcnow()), chat_id),
        )
    _reschedule_pending(chat_id, timezone_name)
    DB.log_event(chat_id, "timezone_changed", {"timezone": timezone_name})


def _valid_hhmm(value: str) -> bool:
    return bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value))


def _set_quiet(chat_id: int, start: str, end: str) -> None:
    if not _valid_hhmm(start) or not _valid_hhmm(end):
        raise ValueError("invalid quiet hours")
    with DB.conn() as db:
        db.execute(
            "UPDATE users SET quiet_start=?,quiet_end=?,updated_at_utc=? WHERE chat_id=?",
            (start, end, iso(utcnow()), chat_id),
        )
    DB.log_event(chat_id, "quiet_hours_changed", {"start": start, "end": end})


def _request_sync() -> None:
    SYNC_SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNC_SIGNAL_PATH.write_text(datetime.now().isoformat(), encoding="utf-8")


@router.message(Command("settings"))
async def command_settings(message: Message) -> None:
    if _authorized_chat(message) is None:
        await message.answer("Сначала привяжи бот через /start с кодом.")
        return
    await _show_settings(message)


@router.callback_query(F.data == "menu:settings")
async def callback_settings(callback: CallbackQuery) -> None:
    if not callback.message or not DB.is_authorized(callback.message.chat.id):
        await callback.answer("Сначала привяжи бот", show_alert=True)
        return
    await _show_settings(callback.message)
    await callback.answer()


@router.message(Command("timezone"))
async def command_timezone(message: Message, command: CommandObject) -> None:
    chat_id = _authorized_chat(message)
    if chat_id is None:
        await message.answer("Сначала привяжи бот.")
        return
    timezone_name = (command.args or "").strip()
    if not timezone_name:
        await message.answer("Пример: <code>/timezone Europe/Moscow</code>", parse_mode="HTML")
        return
    try:
        _set_timezone(chat_id, timezone_name)
    except Exception:
        await message.answer("Не узнал такой часовой пояс. Пример: <code>Europe/Moscow</code>.", parse_mode="HTML")
        return
    _request_sync()
    await message.answer(f"✅ Часовой пояс: <code>{timezone_name}</code>", parse_mode="HTML")


@router.message(Command("quiet"))
async def command_quiet(message: Message, command: CommandObject) -> None:
    chat_id = _authorized_chat(message)
    if chat_id is None:
        await message.answer("Сначала привяжи бот.")
        return
    parts = (command.args or "").split()
    if len(parts) != 2:
        await message.answer("Пример: <code>/quiet 23:00 09:00</code>. Чтобы отключить: <code>/quiet 00:00 00:00</code>.", parse_mode="HTML")
        return
    try:
        _set_quiet(chat_id, parts[0], parts[1])
    except ValueError:
        await message.answer("Нужен формат HH:MM, например <code>/quiet 23:00 09:00</code>.", parse_mode="HTML")
        return
    await message.answer(f"✅ Тихие часы: <code>{parts[0]}–{parts[1]}</code>", parse_mode="HTML")


@router.message(Command("sync"))
async def command_sync(message: Message) -> None:
    if _authorized_chat(message) is None:
        await message.answer("Сначала привяжи бот.")
        return
    _request_sync()
    await message.answer("🔄 Запросил синхронизацию. Обычно занимает до 20 секунд.")


@router.callback_query(F.data.startswith("settings:tz:"))
async def callback_timezone(callback: CallbackQuery) -> None:
    if not callback.message or not DB.is_authorized(callback.message.chat.id):
        await callback.answer("Сначала привяжи бот", show_alert=True)
        return
    timezone_name = callback.data.split(":", 2)[2]
    try:
        _set_timezone(callback.message.chat.id, timezone_name)
    except Exception:
        await callback.answer("Не удалось применить пояс", show_alert=True)
        return
    _request_sync()
    await callback.message.answer(f"✅ Часовой пояс: <code>{timezone_name}</code>", parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("settings:quiet:"))
async def callback_quiet(callback: CallbackQuery) -> None:
    if not callback.message or not DB.is_authorized(callback.message.chat.id):
        await callback.answer("Сначала привяжи бот", show_alert=True)
        return
    _, _, start, end = callback.data.split(":")
    _set_quiet(callback.message.chat.id, start, end)
    await callback.message.answer(f"✅ Тихие часы: <code>{start}–{end}</code>", parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "settings:sync")
async def callback_sync(callback: CallbackQuery) -> None:
    if not callback.message or not DB.is_authorized(callback.message.chat.id):
        await callback.answer("Сначала привяжи бот", show_alert=True)
        return
    _request_sync()
    await callback.message.answer("🔄 Синхронизация запрошена. Проверю веб-ДВИЖ в течение 20 секунд.")
    await callback.answer()


@router.callback_query(F.data == "settings:menu")
async def callback_menu(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer("Что сейчас нужно?", reply_markup=main_menu())
    await callback.answer()
