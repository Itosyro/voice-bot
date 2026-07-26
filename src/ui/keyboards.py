"""
All inline keyboards.

Design rules:
- Unicode symbols on buttons (NO emoji — only Unicode chars)
- Callback prefixes: mode:, style:, lang:, back:, cmd:, settings:, info:, action:
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.prompts.translator import LANG_NAMES
from src.ui.design import (
    BTN_STYLE_ACTION,
    BTN_STYLE_BACK,
    BTN_STYLE_MODE,
    BTN_STYLE_STYLE,
    ICON_BACK,
    ICON_DOWNLOAD,
    ICON_HISTORY,
    ICON_INFO,
    ICON_MENU,
    ICON_OTHER,
    ICON_REGEN,
    ICON_RESET,
    ICON_SETTINGS,
    LANG_FLAG,
    MODE_ICON,
    MODE_NAME,
    STYLE_DESC,
    STYLE_ICON,
    STYLE_NAME,
)

# ── Helpers ──


def _mode_btn(mode: str) -> InlineKeyboardButton:
    icon = MODE_ICON.get(mode, "")
    name = MODE_NAME[mode]
    return InlineKeyboardButton(
        text=f"{icon} {name}" if icon else name,
        callback_data=f"mode:{mode}",
        style=BTN_STYLE_MODE,
    )


def _style_btn(style_id: str) -> InlineKeyboardButton:
    icon = STYLE_ICON.get(style_id, "")
    name = STYLE_NAME.get(style_id, style_id)
    desc = STYLE_DESC.get(style_id, "")
    label = f"{name} — {desc}" if desc else name
    text = f"{icon} {label}" if icon else label
    if len(text) > 64:
        text = text[:61] + "..."
    return InlineKeyboardButton(
        text=text,
        callback_data=f"style:{style_id}",
        style=BTN_STYLE_STYLE,
    )


def _mode_info_btn(mode: str) -> InlineKeyboardButton:
    icon = MODE_ICON.get(mode, "")
    name = MODE_NAME[mode]
    return InlineKeyboardButton(
        text=f"{icon} {name}" if icon else name,
        callback_data=f"info:{mode}",
        style=BTN_STYLE_MODE,
    )


def _back_btn(target: str = "back:modes") -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text=f"{ICON_BACK} Назад", callback_data=target, style=BTN_STYLE_BACK)
    ]


# ── Mode selection (main menu) ──


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_mode_btn("polish"), _mode_btn("prompt")],
            [_mode_btn("humanizer"), _mode_btn("translator")],
            [_mode_btn("summary")],
            [
                InlineKeyboardButton(
                    text=f"{ICON_SETTINGS} Настройки",
                    callback_data="cmd:settings",
                ),
                InlineKeyboardButton(
                    text=f"{ICON_HISTORY} История",
                    callback_data="cmd:history",
                ),
            ],
        ]
    )


# ── Reprocess mode selection ──


def _rerun_btn(mode: str) -> InlineKeyboardButton:
    icon = MODE_ICON.get(mode, "")
    name = MODE_NAME[mode]
    return InlineKeyboardButton(
        text=f"{icon} {name}" if icon else name,
        callback_data=f"rerun:{mode}",
        style=BTN_STYLE_MODE,
    )


def reprocess_mode_keyboard() -> InlineKeyboardMarkup:
    """Выбор режима для НЕМЕДЛЕННОГО повторного прогона последнего запроса
    (rerun:) — не просто смена настройки с просьбой переслать заново."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_rerun_btn("polish"), _rerun_btn("prompt")],
            [_rerun_btn("humanizer"), _rerun_btn("translator")],
            [_rerun_btn("summary")],
            _back_btn(),
        ]
    )


def menu_keyboard() -> InlineKeyboardMarkup:
    """Одна кнопка «Меню» — чтобы после выбора стиля не оставался тупик."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{ICON_MENU} Меню", callback_data="back:modes")]
        ]
    )


# ── Polish styles ──


def polish_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_style_btn("polish_raw")],
            [_style_btn("polish_default")],
            [_style_btn("polish_creative")],
            [_style_btn("polish_formal")],
            [_style_btn("polish_embellish")],
            _back_btn(),
        ]
    )


# ── Prompt styles ──


def prompt_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_style_btn("prompt_general")],
            [_style_btn("prompt_designer")],
            [_style_btn("prompt_coder")],
            [_style_btn("prompt_coder_strict")],
            _back_btn(),
        ]
    )


# ── Humanizer styles ──


def humanizer_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_style_btn("humanize_lite")],
            [_style_btn("humanize_strong")],
            _back_btn(),
        ]
    )


# ── Language picker (translator) ──


def lang_keyboard() -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, _name in LANG_NAMES.items():
        flag = LANG_FLAG.get(code, "")
        row.append(
            InlineKeyboardButton(
                text=f"{flag} {code.upper()}",
                callback_data=f"lang:{code}",
            )
        )
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(_back_btn())
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Result actions ──


def result_keyboard(mode: str, with_transcript: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                # «Ещё вариант» честнее «Повтора»: генерация каждый раз новая.
                text=f"{ICON_REGEN} Ещё вариант",
                callback_data="action:regenerate",
                style=BTN_STYLE_ACTION,
            ),
            InlineKeyboardButton(
                text=f"{ICON_OTHER} Другой режим",
                callback_data="action:other_mode",
                style=BTN_STYLE_ACTION,
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"{ICON_DOWNLOAD} Скачать .txt",
                callback_data="action:export",
                style=BTN_STYLE_ACTION,
            ),
            InlineKeyboardButton(
                text=f"{ICON_MENU} Меню",
                callback_data="back:modes",
                style=BTN_STYLE_ACTION,
            ),
        ],
    ]
    if with_transcript:
        rows.insert(
            1,
            [
                InlineKeyboardButton(
                    text="🎙 Транскрипт — что я сказал дословно",
                    callback_data="action:transcript",
                    style=BTN_STYLE_ACTION,
                )
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Settings ──


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{ICON_OTHER} Сменить режим",
                    callback_data="settings:default_mode",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{MODE_ICON['translator']} Язык перевода",
                    callback_data="settings:target_lang",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{ICON_INFO} О режимах",
                    callback_data="settings:mode_info",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{ICON_RESET} Сброс",
                    callback_data="settings:reset",
                    style=BTN_STYLE_BACK,
                ),
            ],
            _back_btn(),
        ]
    )


# ── Mode info (from settings) ──


def mode_info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_mode_info_btn("polish"), _mode_info_btn("prompt")],
            [_mode_info_btn("humanizer"), _mode_info_btn("translator")],
            [_mode_info_btn("summary")],
            _back_btn("back:settings"),
        ]
    )


# ── Admin dashboard ──


def admin_user_keyboard(telegram_user_id: int, is_blocked: bool) -> InlineKeyboardMarkup:
    """Ban/unban toggle for a single user's admin card."""
    if is_blocked:
        action_btn = InlineKeyboardButton(
            text="✅ Разблокировать", callback_data=f"admin:unban:{telegram_user_id}"
        )
    else:
        action_btn = InlineKeyboardButton(
            text="🚫 Заблокировать", callback_data=f"admin:ban:{telegram_user_id}"
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [action_btn],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить", callback_data=f"admin:user:{telegram_user_id}"
                )
            ],
        ]
    )
