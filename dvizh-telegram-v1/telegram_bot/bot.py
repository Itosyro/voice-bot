from __future__ import annotations

import html
import re
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .config import Settings
from .db import Database, Occurrence, utcnow
from .keyboards import (
    body_keyboard,
    energy_keyboard,
    main_menu,
    reminder_keyboard,
    rescue_keyboard,
    rescue_start_keyboard,
    stress_keyboard,
)
from .logic import AREA_LABELS, BODY_LABELS, ENERGY_LABELS, STRESS_LABELS, describe_weekdays, smart_decision, weekday_mask

router = Router(name="dvizh")


class RepeatWizard(StatesGroup):
    title = State()
    microstep = State()
    area = State()
    days = State()
    custom_days = State()
    time_local = State()
    min_minutes = State()
    normal_minutes = State()
    energy_cost = State()


DB: Database
SETTINGS: Settings


def configure(db: Database, settings: Settings) -> None:
    global DB, SETTINGS
    DB = db
    SETTINGS = settings


def esc(value: str) -> str:
    return html.escape(value, quote=False)


def _local_day(chat_id: int):
    user = DB.get_user(chat_id)
    tz_name = user["timezone"] if user else SETTINGS.timezone
    tz = ZoneInfo(tz_name)
    return utcnow().astimezone(tz).date(), tz_name


async def ensure_auth(message: Message) -> bool:
    if message.chat and DB.is_authorized(message.chat.id):
        return True
    await message.answer("Этот бот привязывается к ДВИЖу по одноразовому коду. Открой /start с кодом привязки.")
    return False


async def ensure_cb_auth(callback: CallbackQuery) -> bool:
    if callback.message and DB.is_authorized(callback.message.chat.id):
        return True
    await callback.answer("Сначала привяжи бот через /start <код>", show_alert=True)
    return False


@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject) -> None:
    if not message.chat or not message.from_user:
        return
    chat_id = message.chat.id
    already = DB.is_authorized(chat_id)
    code = (command.args or "").strip()

    if already:
        await message.answer("ДВИЖ на связи. Что делаем?", reply_markup=main_menu())
        return

    if code != SETTINGS.pair_code:
        await message.answer(
            "Нужен код привязки. После установки он будет показан один раз.\n\n"
            "Формат: <code>/start КОД</code>",
            parse_mode="HTML",
        )
        return

    if not SETTINGS.allow_multi_user and DB.authorized_count() > 0:
        await message.answer("Этот экземпляр ДВИЖа уже привязан к другому Telegram-чату.")
        return

    DB.upsert_user(
        chat_id=chat_id,
        telegram_user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        timezone=SETTINGS.timezone,
        quiet_start=SETTINGS.quiet_start,
        quiet_end=SETTINGS.quiet_end,
        authorized=True,
    )
    DB.log_event(chat_id, "telegram_paired")
    await message.answer(
        "Готово. Этот чат теперь привязан к ДВИЖу.\n\n"
        "Я не буду спамить: один основной пинок по времени, максимум один follow-up, затем тишина.\n"
        "Если залип — просто напиши <b>залип</b>.",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    if await ensure_auth(message):
        await message.answer("Что сейчас нужно?", reply_markup=main_menu())


@router.message(Command("checkin"))
async def cmd_checkin(message: Message) -> None:
    if await ensure_auth(message):
        DB.start_checkin_draft(message.chat.id)
        await message.answer("⚡ Сколько сейчас заряда?", reply_markup=energy_keyboard())


@router.callback_query(F.data == "menu:checkin")
async def cb_checkin(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    chat_id = callback.message.chat.id
    DB.start_checkin_draft(chat_id)
    await callback.message.answer("⚡ Сколько сейчас заряда?", reply_markup=energy_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("ci:e:"))
async def cb_energy(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    value = int(callback.data.rsplit(":", 1)[1])
    DB.update_checkin_draft(callback.message.chat.id, "energy", value)
    await callback.message.edit_text(f"⚡ Заряд: <b>{ENERGY_LABELS[value]}</b>\n\n🧍 Что с телом?", parse_mode="HTML", reply_markup=body_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("ci:b:"))
async def cb_body(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    value = int(callback.data.rsplit(":", 1)[1])
    DB.update_checkin_draft(callback.message.chat.id, "body", value)
    await callback.message.edit_text(f"🧍 Тело: <b>{BODY_LABELS[value]}</b>\n\n🧠 Что внутри?", parse_mode="HTML", reply_markup=stress_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("ci:s:"))
async def cb_stress(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    chat_id = callback.message.chat.id
    value = int(callback.data.rsplit(":", 1)[1])
    DB.update_checkin_draft(chat_id, "stress", value)
    checkin = DB.finish_checkin(chat_id)
    await callback.message.edit_text(
        f"Чек-ин сохранён: ⚡ {ENERGY_LABELS[checkin.energy]} · 🧍 {BODY_LABELS[checkin.body]} · 🧠 {STRESS_LABELS[checkin.stress]}"
    )
    user = DB.get_user(chat_id)
    pending_id = int(user["pending_occurrence_id"]) if user and user["pending_occurrence_id"] else None
    if pending_id:
        DB.set_pending_occurrence(chat_id, None)
        occurrence = DB.get_occurrence(pending_id, chat_id)
        if occurrence and occurrence.status == "pending":
            await send_smart_occurrence(callback.bot, occurrence, checkin)
    await callback.answer()


async def send_smart_occurrence(bot: Bot, occurrence: Occurrence, checkin=None) -> None:
    if checkin is None:
        checkin = DB.latest_checkin(occurrence.chat_id)
    decision = smart_decision(
        title=occurrence.title,
        microstep=occurrence.microstep,
        area=occurrence.area,
        min_minutes=occurrence.min_minutes,
        normal_minutes=occurrence.normal_minutes,
        energy_cost=occurrence.energy_cost,
        checkin=checkin,
    )
    caution = f"\n\n<i>{esc(decision.caution)}</i>" if decision.caution else ""
    text = (
        f"⏰ <b>{esc(occurrence.title)}</b>\n"
        f"{esc(decision.headline)}\n\n"
        f"Сейчас: <b>{esc(decision.action)}</b>\n"
        f"Ставка: <b>{decision.minutes} мин</b>{caution}"
    )
    await bot.send_message(occurrence.chat_id, text, parse_mode="HTML", reply_markup=reminder_keyboard(occurrence.id, decision.minutes))
    DB.mark_reminder_sent(occurrence.id)
    DB.log_event(occurrence.chat_id, "smart_reminder_sent", {"occurrence_id": occurrence.id, "mode": decision.mode, "minutes": decision.minutes})


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    if not await ensure_auth(message):
        return
    await send_today(message)


@router.callback_query(F.data == "menu:today")
async def cb_today(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    await send_today(callback.message)
    await callback.answer()


async def send_today(message: Message) -> None:
    chat_id = message.chat.id
    day, tz_name = _local_day(chat_id)
    DB.ensure_occurrences_for_day(chat_id, day, tz_name)
    occurrences = DB.list_today_occurrences(chat_id, day)
    if not occurrences:
        await message.answer("На сегодня повторяющихся задач пока нет. Это не пустой день — просто расписание ещё не задано.", reply_markup=main_menu())
        return
    lines = [f"<b>Сегодня, {day.strftime('%d.%m')}</b>"]
    tz = ZoneInfo(tz_name)
    for occ in occurrences:
        local_time = occ.scheduled_at_utc.astimezone(tz).strftime("%H:%M")
        icon = {"done": "✅", "partial": "◐", "skipped": "—", "pending": "○"}.get(occ.status, "○")
        lines.append(f"{icon} <code>{local_time}</code>  {esc(occ.title)}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("repeat"))
async def cmd_repeat(message: Message, state: FSMContext) -> None:
    if not await ensure_auth(message):
        return
    await state.clear()
    await state.set_state(RepeatWizard.title)
    await message.answer("Название повторяющейся задачи?\nНапример: <b>10 вопросов ПДД</b>", parse_mode="HTML")


@router.callback_query(F.data == "menu:repeat")
async def cb_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    if not await ensure_cb_auth(callback):
        return
    await state.clear()
    await state.set_state(RepeatWizard.title)
    await callback.message.answer("Название повторяющейся задачи?")
    await callback.answer()


@router.message(RepeatWizard.title)
async def repeat_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer("Напиши короткое, но понятное действие.")
        return
    await state.update_data(title=title)
    await state.set_state(RepeatWizard.microstep)
    await message.answer("Микрошаг на плохой день?\nНапример: <b>открыть билет и сделать 3 вопроса</b>.\nЕсли не нужен — отправь <code>-</code>.", parse_mode="HTML")


@router.message(RepeatWizard.microstep)
async def repeat_micro(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    await state.update_data(microstep=None if value == "-" else value)
    await state.set_state(RepeatWizard.area)
    from .keyboards import kb
    await message.answer("К какой сфере относится?", reply_markup=kb([
        [("🚦 ПДД", "wiz:area:pdd"), ("🍔 Кафе", "wiz:area:cafe")],
        [("🏐 Волейбол", "wiz:area:volleyball"), ("📱 Соцсети", "wiz:area:social")],
        [("🧘 Восстановление", "wiz:area:recovery"), ("• Разное", "wiz:area:other")],
    ]))


@router.callback_query(RepeatWizard.area, F.data.startswith("wiz:area:"))
async def repeat_area(callback: CallbackQuery, state: FSMContext) -> None:
    area = callback.data.rsplit(":", 1)[1]
    if area not in AREA_LABELS:
        await callback.answer("Неизвестная сфера", show_alert=True)
        return
    await state.update_data(area=area)
    await state.set_state(RepeatWizard.days)
    from .keyboards import kb
    await callback.message.answer("В какие дни?", reply_markup=kb([
        [("Каждый день", "wiz:days:daily"), ("Будни", "wiz:days:weekdays")],
        [("ПН СР ПТ", "wiz:days:mwf"), ("ВТ ЧТ СБ", "wiz:days:tts")],
        [("Свои дни", "wiz:days:custom")],
    ]))
    await callback.answer()


@router.callback_query(RepeatWizard.days, F.data.startswith("wiz:days:"))
async def repeat_days(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.rsplit(":", 1)[1]
    modes = {
        "daily": weekday_mask(set(range(7))),
        "weekdays": weekday_mask({0, 1, 2, 3, 4}),
        "mwf": weekday_mask({0, 2, 4}),
        "tts": weekday_mask({1, 3, 5}),
    }
    if mode == "custom":
        await state.set_state(RepeatWizard.custom_days)
        await callback.message.answer("Напиши дни через пробел: <code>пн ср пт</code>", parse_mode="HTML")
        await callback.answer()
        return
    if mode not in modes:
        await callback.answer("Неизвестный вариант", show_alert=True)
        return
    await state.update_data(weekdays_mask=modes[mode])
    await state.set_state(RepeatWizard.time_local)
    await callback.message.answer("Во сколько напоминать? Формат <code>HH:MM</code>, например <code>10:30</code>.", parse_mode="HTML")
    await callback.answer()


@router.message(RepeatWizard.custom_days)
async def repeat_custom_days(message: Message, state: FSMContext) -> None:
    mapping = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}
    tokens = re.findall(r"[а-яё]+", (message.text or "").lower())
    days = {mapping[token] for token in tokens if token in mapping}
    if not days:
        await message.answer("Не понял дни. Пример: <code>пн ср пт</code>", parse_mode="HTML")
        return
    await state.update_data(weekdays_mask=weekday_mask(days))
    await state.set_state(RepeatWizard.time_local)
    await message.answer("Во сколько напоминать? Например <code>18:30</code>.", parse_mode="HTML")


@router.message(RepeatWizard.time_local)
async def repeat_time(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        await message.answer("Нужен формат HH:MM, например 09:30 или 18:05.")
        return
    await state.update_data(time_local=value)
    await state.set_state(RepeatWizard.min_minutes)
    await message.answer("Минимум на плохой день — сколько минут? Обычно <b>2–5</b>.", parse_mode="HTML")


@router.message(RepeatWizard.min_minutes)
async def repeat_min(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip())
    except ValueError:
        value = -1
    if not 2 <= value <= 15:
        await message.answer("Выбери от 2 до 15 минут.")
        return
    await state.update_data(min_minutes=value)
    await state.set_state(RepeatWizard.normal_minutes)
    await message.answer("А нормальный раунд? От 5 до 60 минут.")


@router.message(RepeatWizard.normal_minutes)
async def repeat_normal(message: Message, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip())
    except ValueError:
        value = -1
    if not 5 <= value <= 60:
        await message.answer("Выбери от 5 до 60 минут.")
        return
    await state.update_data(normal_minutes=value)
    await state.set_state(RepeatWizard.energy_cost)
    from .keyboards import kb
    await message.answer("Сколько энергии обычно требует?", reply_markup=kb([[("Низко", "wiz:energy:0"), ("Средне", "wiz:energy:1"), ("Высоко", "wiz:energy:2")]]))


@router.callback_query(RepeatWizard.energy_cost, F.data.startswith("wiz:energy:"))
async def repeat_energy(callback: CallbackQuery, state: FSMContext) -> None:
    energy_cost = int(callback.data.rsplit(":", 1)[1])
    data: dict[str, Any] = await state.get_data()
    task_id = DB.add_recurring_task(
        chat_id=callback.message.chat.id,
        title=data["title"],
        microstep=data.get("microstep"),
        area=data["area"],
        weekdays_mask=int(data["weekdays_mask"]),
        time_local=data["time_local"],
        min_minutes=int(data["min_minutes"]),
        normal_minutes=int(data["normal_minutes"]),
        energy_cost=energy_cost,
    )
    day, tz_name = _local_day(callback.message.chat.id)
    DB.ensure_occurrences_for_day(callback.message.chat.id, day, tz_name)
    await state.clear()
    await callback.message.answer(
        f"✅ Повтор #{task_id} создан.\n<b>{esc(data['title'])}</b> · {describe_weekdays(int(data['weekdays_mask']))} · {data['time_local']}",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
    await callback.answer()


@router.message(Command("repeats"))
async def cmd_repeats(message: Message) -> None:
    if await ensure_auth(message):
        await send_repeats(message)


@router.callback_query(F.data == "menu:repeats")
async def cb_repeats(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    await send_repeats(callback.message)
    await callback.answer()


async def send_repeats(message: Message) -> None:
    tasks = DB.list_recurring_tasks(message.chat.id)
    if not tasks:
        await message.answer("Повторов пока нет. Создай первый через /repeat.")
        return
    lines = ["<b>Повторяющиеся задачи</b>"]
    for task in tasks:
        state = "●" if task.enabled else "○"
        lines.append(f"{state} <b>#{task.id}</b> {esc(task.title)} — {describe_weekdays(task.weekdays_mask)}, <code>{task.time_local}</code>")
    lines.append("\nОтключить: <code>/off ID</code> · включить: <code>/on ID</code> · удалить: <code>/del ID</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")


async def _task_switch(message: Message, enabled: bool, command: CommandObject) -> None:
    if not await ensure_auth(message):
        return
    try:
        task_id = int((command.args or "").strip())
    except ValueError:
        await message.answer("Укажи ID задачи, например /off 3")
        return
    DB.set_task_enabled(message.chat.id, task_id, enabled)
    await message.answer("Включено." if enabled else "Пауза. Новые напоминания по этому повтору не создаются.")


@router.message(Command("off"))
async def cmd_off(message: Message, command: CommandObject) -> None:
    await _task_switch(message, False, command)


@router.message(Command("on"))
async def cmd_on(message: Message, command: CommandObject) -> None:
    await _task_switch(message, True, command)


@router.message(Command("del"))
async def cmd_del(message: Message, command: CommandObject) -> None:
    if not await ensure_auth(message):
        return
    try:
        task_id = int((command.args or "").strip())
    except ValueError:
        await message.answer("Укажи ID задачи, например /del 3")
        return
    DB.delete_task(message.chat.id, task_id)
    await message.answer("Удалено.")


@router.callback_query(F.data.startswith("occ:done:"))
async def cb_occ_done(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    occurrence_id = int(callback.data.split(":")[2])
    DB.set_occurrence_status(occurrence_id, callback.message.chat.id, "done")
    DB.log_event(callback.message.chat.id, "occurrence_done", {"occurrence_id": occurrence_id})
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("✅ Засчитано. Не надо добивать день сверху.")
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("occ:partial:"))
async def cb_occ_partial(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    occurrence_id = int(callback.data.split(":")[2])
    DB.set_occurrence_status(occurrence_id, callback.message.chat.id, "partial")
    DB.log_event(callback.message.chat.id, "occurrence_partial", {"occurrence_id": occurrence_id})
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("◐ Часть тоже считается. Следующий повтор придёт по расписанию.")
    await callback.answer()


@router.callback_query(F.data.startswith("occ:snooze:"))
async def cb_occ_snooze(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    _, _, occurrence_id, minutes = callback.data.split(":")
    DB.snooze_occurrence(int(occurrence_id), callback.message.chat.id, int(minutes))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"⏰ Отложил на {minutes} минут.")
    await callback.answer()


@router.callback_query(F.data.startswith("occ:start:"))
async def cb_occ_start(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    _, _, occurrence_id, minutes = callback.data.split(":")
    session_id = DB.start_focus_session(callback.message.chat.id, int(occurrence_id), "reminder", int(minutes))
    DB.log_event(callback.message.chat.id, "focus_started", {"session_id": session_id, "occurrence_id": int(occurrence_id), "minutes": int(minutes)})
    await callback.message.answer(f"▶️ Поехали. Только {minutes} минут. Я вернусь в конце раунда.")
    await callback.answer()


async def send_rescue(message: Message) -> None:
    DB.log_event(message.chat.id, "doomscroll_rescue_opened")
    await message.answer(
        "🧯 <b>Поймал залип — уже достаточно.</b>\n\n"
        "1. Закрой ленту.\n"
        "2. Положи телефон экраном вниз.\n"
        "3. Встань или просто поменяй положение тела.\n"
        "4. Один длинный выдох.\n\n"
        "Ничего не спасаем целиком. Через 90 секунд выберем один микрошаг.",
        parse_mode="HTML",
        reply_markup=rescue_keyboard(),
    )


@router.message(Command("zalip"))
async def cmd_zalip(message: Message) -> None:
    if await ensure_auth(message):
        await send_rescue(message)


@router.callback_query(F.data == "menu:zalip")
async def cb_zalip(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    await send_rescue(callback.message)
    await callback.answer()


@router.message(F.text.regexp(r"(?i)^\s*(я\s+)?залип(аю)?[.!?\s]*$"))
async def text_zalip(message: Message) -> None:
    if await ensure_auth(message):
        await send_rescue(message)


@router.callback_query(F.data == "rescue:ready")
async def cb_rescue_ready(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    chat_id = callback.message.chat.id
    day, tz_name = _local_day(chat_id)
    DB.ensure_occurrences_for_day(chat_id, day, tz_name)
    occurrence = DB.best_pending_occurrence(chat_id, utcnow())
    if occurrence:
        micro = occurrence.microstep or f"Открой «{occurrence.title}» и сделай первый шаг."
        await callback.message.answer(
            f"Сейчас только это:\n\n<b>{esc(micro)}</b>\n\nПять минут. Потом можно остановиться.",
            parse_mode="HTML",
            reply_markup=rescue_start_keyboard(occurrence.id),
        )
    else:
        await callback.message.answer(
            "Просроченной задачи нет. Выбери один самый маленький шаг из ДВИЖа и дай ему пять минут.",
            reply_markup=rescue_start_keyboard(None),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("rescue:start:"))
async def cb_rescue_start(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    raw = int(callback.data.rsplit(":", 1)[1])
    occurrence_id = raw or None
    session_id = DB.start_focus_session(callback.message.chat.id, occurrence_id, "doomscroll_rescue", 5)
    DB.log_event(callback.message.chat.id, "doomscroll_rescue_focus_started", {"session_id": session_id, "occurrence_id": occurrence_id})
    await callback.message.answer("▶️ 5 минут пошли. Не улучшай план — просто делай первый шаг.")
    await callback.answer()


@router.callback_query(F.data.startswith("focus:"))
async def cb_focus_result(callback: CallbackQuery) -> None:
    if not await ensure_cb_auth(callback):
        return
    _, result, session_raw = callback.data.split(":")
    session_id = int(session_raw)
    row = DB.finish_focus_session(session_id, callback.message.chat.id, result)
    if not row:
        await callback.answer("Раунд не найден", show_alert=True)
        return
    occurrence_id = row["occurrence_id"]
    if occurrence_id:
        if result == "done":
            DB.set_occurrence_status(int(occurrence_id), callback.message.chat.id, "done")
        elif result == "partial":
            DB.set_occurrence_status(int(occurrence_id), callback.message.chat.id, "partial")
    DB.log_event(callback.message.chat.id, "focus_finished", {"session_id": session_id, "result": result})
    text = {
        "done": "✅ Готово. Раунд засчитан.",
        "partial": "◐ Часть засчитана. Это не нулевой день.",
        "no": "Окей. Не превращаем один неудачный раунд в приговор всему дню.",
    }[result]
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(text, reply_markup=main_menu())
    await callback.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменил текущий ввод.", reply_markup=main_menu())
