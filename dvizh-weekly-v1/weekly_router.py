from __future__ import annotations

import html
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .config import Settings
from .db import Database, utcnow
from .keyboards import kb, main_menu
from .weekly_store import KIND_LABELS, WeeklyStore, describe_weekdays, weekday_mask

router = Router(name="dvizh-weekly")
DB: Database
SETTINGS: Settings
STORE: WeeklyStore


class EventWizard(StatesGroup):
    title = State()
    kind = State()
    recurrence = State()
    once_date = State()
    weekly_days = State()
    weekly_custom_days = State()
    time_local = State()
    duration = State()
    duration_custom = State()
    reminder = State()


def configure(db: Database, settings: Settings, store: WeeklyStore) -> None:
    global DB, SETTINGS, STORE
    DB = db
    SETTINGS = settings
    STORE = store


def esc(value: str) -> str:
    return html.escape(value, quote=False)


def _user_tz(chat_id: int) -> tuple[ZoneInfo, str]:
    user = DB.get_user(chat_id)
    tz_name = str(user["timezone"] if user else SETTINGS.timezone)
    try:
        return ZoneInfo(tz_name), tz_name
    except Exception:
        return ZoneInfo("Europe/Moscow"), "Europe/Moscow"


def _local_today(chat_id: int) -> tuple[date, str]:
    tz, tz_name = _user_tz(chat_id)
    return utcnow().astimezone(tz).date(), tz_name


async def _auth_message(message: Message) -> bool:
    if message.chat and DB.is_authorized(message.chat.id):
        return True
    await message.answer("Сначала привяжи Telegram к ДВИЖу через /start с кодом.")
    return False


async def _auth_callback(callback: CallbackQuery) -> bool:
    if callback.message and DB.is_authorized(callback.message.chat.id):
        return True
    await callback.answer("Сначала привяжи Telegram к ДВИЖу", show_alert=True)
    return False


def _kind_keyboard():
    return kb([
        [("💼 Работа", "week:kind:work"), ("🛋 Отдых", "week:kind:rest")],
        [("🤝 Встреча", "week:kind:friend"), ("📍 Дела", "week:kind:errand")],
        [("📄 Документы", "week:kind:documents"), ("🩺 Здоровье", "week:kind:health")],
        [("🏋️ Зал", "week:kind:gym"), ("🏐 Волейбол", "week:kind:volleyball")],
        [("• Разное", "week:kind:other")],
    ])


def _recurrence_keyboard():
    return kb([[("📌 Один раз", "week:rec:once"), ("🔁 Каждую неделю", "week:rec:weekly")]])


def _weekly_days_keyboard():
    return kb([
        [("Каждый день", "week:days:daily"), ("Будни", "week:days:weekdays")],
        [("ПН СР ПТ", "week:days:mwf"), ("ВТ ЧТ СБ", "week:days:tts")],
        [("Свои дни", "week:days:custom")],
    ])


def _duration_keyboard():
    return kb([
        [("30 мин", "week:duration:30"), ("60 мин", "week:duration:60")],
        [("90 мин", "week:duration:90"), ("120 мин", "week:duration:120")],
        [("Другое", "week:duration:custom")],
    ])


def _reminder_keyboard():
    return kb([
        [("В момент начала", "week:remind:0"), ("За 10 мин", "week:remind:10")],
        [("За 30 мин", "week:remind:30"), ("За 1 час", "week:remind:60")],
        [("За 2 часа", "week:remind:120")],
    ])


def _event_actions(occurrence_id: int):
    return kb([
        [("✅ Готово", f"week:done:{occurrence_id}"), ("— Пропустить", f"week:skip:{occurrence_id}")],
        [("⏰ +10", f"week:snooze:{occurrence_id}:10"), ("+30", f"week:snooze:{occurrence_id}:30")],
    ])


def _parse_local_date(value: str, today: date) -> date | None:
    raw = value.strip().lower()
    if raw in {"сегодня", "today"}:
        return today
    if raw in {"завтра", "tomorrow"}:
        return today + timedelta(days=1)
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m"):
        try:
            parsed = datetime.strptime(raw, fmt)
            if fmt == "%d.%m":
                parsed = parsed.replace(year=today.year)
                candidate = parsed.date()
                if candidate < today:
                    candidate = candidate.replace(year=today.year + 1)
                return candidate
            return parsed.date()
        except ValueError:
            pass
    return None


def _format_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} мин"
    hours, rest = divmod(minutes, 60)
    return f"{hours} ч" if rest == 0 else f"{hours} ч {rest} мин"


async def _send_today(message: Message) -> None:
    chat_id = message.chat.id
    day, tz_name = _local_today(chat_id)
    tz = ZoneInfo(tz_name)

    DB.ensure_occurrences_for_day(chat_id, day, tz_name)
    STORE.expire_before(chat_id, day)
    STORE.ensure_range(chat_id, day, 1, tz_name)

    task_occurrences = DB.list_today_occurrences(chat_id, day)
    schedule_occurrences = STORE.list_occurrences(chat_id, day, 1)

    lines = [f"<b>Сегодня, {day.strftime('%d.%m')}</b>"]
    if schedule_occurrences:
        lines.append("\n<b>🗓 Расписание</b>")
        for occ in schedule_occurrences:
            icon = {"pending": "○", "done": "✅", "skipped": "—"}.get(occ.status, "○")
            start = occ.start_at_utc.astimezone(tz).strftime("%H:%M")
            kind = KIND_LABELS.get(occ.kind, "• Разное")
            lines.append(f"{icon} <code>{start}</code> {kind} · {esc(occ.title)}")
    else:
        lines.append("\n<b>🗓 Расписание</b>\nпока пусто")

    if task_occurrences:
        lines.append("\n<b>🎯 Повторяющиеся задачи</b>")
        for occ in task_occurrences:
            icon = {"done": "✅", "partial": "◐", "skipped": "—", "pending": "○"}.get(occ.status, "○")
            start = occ.scheduled_at_utc.astimezone(tz).strftime("%H:%M")
            lines.append(f"{icon} <code>{start}</code> {esc(occ.title)}")
    else:
        lines.append("\n<b>🎯 Повторяющиеся задачи</b>\nпока нет")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=main_menu())


@router.message(Command("today"))
async def command_today(message: Message) -> None:
    if await _auth_message(message):
        await _send_today(message)


@router.callback_query(F.data == "menu:today")
async def callback_today(callback: CallbackQuery) -> None:
    if not await _auth_callback(callback):
        return
    await _send_today(callback.message)
    await callback.answer()


async def _send_week(message: Message) -> None:
    chat_id = message.chat.id
    today, tz_name = _local_today(chat_id)
    tz = ZoneInfo(tz_name)
    STORE.expire_before(chat_id, today)
    STORE.ensure_range(chat_id, today, 7, tz_name)
    occurrences = STORE.list_occurrences(chat_id, today, 7)
    by_day: dict[str, list[Any]] = {}
    for occurrence in occurrences:
        by_day.setdefault(occurrence.due_date_local, []).append(occurrence)

    lines = ["<b>🗓 Ближайшие 7 дней</b>"]
    day_names = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
    for offset in range(7):
        day = today + timedelta(days=offset)
        rows = by_day.get(day.isoformat(), [])
        heading = "СЕГОДНЯ" if offset == 0 else day_names[day.weekday()]
        lines.append(f"\n<b>{heading} · {day.strftime('%d.%m')}</b>")
        if not rows:
            lines.append("— свободно")
            continue
        for occ in rows:
            icon = {"pending": "○", "done": "✅", "skipped": "—"}.get(occ.status, "○")
            start = occ.start_at_utc.astimezone(tz).strftime("%H:%M")
            kind = KIND_LABELS.get(occ.kind, "• Разное")
            lines.append(f"{icon} <code>{start}</code> {kind} · {esc(occ.title)}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("week"))
async def command_week(message: Message) -> None:
    if await _auth_message(message):
        await _send_week(message)


@router.callback_query(F.data == "menu:week")
async def callback_week(callback: CallbackQuery) -> None:
    if not await _auth_callback(callback):
        return
    await _send_week(callback.message)
    await callback.answer()


@router.message(Command("event"))
async def command_event(message: Message, state: FSMContext) -> None:
    if not await _auth_message(message):
        return
    await state.clear()
    await state.set_state(EventWizard.title)
    await message.answer("Что поставить в расписание?\nНапример: <b>Смена в кафе</b>, <b>Встреча с другом</b> или <b>Зал — верх</b>.", parse_mode="HTML")


@router.callback_query(F.data == "menu:event")
async def callback_event(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _auth_callback(callback):
        return
    await state.clear()
    await state.set_state(EventWizard.title)
    await callback.message.answer("Что поставить в расписание?")
    await callback.answer()


@router.message(EventWizard.title)
async def wizard_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not 2 <= len(title) <= 100:
        await message.answer("Название должно быть от 2 до 100 символов.")
        return
    await state.update_data(title=title)
    await state.set_state(EventWizard.kind)
    await message.answer("Что это за блок?", reply_markup=_kind_keyboard())


@router.callback_query(EventWizard.kind, F.data.startswith("week:kind:"))
async def wizard_kind(callback: CallbackQuery, state: FSMContext) -> None:
    kind = callback.data.rsplit(":", 1)[1]
    if kind not in KIND_LABELS:
        await callback.answer("Неизвестный тип", show_alert=True)
        return
    await state.update_data(kind=kind)
    await state.set_state(EventWizard.recurrence)
    await callback.message.answer("Это разовое событие или повторяется каждую неделю?", reply_markup=_recurrence_keyboard())
    await callback.answer()


@router.callback_query(EventWizard.recurrence, F.data.startswith("week:rec:"))
async def wizard_recurrence(callback: CallbackQuery, state: FSMContext) -> None:
    recurrence = callback.data.rsplit(":", 1)[1]
    await state.update_data(recurrence=recurrence)
    if recurrence == "once":
        await state.set_state(EventWizard.once_date)
        await callback.message.answer("Дата? Можно написать <code>сегодня</code>, <code>завтра</code>, <code>31.08</code> или <code>31.08.2026</code>.", parse_mode="HTML")
    elif recurrence == "weekly":
        await state.set_state(EventWizard.weekly_days)
        await callback.message.answer("В какие дни недели?", reply_markup=_weekly_days_keyboard())
    else:
        await callback.answer("Неизвестный вариант", show_alert=True)
        return
    await callback.answer()


@router.message(EventWizard.once_date)
async def wizard_once_date(message: Message, state: FSMContext) -> None:
    today, _ = _local_today(message.chat.id)
    chosen = _parse_local_date(message.text or "", today)
    if chosen is None or chosen < today:
        await message.answer("Не понял дату или она уже прошла. Пример: <code>завтра</code> или <code>31.08</code>.", parse_mode="HTML")
        return
    await state.update_data(date_local=chosen.isoformat())
    await state.set_state(EventWizard.time_local)
    await message.answer("Во сколько начало? Например <code>18:30</code>.", parse_mode="HTML")


@router.callback_query(EventWizard.weekly_days, F.data.startswith("week:days:"))
async def wizard_weekly_days(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.rsplit(":", 1)[1]
    masks = {
        "daily": weekday_mask(set(range(7))),
        "weekdays": weekday_mask({0, 1, 2, 3, 4}),
        "mwf": weekday_mask({0, 2, 4}),
        "tts": weekday_mask({1, 3, 5}),
    }
    if mode == "custom":
        await state.set_state(EventWizard.weekly_custom_days)
        await callback.message.answer("Напиши дни через пробел: <code>пн ср пт</code>.", parse_mode="HTML")
        await callback.answer()
        return
    if mode not in masks:
        await callback.answer("Неизвестный вариант", show_alert=True)
        return
    await state.update_data(weekdays_mask=masks[mode])
    await state.set_state(EventWizard.time_local)
    await callback.message.answer("Во сколько начало? Например <code>18:30</code>.", parse_mode="HTML")
    await callback.answer()


@router.message(EventWizard.weekly_custom_days)
async def wizard_custom_days(message: Message, state: FSMContext) -> None:
    mapping = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}
    tokens = re.findall(r"[а-яё]+", (message.text or "").lower())
    days = {mapping[token] for token in tokens if token in mapping}
    if not days:
        await message.answer("Не понял дни. Пример: <code>пн ср пт</code>.", parse_mode="HTML")
        return
    await state.update_data(weekdays_mask=weekday_mask(days))
    await state.set_state(EventWizard.time_local)
    await message.answer("Во сколько начало? Например <code>18:30</code>.", parse_mode="HTML")


@router.message(EventWizard.time_local)
async def wizard_time(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        await message.answer("Нужен формат HH:MM, например <code>09:30</code>.", parse_mode="HTML")
        return
    await state.update_data(start_local=value)
    await state.set_state(EventWizard.duration)
    await message.answer("Сколько длится?", reply_markup=_duration_keyboard())


@router.callback_query(EventWizard.duration, F.data.startswith("week:duration:"))
async def wizard_duration(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.rsplit(":", 1)[1]
    if value == "custom":
        await state.set_state(EventWizard.duration_custom)
        await callback.message.answer("Сколько минут? От 5 до 720.")
        await callback.answer()
        return
    minutes = int(value)
    await state.update_data(duration_minutes=minutes)
    await state.set_state(EventWizard.reminder)
    await callback.message.answer("Когда напомнить?", reply_markup=_reminder_keyboard())
    await callback.answer()


@router.message(EventWizard.duration_custom)
async def wizard_duration_custom(message: Message, state: FSMContext) -> None:
    try:
        minutes = int((message.text or "").strip())
    except ValueError:
        minutes = -1
    if not 5 <= minutes <= 720:
        await message.answer("Нужно число от 5 до 720 минут.")
        return
    await state.update_data(duration_minutes=minutes)
    await state.set_state(EventWizard.reminder)
    await message.answer("Когда напомнить?", reply_markup=_reminder_keyboard())


@router.callback_query(EventWizard.reminder, F.data.startswith("week:remind:"))
async def wizard_reminder(callback: CallbackQuery, state: FSMContext) -> None:
    reminder = int(callback.data.rsplit(":", 1)[1])
    data: dict[str, Any] = await state.get_data()
    chat_id = callback.message.chat.id
    recurrence = data["recurrence"]
    if recurrence == "once":
        item_id = STORE.add_once(
            chat_id=chat_id,
            title=data["title"],
            kind=data["kind"],
            date_local=date.fromisoformat(data["date_local"]),
            start_local=data["start_local"],
            duration_minutes=int(data["duration_minutes"]),
            reminder_minutes=reminder,
        )
        recurrence_text = date.fromisoformat(data["date_local"]).strftime("%d.%m.%Y")
    else:
        item_id = STORE.add_weekly(
            chat_id=chat_id,
            title=data["title"],
            kind=data["kind"],
            weekdays_mask=int(data["weekdays_mask"]),
            start_local=data["start_local"],
            duration_minutes=int(data["duration_minutes"]),
            reminder_minutes=reminder,
        )
        recurrence_text = describe_weekdays(int(data["weekdays_mask"]))

    today, tz_name = _local_today(chat_id)
    STORE.ensure_range(chat_id, today, 7, tz_name)
    await state.clear()
    await callback.message.answer(
        f"✅ Добавил в расписание #{item_id}.\n"
        f"<b>{esc(data['title'])}</b> · {KIND_LABELS[data['kind']]}\n"
        f"{recurrence_text} · <code>{data['start_local']}</code> · {_format_duration(int(data['duration_minutes']))}\n"
        f"Напоминание: {'в момент начала' if reminder == 0 else f'за {reminder} мин'}",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
    await callback.answer()


async def _send_schedule(message: Message) -> None:
    items = STORE.list_items(message.chat.id)
    if not items:
        await message.answer("Расписание пока пустое. Добавь первый блок через /event.")
        return
    lines = ["<b>🗂 Моё расписание</b>"]
    for item in items:
        state = "●" if item.enabled else "○"
        kind = KIND_LABELS.get(item.kind, "• Разное")
        recurrence = (
            date.fromisoformat(item.date_local).strftime("%d.%m.%Y")
            if item.recurrence == "once" and item.date_local
            else describe_weekdays(item.weekdays_mask or 0)
        )
        lines.append(
            f"{state} <b>#{item.id}</b> {kind} · {esc(item.title)}\n"
            f"   {recurrence}, <code>{item.start_local}</code>, {_format_duration(item.duration_minutes)}"
        )
    lines.append("\nПауза: <code>/caloff ID</code> · вернуть: <code>/calon ID</code> · удалить: <code>/caldel ID</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("schedule"))
async def command_schedule(message: Message) -> None:
    if await _auth_message(message):
        await _send_schedule(message)


@router.callback_query(F.data == "menu:schedule")
async def callback_schedule(callback: CallbackQuery) -> None:
    if not await _auth_callback(callback):
        return
    await _send_schedule(callback.message)
    await callback.answer()


async def _item_switch(message: Message, command: CommandObject, enabled: bool) -> None:
    if not await _auth_message(message):
        return
    try:
        item_id = int((command.args or "").strip())
    except ValueError:
        await message.answer("Укажи ID, например <code>/caloff 2</code>.", parse_mode="HTML")
        return
    if not STORE.set_item_enabled(message.chat.id, item_id, enabled):
        await message.answer("Не нашёл такой блок расписания.")
        return
    await message.answer("Включено." if enabled else "Поставил этот блок на паузу.")


@router.message(Command("caloff"))
async def command_caloff(message: Message, command: CommandObject) -> None:
    await _item_switch(message, command, False)


@router.message(Command("calon"))
async def command_calon(message: Message, command: CommandObject) -> None:
    await _item_switch(message, command, True)


@router.message(Command("caldel"))
async def command_caldel(message: Message, command: CommandObject) -> None:
    if not await _auth_message(message):
        return
    try:
        item_id = int((command.args or "").strip())
    except ValueError:
        await message.answer("Укажи ID, например <code>/caldel 2</code>.", parse_mode="HTML")
        return
    if STORE.delete_item(message.chat.id, item_id):
        await message.answer("Удалил блок расписания.")
    else:
        await message.answer("Не нашёл такой блок.")


@router.callback_query(F.data.startswith("week:done:"))
async def callback_done(callback: CallbackQuery) -> None:
    if not await _auth_callback(callback):
        return
    occurrence_id = int(callback.data.rsplit(":", 1)[1])
    if STORE.set_occurrence_status(callback.message.chat.id, occurrence_id, "done"):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Отметил. Следующий повтор останется на своём месте.")
    await callback.answer()


@router.callback_query(F.data.startswith("week:skip:"))
async def callback_skip(callback: CallbackQuery) -> None:
    if not await _auth_callback(callback):
        return
    occurrence_id = int(callback.data.rsplit(":", 1)[1])
    if STORE.set_occurrence_status(callback.message.chat.id, occurrence_id, "skipped"):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("— Пропустил только этот раз. Никакого хвоста просроченных событий.")
    await callback.answer()


@router.callback_query(F.data.startswith("week:snooze:"))
async def callback_snooze(callback: CallbackQuery) -> None:
    if not await _auth_callback(callback):
        return
    _, _, occurrence_raw, minutes_raw = callback.data.split(":")
    STORE.snooze(callback.message.chat.id, int(occurrence_raw), int(minutes_raw))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"⏰ Напомню ещё раз через {minutes_raw} минут.")
    await callback.answer()


@router.message(Command("cancel"))
async def command_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменил текущий ввод.", reply_markup=main_menu())


async def send_event_reminder(bot, occurrence) -> None:
    tz, _ = _user_tz(occurrence.chat_id)
    local_start = occurrence.start_at_utc.astimezone(tz).strftime("%H:%M")
    kind = KIND_LABELS.get(occurrence.kind, "• Разное")
    before = occurrence.reminder_minutes
    prefix = "Сейчас начинается" if before == 0 else f"Через {before} мин"
    duration = int((occurrence.end_at_utc - occurrence.start_at_utc).total_seconds() // 60)
    await bot.send_message(
        occurrence.chat_id,
        f"⏰ <b>{prefix}: {esc(occurrence.title)}</b>\n"
        f"{kind} · <code>{local_start}</code> · {_format_duration(duration)}\n\n"
        "Это блок расписания, не ещё один долг. Если планы поменялись — можно пропустить только этот раз.",
        parse_mode="HTML",
        reply_markup=_event_actions(occurrence.id),
    )
