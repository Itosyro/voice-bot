from __future__ import annotations

import html
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .config import Settings
from .db import Database, utcnow
from .keyboards import kb, main_menu
from .readiness import ReadinessResult
from .training_store import ACTIVITY_LABELS, TrainingStore
from .weekly_store import WeeklyStore

router = Router(name="dvizh-training")
DB: Database
SETTINGS: Settings
STORE: TrainingStore
WEEKLY: WeeklyStore

DAY_LABELS = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
STATUS_ICONS = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


class ReadinessWizard(StatesGroup):
    sleep = State()
    sleep_quality = State()
    energy = State()
    soreness = State()
    pain = State()
    stress = State()
    health = State()


class SessionWizard(StatesGroup):
    activity = State()
    duration = State()
    rpe = State()
    result = State()
    pain = State()
    jumps = State()


def configure(db: Database, settings: Settings, store: TrainingStore, weekly: WeeklyStore) -> None:
    global DB, SETTINGS, STORE, WEEKLY
    DB = db
    SETTINGS = settings
    STORE = store
    WEEKLY = weekly


def esc(value: Any) -> str:
    return html.escape(str(value), quote=False)


def _timezone(chat_id: int) -> tuple[ZoneInfo, str]:
    user = DB.get_user(chat_id)
    name = str(user["timezone"] if user else SETTINGS.timezone)
    try:
        return ZoneInfo(name), name
    except Exception:
        return ZoneInfo("Europe/Moscow"), "Europe/Moscow"


def _today(chat_id: int) -> tuple[date, str]:
    tz, name = _timezone(chat_id)
    return utcnow().astimezone(tz).date(), name


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


def _dashboard_keyboard(plan_enabled: bool, has_readiness: bool):
    rows = [
        [("🧠 Обновить готовность" if has_readiness else "🧠 Пройти готовность", "training:ready")],
        [("🏐 Можно ли волейбол?", "training:volleyball"), ("📝 Записать тренировку", "training:log")],
        [("📋 План 4× Upper/Lower", "training:plan")],
    ]
    if not plan_enabled:
        rows.append([("⚙️ Включить план 4×", "training:plan:enable")])
    else:
        rows.append([("⏸ Пауза плана", "training:plan:disable"), ("🗓 Открыть неделю", "menu:week")])
    rows.append([("⬅️ Главное меню", "training:menu")])
    return kb(rows)


def _readiness_text(result: ReadinessResult | dict[str, Any]) -> str:
    if isinstance(result, ReadinessResult):
        payload = result.to_dict()
    else:
        payload = result
    status = str(payload.get("status") or "yellow")
    icon = STATUS_ICONS.get(status, "🟡")
    reasons = payload.get("reasons") if isinstance(payload.get("reasons"), list) else []
    lines = [
        f"{icon} <b>{esc(payload.get('label') or 'Готовность')}</b> · {int(payload.get('score') or 0)}/100",
        "",
        f"<b>Силовая:</b> {esc(payload.get('strength_text') or '—')}",
        f"<b>Волейбол:</b> {esc(payload.get('volleyball_text') or '—')}",
        f"<b>Потолок усилия:</b> RPE {int(payload.get('rpe_cap') or 0)}/10",
    ]
    if reasons:
        lines.append("\n<b>Почему:</b>")
        lines.extend(f"• {esc(reason)}" for reason in reasons[:6])
    if payload.get("urgent"):
        lines.append("\n<b>Не тренируйся через опасный симптом. При боли/давлении в груди, обмороке или необычной сильной одышке нужна срочная медицинская помощь.</b>")
    return "\n".join(lines)


async def _send_dashboard(message: Message) -> None:
    chat_id = message.chat.id
    today, timezone_name = _today(chat_id)
    STORE.sync_slots_from_schedule(chat_id)
    profile = STORE.profile(chat_id)
    plan_enabled = bool(profile and profile["plan_enabled"])
    readiness = STORE.readiness_for_day(chat_id, today)
    context = STORE.schedule_context(chat_id, today)
    loads = STORE.load_summary(chat_id)
    upcoming = STORE.upcoming_training(chat_id, today, 7)

    lines = ["<b>🏋️ Тренировки и восстановление</b>"]
    if readiness:
        lines.append("\n" + _readiness_text(readiness["result"]))
    else:
        lines.append("\nСегодня готовность ещё не отмечена. Это займёт около минуты.")

    today_rows = [row for row in upcoming if row["dueDate"] == today.isoformat() and row["status"] == "pending"]
    if today_rows:
        lines.append("\n<b>Сегодня по плану:</b>")
        tz = ZoneInfo(timezone_name)
        for row in today_rows:
            start = row["startAt"]
            try:
                from datetime import datetime
                local_time = datetime.fromisoformat(start).astimezone(tz).strftime("%H:%M")
            except Exception:
                local_time = "—"
            lines.append(f"• <code>{local_time}</code> {esc(row['title'])}")
    elif context["gym_today"] or context["volleyball_today"]:
        lines.append("\nСегодня есть спортивный блок в недельном расписании.")
    else:
        lines.append("\nСегодня обязательной тренировки нет.")

    baseline = loads["baseline_weekly_load"]
    load_line = f"{int(loads['load_7d'] or 0)} AU за 7 дней"
    if baseline:
        load_line += f" · недавнее среднее {int(baseline)} AU/нед"
    lines.append(f"\n<b>Нагрузка:</b> {load_line}")
    lines.append("<small>AU = длительность × субъективное усилие RPE. Это ориентир, не медицинский допуск.</small>")

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_dashboard_keyboard(plan_enabled, bool(readiness)),
    )


@router.message(Command("training"))
async def command_training(message: Message) -> None:
    if await _auth_message(message):
        await _send_dashboard(message)


@router.callback_query(F.data == "menu:training")
async def callback_training(callback: CallbackQuery) -> None:
    if not await _auth_callback(callback):
        return
    await _send_dashboard(callback.message)
    await callback.answer()


@router.callback_query(F.data == "training:menu")
async def callback_training_menu(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer("Что сейчас нужно?", reply_markup=main_menu())
    await callback.answer()


@router.message(Command("ready"))
async def command_ready(message: Message, state: FSMContext) -> None:
    if not await _auth_message(message):
        return
    await _start_readiness(message, state)


@router.callback_query(F.data == "training:ready")
async def callback_ready(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _auth_callback(callback):
        return
    await _start_readiness(callback.message, state)
    await callback.answer()


async def _start_readiness(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ReadinessWizard.sleep)
    await message.answer(
        "🛌 <b>Сколько спал?</b>",
        parse_mode="HTML",
        reply_markup=kb([
            [("<5 ч", "tr:ready:sleep:45"), ("5–6 ч", "tr:ready:sleep:55")],
            [("6–7 ч", "tr:ready:sleep:65"), ("7–8 ч", "tr:ready:sleep:75")],
            [("8+ ч", "tr:ready:sleep:85")],
        ]),
    )


@router.callback_query(ReadinessWizard.sleep, F.data.startswith("tr:ready:sleep:"))
async def readiness_sleep(callback: CallbackQuery, state: FSMContext) -> None:
    value = int(callback.data.rsplit(":", 1)[1]) / 10
    await state.update_data(sleep_hours=value)
    await state.set_state(ReadinessWizard.sleep_quality)
    await callback.message.answer(
        "Какое качество сна?",
        reply_markup=kb([[("Провал", "tr:ready:sq:0"), ("Плохо", "tr:ready:sq:1")], [("Норм", "tr:ready:sq:2"), ("Хорошо", "tr:ready:sq:3")]]),
    )
    await callback.answer()


@router.callback_query(ReadinessWizard.sleep_quality, F.data.startswith("tr:ready:sq:"))
async def readiness_sleep_quality(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(sleep_quality=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(ReadinessWizard.energy)
    await callback.message.answer(
        "⚡ Сколько энергии прямо сейчас?",
        reply_markup=kb([[("0 · лежу", "tr:ready:energy:0"), ("1 · мало", "tr:ready:energy:1")], [("2 · норм", "tr:ready:energy:2"), ("3 · много", "tr:ready:energy:3")]]),
    )
    await callback.answer()


@router.callback_query(ReadinessWizard.energy, F.data.startswith("tr:ready:energy:"))
async def readiness_energy(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(energy=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(ReadinessWizard.soreness)
    await callback.message.answer(
        "🧱 Насколько забиты мышцы?",
        reply_markup=kb([[("0 · свежий", "tr:ready:sore:0"), ("1 · слегка", "tr:ready:sore:1")], [("2 · заметно", "tr:ready:sore:2"), ("3 · сильно", "tr:ready:sore:3")]]),
    )
    await callback.answer()


@router.callback_query(ReadinessWizard.soreness, F.data.startswith("tr:ready:sore:"))
async def readiness_soreness(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(soreness=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(ReadinessWizard.pain)
    await callback.message.answer(
        "🦴 Есть боль в суставе/сухожилии или боль, меняющая движение?",
        reply_markup=kb([[("0 · нет", "tr:ready:pain:0"), ("1 · слабая", "tr:ready:pain:1")], [("2 · заметная", "tr:ready:pain:2"), ("3 · сильная", "tr:ready:pain:3")]]),
    )
    await callback.answer()


@router.callback_query(ReadinessWizard.pain, F.data.startswith("tr:ready:pain:"))
async def readiness_pain(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(pain=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(ReadinessWizard.stress)
    await callback.message.answer(
        "🧠 Стресс/перегруз головы?",
        reply_markup=kb([[("0 · тихо", "tr:ready:stress:0"), ("1 · немного", "tr:ready:stress:1")], [("2 · высоко", "tr:ready:stress:2"), ("3 · шторм", "tr:ready:stress:3")]]),
    )
    await callback.answer()


@router.callback_query(ReadinessWizard.stress, F.data.startswith("tr:ready:stress:"))
async def readiness_stress(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(stress=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(ReadinessWizard.health)
    await callback.message.answer(
        "Последняя проверка: болезнь или опасный симптом?",
        reply_markup=kb([
            [("✅ Нет", "tr:ready:health:none"), ("🤧 Лёгкая простуда", "tr:ready:health:mild")],
            [("🤒 Температура/ломота", "tr:ready:health:systemic")],
            [("🚨 Боль в груди/обморок/необычная одышка", "tr:ready:health:redflag")],
        ]),
    )
    await callback.answer()


@router.callback_query(ReadinessWizard.health, F.data.startswith("tr:ready:health:"))
async def readiness_health(callback: CallbackQuery, state: FSMContext) -> None:
    choice = callback.data.rsplit(":", 1)[1]
    data = await state.get_data()
    today, _ = _today(callback.message.chat.id)
    illness = choice if choice in {"none", "mild", "systemic"} else "none"
    red_flag = choice == "redflag"
    result = STORE.save_readiness(
        chat_id=callback.message.chat.id,
        local_day=today,
        sleep_hours=float(data["sleep_hours"]),
        sleep_quality=int(data["sleep_quality"]),
        energy=int(data["energy"]),
        soreness=int(data["soreness"]),
        pain=int(data["pain"]),
        stress=int(data["stress"]),
        illness=illness,
        red_flag=red_flag,
    )
    try:
        DB.log_event(callback.message.chat.id, "training_readiness_saved", {"date": today.isoformat(), "score": result.score, "status": result.status})
    except Exception:
        pass
    await state.clear()
    await callback.message.answer(
        _readiness_text(result),
        parse_mode="HTML",
        reply_markup=kb([[("🏋️ К тренировкам", "menu:training"), ("🗓 Неделя", "menu:week")]]),
    )
    await callback.answer()


@router.callback_query(F.data == "training:volleyball")
async def callback_volleyball(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _auth_callback(callback):
        return
    today, _ = _today(callback.message.chat.id)
    readiness = STORE.readiness_for_day(callback.message.chat.id, today)
    if not readiness:
        await callback.message.answer("Чтобы не гадать, сначала пройди минутную готовность.", reply_markup=kb([[("🧠 Пройти", "training:ready")]]))
    else:
        payload = readiness["result"]
        icon = STATUS_ICONS.get(str(payload.get("status")), "🟡")
        await callback.message.answer(
            f"{icon} <b>Волейбол сегодня</b>\n\n{esc(payload.get('volleyball_text') or '—')}\n\nПотолок усилия: <b>RPE {int(payload.get('rpe_cap') or 0)}/10</b>.",
            parse_mode="HTML",
            reply_markup=kb([[("📝 Записать после игры", "training:log:volleyball"), ("🧠 Обновить", "training:ready")]]),
        )
    await callback.answer()


@router.callback_query(F.data == "training:plan")
async def callback_plan(callback: CallbackQuery) -> None:
    if not await _auth_callback(callback):
        return
    STORE.sync_slots_from_schedule(callback.message.chat.id)
    profile = STORE.profile(callback.message.chat.id)
    slots = STORE.plan_slots(callback.message.chat.id)
    if not slots:
        text = (
            "<b>4× Upper/Lower</b>\n\n"
            "ПН — Верх A\nВТ — Низ A\nЧТ — Верх B\nСБ — Низ B\n\n"
            "Время и дни после включения можно менять в веб-ДВИЖе → Неделя → Правила расписания."
        )
        keyboard = kb([[("⚙️ Включить план", "training:plan:enable")], [("⬅️ Назад", "menu:training")]])
    else:
        lines = ["<b>📋 План 4× Upper/Lower</b>"]
        for slot in slots:
            icon = "✅" if slot.enabled and profile and profile["plan_enabled"] else "⏸"
            lines.append(f"{icon} {DAY_LABELS[slot.weekday]} <code>{slot.start_local}</code> · {esc(slot.title)} · {slot.duration_minutes} мин")
        lines.append("\nМеняй дни и время через веб-ДВИЖ → Неделя → Правила расписания.")
        text = "\n".join(lines)
        keyboard = kb([[("⏸ Пауза", "training:plan:disable"), ("▶️ Включить", "training:plan:enable")], [("🗓 Неделя", "menu:week"), ("⬅️ Назад", "menu:training")]])
    await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "training:plan:enable")
async def callback_plan_enable(callback: CallbackQuery) -> None:
    if not await _auth_callback(callback):
        return
    today, timezone_name = _today(callback.message.chat.id)
    STORE.ensure_default_plan(callback.message.chat.id)
    WEEKLY.ensure_range(callback.message.chat.id, today, 8, timezone_name)
    try:
        DB.log_event(callback.message.chat.id, "training_plan_enabled", {"template": "upper_lower_4x"})
    except Exception:
        pass
    await callback.message.answer(
        "✅ План 4× включён: ПН/ВТ/ЧТ/СБ. Открой веб-ДВИЖ → Неделя, чтобы подвинуть дни и время под жизнь и волейбол.",
        reply_markup=kb([[("📋 Посмотреть план", "training:plan"), ("🗓 Неделя", "menu:week")]]),
    )
    await callback.answer()


@router.callback_query(F.data == "training:plan:disable")
async def callback_plan_disable(callback: CallbackQuery) -> None:
    if not await _auth_callback(callback):
        return
    STORE.set_plan_enabled(callback.message.chat.id, False)
    await callback.message.answer("⏸ План поставлен на паузу. История тренировок сохранена.", reply_markup=kb([[("▶️ Включить снова", "training:plan:enable")]]))
    await callback.answer()


@router.callback_query(F.data == "training:log")
async def callback_log(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _auth_callback(callback):
        return
    await _start_log(callback.message, state, None)
    await callback.answer()


@router.callback_query(F.data.startswith("training:log:"))
async def callback_log_prefilled(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _auth_callback(callback):
        return
    activity = callback.data.rsplit(":", 1)[1]
    await _start_log(callback.message, state, activity if activity in ACTIVITY_LABELS else None)
    await callback.answer()


async def _start_log(message: Message, state: FSMContext, activity: str | None) -> None:
    await state.clear()
    if activity:
        await state.update_data(activity=activity)
        await state.set_state(SessionWizard.duration)
        await _ask_duration(message)
        return
    await state.set_state(SessionWizard.activity)
    await message.answer(
        "Что записать?",
        reply_markup=kb([
            [("Верх A", "tr:log:activity:upper_a"), ("Низ A", "tr:log:activity:lower_a")],
            [("Верх B", "tr:log:activity:upper_b"), ("Низ B", "tr:log:activity:lower_b")],
            [("🏐 Волейбол", "tr:log:activity:volleyball"), ("🚶 Восстановление", "tr:log:activity:recovery")],
            [("Другое", "tr:log:activity:other")],
        ]),
    )


@router.callback_query(SessionWizard.activity, F.data.startswith("tr:log:activity:"))
async def log_activity(callback: CallbackQuery, state: FSMContext) -> None:
    activity = callback.data.rsplit(":", 1)[1]
    if activity not in ACTIVITY_LABELS:
        await callback.answer("Неизвестный тип", show_alert=True)
        return
    await state.update_data(activity=activity)
    await state.set_state(SessionWizard.duration)
    await _ask_duration(callback.message)
    await callback.answer()


async def _ask_duration(message: Message) -> None:
    await message.answer(
        "Сколько минут?",
        reply_markup=kb([[("30", "tr:log:duration:30"), ("45", "tr:log:duration:45"), ("60", "tr:log:duration:60")], [("75", "tr:log:duration:75"), ("90", "tr:log:duration:90"), ("120", "tr:log:duration:120")]]),
    )


@router.callback_query(SessionWizard.duration, F.data.startswith("tr:log:duration:"))
async def log_duration(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(duration=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(SessionWizard.rpe)
    await callback.message.answer(
        "Насколько тяжело было по шкале RPE 1–10?\n1 — очень легко, 10 — максимум.",
        reply_markup=kb([[(str(n), f"tr:log:rpe:{n}") for n in range(1, 6)], [(str(n), f"tr:log:rpe:{n}") for n in range(6, 11)]]),
    )
    await callback.answer()


@router.callback_query(SessionWizard.rpe, F.data.startswith("tr:log:rpe:"))
async def log_rpe(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(rpe=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(SessionWizard.result)
    await callback.message.answer(
        "Чем закончилось?",
        reply_markup=kb([[("✅ Сделал", "tr:log:result:done"), ("◐ Часть", "tr:log:result:partial")], [("— Пропустил", "tr:log:result:skipped")]]),
    )
    await callback.answer()


@router.callback_query(SessionWizard.result, F.data.startswith("tr:log:result:"))
async def log_result(callback: CallbackQuery, state: FSMContext) -> None:
    result = callback.data.rsplit(":", 1)[1]
    await state.update_data(result=result)
    await state.set_state(SessionWizard.pain)
    await callback.message.answer(
        "Боль после занятия?",
        reply_markup=kb([[("0 · нет", "tr:log:pain:0"), ("1 · слабая", "tr:log:pain:1")], [("2 · заметная", "tr:log:pain:2"), ("3 · сильная", "tr:log:pain:3")]]),
    )
    await callback.answer()


@router.callback_query(SessionWizard.pain, F.data.startswith("tr:log:pain:"))
async def log_pain(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(pain_after=int(callback.data.rsplit(":", 1)[1]))
    data = await state.get_data()
    if data.get("activity") == "volleyball":
        await state.set_state(SessionWizard.jumps)
        await callback.message.answer(
            "Примерно сколько прыжков? Можно грубо.",
            reply_markup=kb([[("0–15", "tr:log:jumps:10"), ("15–35", "tr:log:jumps:25")], [("35–60", "tr:log:jumps:45"), ("60+", "tr:log:jumps:80")]]),
        )
    else:
        await _finish_log(callback.message, state, None)
    await callback.answer()


@router.callback_query(SessionWizard.jumps, F.data.startswith("tr:log:jumps:"))
async def log_jumps(callback: CallbackQuery, state: FSMContext) -> None:
    await _finish_log(callback.message, state, int(callback.data.rsplit(":", 1)[1]))
    await callback.answer()


async def _finish_log(message: Message, state: FSMContext, jumps: int | None) -> None:
    data = await state.get_data()
    today, _ = _today(message.chat.id)
    session_id = STORE.log_session(
        chat_id=message.chat.id,
        local_day=today,
        activity=str(data["activity"]),
        duration_minutes=int(data["duration"]),
        rpe=int(data["rpe"]),
        result=str(data["result"]),
        pain_after=int(data["pain_after"]),
        jumps=jumps,
        source="telegram",
    )
    load = 0 if data["result"] == "skipped" else int(data["duration"]) * int(data["rpe"])
    try:
        DB.log_event(message.chat.id, "training_session_logged", {"session_id": session_id, "activity": data["activity"], "load": load})
    except Exception:
        pass
    await state.clear()
    warning = "\n⚠️ Сильная боль после занятия — не добивай нагрузку и оцени состояние очно." if int(data["pain_after"]) >= 3 else ""
    await message.answer(
        f"✅ Записано: <b>{esc(ACTIVITY_LABELS[str(data['activity'])])}</b> · {int(data['duration'])} мин · RPE {int(data['rpe'])} · нагрузка {load} AU.{warning}",
        parse_mode="HTML",
        reply_markup=kb([[("🏋️ Дашборд", "menu:training"), ("🧠 Готовность", "training:ready")]]),
    )
