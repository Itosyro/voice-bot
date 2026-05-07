"""
Design System for Voice Polisher Bot.

Single source of truth for all visual elements.
Every emoji, label, and separator lives here.
"""

# ── Brand ──
BRAND = "✦ VOICE ✦"

# ── Mode icons (Unicode symbols — compact and elegant) ──
MODE_ICON = {
    "polish": "✎",
    "prompt": "◇",
    "humanizer": "≈",
    "translator": "⇄",
    "summary": "∑",
}

# ── Mode names (Russian, CAPS for buttons) ──
MODE_NAME = {
    "polish": "ПОЛИРОВКА",
    "prompt": "ПРОМПТ",
    "humanizer": "ОЧЕЛОВЕЧИТЬ",
    "translator": "ПЕРЕВОД",
    "summary": "САММАРИ",
}

# ── Style names ──
STYLE_NAME = {
    "polish_raw": "Сырой",
    "polish_default": "Обычный",
    "polish_creative": "Творческий",
    "polish_formal": "Деловой",
    "polish_embellish": "Литературный",
    "prompt_general": "Общий",
    "prompt_designer": "Дизайнер",
    "prompt_coder": "Кодер",
    "prompt_coder_strict": "Строгий",
    "humanize_lite": "Лёгкий",
    "humanize_strong": "Сильный",
}

# ── Style icons (Unicode, per sub-style) ──
STYLE_ICON = {
    "polish_raw": "▪",
    "polish_default": "▫",
    "polish_creative": "◦",
    "polish_formal": "▸",
    "polish_embellish": "◈",
    "prompt_general": "▪",
    "prompt_designer": "▫",
    "prompt_coder": "◦",
    "prompt_coder_strict": "▸",
    "humanize_lite": "▪",
    "humanize_strong": "▫",
}

# ── Short descriptions for sub-style buttons ──
STYLE_DESC = {
    "polish_raw": "как есть, без правок",
    "polish_default": "минимальная правка",
    "polish_creative": "живой, с ритмом",
    "polish_formal": "деловой тон",
    "polish_embellish": "литературный стиль",
    "prompt_general": "под любую задачу",
    "prompt_designer": "UI/UX, дизайн",
    "prompt_coder": "код, архитектура",
    "prompt_coder_strict": "production, SLO",
    "humanize_lite": "мягко, AI-маркеры",
    "humanize_strong": "переписать полностью",
}

# ── Action icons ──
ICON_BACK = "←"
ICON_REGEN = "↻"
ICON_MENU = "≡"
ICON_SETTINGS = "⚙"
ICON_HISTORY = "▤"
ICON_INFO = "ⓘ"
ICON_RESET = "↺"
ICON_OTHER = "⟳"
ICON_DOWNLOAD = "⇩"

# ── Button color styles (Bot API 9.4+) ──
# Values: "primary" (blue), "success" (green), "danger" (red), None (default/white)
BTN_STYLE_SETTINGS = "primary"
BTN_STYLE_BACK = "danger"
BTN_STYLE_STYLE = "success"

# ── Separator ──
DIV = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"

# ── Language flags ──
LANG_FLAG = {
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
