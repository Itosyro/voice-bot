"""
All inline keyboards.

Design rules:
- No style= param (Telegram doesn't support it)
- Mode buttons: icon + CAPS name
- Sub-style buttons: one per row, name + short description
- Consistent callback_data prefixes: mode:, style:, lang:, back:, cmd:, settings:, info:
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.prompts.translator import LANG_NAMES
from src.ui.design import (
    ICON_BACK,
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
    STYLE_NAME,
)

# ── Mode selection (main menu) ──

def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{MODE_ICON['polish']} {MODE_NAME['polish']}",
                    callback_data="mode:polish",
                ),
                InlineKeyboardButton(
                    text=f"{MODE_ICON['prompt']} {MODE_NAME['prompt']}",
                    callback_data="mode:prompt",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{MODE_ICON['humanizer']} {MODE_NAME['humanizer']}",
                    callback_data="mode:humanizer",
                ),
                InlineKeyboardButton(
                    text=f"{MODE_ICON['translator']} {MODE_NAME['translator']}",
                    callback_data="mode:translator",
                ),
            ],
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


# ── Sub-style buttons (name + description) ──

def _style_btn(style_id: str) -> InlineKeyboardButton:
    name = STYLE_NAME.get(style_id, style_id)
    desc = STYLE_DESC.get(style_id, "")
    text = f"{name} — {desc}" if desc else name
    if len(text) > 64:
        text = text[:61] + "..."
    return InlineKeyboardButton(text=text, callback_data=f"style:{style_id}")


def _back_btn() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=f"{ICON_BACK} Назад", callback_data="back:modes")]


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
        flag = LANG_FLAG.get(code, "🏳️")
        row.append(
            InlineKeyboardButton(text=f"{flag} {code.upper()}", callback_data=f"lang:{code}")
        )
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(_back_btn())
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Result actions ──

def result_keyboard(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{ICON_REGEN} Повтор",
                    callback_data="action:regenerate",
                ),
                InlineKeyboardButton(
                    text=f"{ICON_OTHER} Другой режим",
                    callback_data="action:other_mode",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{ICON_MENU} Меню",
                    callback_data="back:modes",
                ),
            ],
        ]
    )


# ── Settings ──

def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{MODE_ICON['polish']} Сменить режим",
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
                ),
            ],
            _back_btn(),
        ]
    )


# ── Mode info (from settings) ──

def mode_info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{MODE_ICON['polish']} {MODE_NAME['polish']}",
                    callback_data="info:polish",
                ),
                InlineKeyboardButton(
                    text=f"{MODE_ICON['prompt']} {MODE_NAME['prompt']}",
                    callback_data="info:prompt",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{MODE_ICON['humanizer']} {MODE_NAME['humanizer']}",
                    callback_data="info:humanizer",
                ),
                InlineKeyboardButton(
                    text=f"{MODE_ICON['translator']} {MODE_NAME['translator']}",
                    callback_data="info:translator",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"{ICON_BACK} Назад к настройкам",
                    callback_data="back:settings",
                ),
            ],
        ]
    )
