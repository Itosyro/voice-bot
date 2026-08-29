from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def kb(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data) for text, data in row] for row in rows]
    )


def main_menu() -> InlineKeyboardMarkup:
    return kb([
        [("⚡ Чек-ин", "menu:checkin"), ("📅 Сегодня", "menu:today")],
        [("🗓 Неделя", "menu:week"), ("➕ Событие", "menu:event")],
        [("🗂 Расписание", "menu:schedule"), ("➕ Повтор", "menu:repeat")],
        [("🔁 Мои повторы", "menu:repeats"), ("⚙️ Настройки", "menu:settings")],
        [("🧯 Я залип", "menu:zalip")],
    ])


def energy_keyboard() -> InlineKeyboardMarkup:
    return kb([[("🛌 Лежу", "ci:e:0"), ("🪫 5 минут", "ci:e:1")], [("🙂 Норм", "ci:e:2"), ("⚡ Много", "ci:e:3")]])


def body_keyboard() -> InlineKeyboardMarkup:
    return kb([[("✅ Ок", "ci:b:0"), ("〰️ Ноет", "ci:b:1")], [("🧱 Ломит", "ci:b:2"), ("🛑 Стоп", "ci:b:3")]])


def stress_keyboard() -> InlineKeyboardMarkup:
    return kb([[("😌 Тихо", "ci:s:0"), ("😐 Есть", "ci:s:1")], [("😣 Сильно", "ci:s:2"), ("🌪 Шторм", "ci:s:3")]])


def reminder_keyboard(occurrence_id: int, minutes: int) -> InlineKeyboardMarkup:
    return kb([
        [(f"▶️ Начать {minutes} мин", f"occ:start:{occurrence_id}:{minutes}")],
        [("✅ Готово", f"occ:done:{occurrence_id}"), ("◐ Сделал часть", f"occ:partial:{occurrence_id}")],
        [("⏰ +10", f"occ:snooze:{occurrence_id}:10"), ("+30", f"occ:snooze:{occurrence_id}:30"), ("+60", f"occ:snooze:{occurrence_id}:60")],
    ])


def focus_result_keyboard(session_id: int) -> InlineKeyboardMarkup:
    return kb([[("✅ Сделал", f"focus:done:{session_id}"), ("◐ Часть", f"focus:partial:{session_id}"), ("❌ Не вышло", f"focus:no:{session_id}")]])


def rescue_keyboard() -> InlineKeyboardMarkup:
    return kb([[("⏱ 90 секунд прошло", "rescue:ready")]])


def rescue_start_keyboard(occurrence_id: int | None) -> InlineKeyboardMarkup:
    value = occurrence_id if occurrence_id is not None else 0
    return kb([[("▶️ Начать 5 минут", f"rescue:start:{value}")], [("⚡ Сначала чек-ин", "menu:checkin")]])
