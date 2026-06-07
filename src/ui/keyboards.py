from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.prompts.translator import LANG_NAMES


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✨ Polish", callback_data="mode:polish"),
                InlineKeyboardButton(text="🧠 Prompt Engineer", callback_data="mode:prompt"),
            ],
            [
                InlineKeyboardButton(text="🤖 Humanizer", callback_data="mode:humanizer"),
                InlineKeyboardButton(text="🌍 Translator", callback_data="mode:translator"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="cmd:settings"),
                InlineKeyboardButton(text="📜 История", callback_data="cmd:history"),
            ],
        ]
    )


def polish_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Default", callback_data="style:polish_default"),
                InlineKeyboardButton(text="🎨 Creative", callback_data="style:polish_creative"),
            ],
            [
                InlineKeyboardButton(text="👔 Formal", callback_data="style:polish_formal"),
                InlineKeyboardButton(text="✍️ Embellish", callback_data="style:polish_embellish"),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back:modes")],
        ]
    )


def prompt_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌐 General", callback_data="style:prompt_general"),
                InlineKeyboardButton(text="🎨 Designer", callback_data="style:prompt_designer"),
            ],
            [
                InlineKeyboardButton(text="💻 Coder", callback_data="style:prompt_coder"),
                InlineKeyboardButton(
                    text="🔒 Coder Strict", callback_data="style:prompt_coder_strict"
                ),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back:modes")],
        ]
    )


def humanizer_style_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🌿 Lite", callback_data="style:humanize_lite"),
                InlineKeyboardButton(text="🔥 Strong", callback_data="style:humanize_strong"),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back:modes")],
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
            InlineKeyboardButton(text=f"{emoji} {code.upper()}", callback_data=f"lang:{code}")
        )
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back:modes")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def result_keyboard(mode: str) -> InlineKeyboardMarkup:
    """Keyboard for text processing results."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="action:regenerate"),
                InlineKeyboardButton(text="🔀 Сменить режим", callback_data="back:modes"),
            ],
            [
                InlineKeyboardButton(
                    text="💾 Сделать default", callback_data=f"action:set_default:{mode}"
                ),
            ],
        ]
    )


def result_voice_keyboard(mode: str) -> InlineKeyboardMarkup:
    """Keyboard for voice processing results — includes retranscribe button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="action:regenerate"),
                InlineKeyboardButton(text="🔀 Сменить режим", callback_data="back:modes"),
            ],
            [
                InlineKeyboardButton(
                    text="💾 Сделать default", callback_data=f"action:set_default:{mode}"
                ),
                InlineKeyboardButton(
                    text="🎙️ Перетранскрибировать", callback_data="action:retranscribe"
                ),
            ],
        ]
    )


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎯 Режим по умолчанию", callback_data="settings:default_mode"
                ),
            ],
            [
                InlineKeyboardButton(text="🌍 Язык перевода", callback_data="settings:target_lang"),
            ],
            [
                InlineKeyboardButton(text="🗑️ Сбросить настройки", callback_data="settings:reset"),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back:modes")],
        ]
    )
