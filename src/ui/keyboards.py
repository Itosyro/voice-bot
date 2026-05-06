"""
All inline keyboards.

Design rules:
- Mode buttons: style="danger" (red accent), plain text only
- Utility buttons (settings, history, back): no style (default/neutral)
- Sub-style buttons: style="primary" (blue)
- NO icons/symbols/emoji on buttons — clean text only
- Callback prefixes: mode:, style:, lang:, back:, cmd:, settings:, info:, action:
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.prompts.translator import LANG_NAMES
from src.ui.design import (
    LANG_FLAG,
    MODE_NAME,
    STYLE_DESC,
    STYLE_NAME,
)

# ── Style constants ──

S_MODE = "danger"
S_STYLE = "primary"


# ── Helpers ──

def _mode_btn(mode: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=MODE_NAME[mode],
        callback_data=f"mode:{mode}",
        style=S_MODE,
    )


def _style_btn(style_id: str) -> InlineKeyboardButton:
    name = STYLE_NAME.get(style_id, style_id)
    desc = STYLE_DESC.get(style_id, "")
    text = f"{name} — {desc}" if desc else name
    if len(text) > 64:
        text = text[:61] + "..."
    return InlineKeyboardButton(
        text=text, callback_data=f"style:{style_id}", style=S_STYLE
    )


def _back_btn(target: str = "back:modes") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="Назад", callback_data=target)]


# ── Mode selection (main menu) ──

def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_mode_btn("polish"), _mode_btn("prompt")],
            [_mode_btn("humanizer"), _mode_btn("translator")],
            [
                InlineKeyboardButton(
                    text="Настройки",
                    callback_data="cmd:settings",
                ),
                InlineKeyboardButton(
                    text="История",
                    callback_data="cmd:history",
                ),
            ],
        ]
    )


# ── Reprocess mode selection ──

def reprocess_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_mode_btn("polish"), _mode_btn("prompt")],
            [_mode_btn("humanizer"), _mode_btn("translator")],
            _back_btn(),
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
                style=S_STYLE,
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

def result_keyboard(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Повтор",
                    callback_data="action:regenerate",
                ),
                InlineKeyboardButton(
                    text="Другой режим",
                    callback_data="action:other_mode",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Меню",
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
                    text="Сменить режим",
                    callback_data="settings:default_mode",
                    style=S_STYLE,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Язык перевода",
                    callback_data="settings:target_lang",
                    style=S_STYLE,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="О режимах",
                    callback_data="settings:mode_info",
                    style=S_STYLE,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Сброс",
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
                    text=MODE_NAME["polish"],
                    callback_data="info:polish",
                    style=S_MODE,
                ),
                InlineKeyboardButton(
                    text=MODE_NAME["prompt"],
                    callback_data="info:prompt",
                    style=S_MODE,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=MODE_NAME["humanizer"],
                    callback_data="info:humanizer",
                    style=S_MODE,
                ),
                InlineKeyboardButton(
                    text=MODE_NAME["translator"],
                    callback_data="info:translator",
                    style=S_MODE,
                ),
            ],
            _back_btn("back:settings"),
        ]
    )
