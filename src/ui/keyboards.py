from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.prompts.translator import LANG_NAMES


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ПОЛИРОВКА", callback_data="mode:polish", style="primary"
                ),
                InlineKeyboardButton(
                    text="ПРОМПТ", callback_data="mode:prompt", style="primary"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="ОЧЕЛОВЕЧИТЬ", callback_data="mode:humanizer", style="success"
                ),
                InlineKeyboardButton(
                    text="ПЕРЕВОД", callback_data="mode:translator", style="success"
                ),
            ],
            [
                InlineKeyboardButton(text="⚙ Настройки", callback_data="cmd:settings"),
                InlineKeyboardButton(text="История", callback_data="cmd:history"),
            ],
        ]
    )


def polish_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Обычный", callback_data="style:polish_default", style="primary"
                ),
                InlineKeyboardButton(
                    text="Творческий", callback_data="style:polish_creative", style="success"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Деловой", callback_data="style:polish_formal", style="primary"
                ),
                InlineKeyboardButton(
                    text="Литературный", callback_data="style:polish_embellish", style="success"
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
                    text="Общий", callback_data="style:prompt_general", style="primary"
                ),
                InlineKeyboardButton(
                    text="Дизайнер", callback_data="style:prompt_designer", style="success"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Кодер", callback_data="style:prompt_coder", style="primary"
                ),
                InlineKeyboardButton(
                    text="Строгий", callback_data="style:prompt_coder_strict", style="danger"
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
                    text="Лёгкий", callback_data="style:humanize_lite", style="success"
                ),
                InlineKeyboardButton(
                    text="Сильный", callback_data="style:humanize_strong", style="danger"
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
                    text="Повтор", callback_data="action:regenerate", style="primary"
                ),
                InlineKeyboardButton(
                    text="Меню", callback_data="back:modes", style="success"
                ),
            ],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Режим", callback_data="settings:default_mode",
                    style="primary",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Язык", callback_data="settings:target_lang", style="primary"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Сброс", callback_data="settings:reset", style="danger"
                ),
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="back:modes")],
        ]
    )
