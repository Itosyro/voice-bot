from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.prompts.translator import LANG_NAMES


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="POLISH", callback_data="mode:polish", style="primary"
                ),
                InlineKeyboardButton(
                    text="PROMPT", callback_data="mode:prompt", style="primary"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="HUMANIZER", callback_data="mode:humanizer", style="success"
                ),
                InlineKeyboardButton(
                    text="TRANSLATOR", callback_data="mode:translator", style="success"
                ),
            ],
            [
                InlineKeyboardButton(text="Настройки", callback_data="cmd:settings"),
                InlineKeyboardButton(text="История", callback_data="cmd:history"),
            ],
        ]
    )


def polish_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Default", callback_data="style:polish_default", style="primary"
                ),
                InlineKeyboardButton(
                    text="Creative", callback_data="style:polish_creative", style="success"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Formal", callback_data="style:polish_formal", style="primary"
                ),
                InlineKeyboardButton(
                    text="Embellish", callback_data="style:polish_embellish", style="success"
                ),
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="back:modes")],
        ]
    )


def prompt_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="General", callback_data="style:prompt_general", style="primary"
                ),
                InlineKeyboardButton(
                    text="Designer", callback_data="style:prompt_designer", style="success"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Coder", callback_data="style:prompt_coder", style="primary"
                ),
                InlineKeyboardButton(
                    text="Strict", callback_data="style:prompt_coder_strict", style="danger"
                ),
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="back:modes")],
        ]
    )


def humanizer_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Lite", callback_data="style:humanize_lite", style="success"
                ),
                InlineKeyboardButton(
                    text="Strong", callback_data="style:humanize_strong", style="danger"
                ),
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="back:modes")],
        ]
    )


LANG_EMOJI = {
    "en": "🇬🇧",
    "ru": "🇷🇺",
    "es": "🇪🇸",
    "fr": "🇫🇷",
    "de": "🇩🇪",
    "zh": "🇨🇳",
    "ja": "🇯🇵",
    "ko": "🇰🇷",
    "ar": "🇸🇦",
    "tr": "🇹🇷",
    "pt": "🇵🇹",
    "it": "🇮🇹",
    "pl": "🇵🇱",
    "uk": "🇺🇦",
}


def lang_keyboard() -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code, _name in LANG_NAMES.items():
        emoji = LANG_EMOJI.get(code, "🏳️")
        row.append(
            InlineKeyboardButton(
                text=f"{emoji} {code.upper()}", callback_data=f"lang:{code}", style="primary"
            )
        )
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="back:modes")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def result_keyboard(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Ещё раз", callback_data="action:regenerate", style="primary"
                ),
                InlineKeyboardButton(
                    text="Режимы", callback_data="back:modes", style="success"
                ),
            ],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Режим по умолчанию", callback_data="settings:default_mode",
                    style="primary",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Язык перевода", callback_data="settings:target_lang", style="primary"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Сбросить", callback_data="settings:reset", style="danger"
                ),
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="back:modes")],
        ]
    )
