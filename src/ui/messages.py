START_MESSAGE = """\
VOICE POLISHER

Голос → текст за секунды.
Выбери режим и отправь голосовое или текст."""

HELP_MESSAGE = """\
VOICE POLISHER — СПРАВКА

РЕЖИМЫ

✦ POLISH — чистит речь
  default · creative · formal · embellish

✦ PROMPT — идея → промпт
  general · designer · coder · strict

✦ HUMANIZER — убирает AI
  lite · strong

✦ TRANSLATOR — перевод
  14 языков, сохраняет тон

КОМАНДЫ
/modes — выбор режима
/settings — настройки
/lang en — сменить язык
/history — последние запросы"""

HUMANIZER_VOICE_ERROR = "Humanizer работает только с текстом.\nОтправь текст или переключи режим."

VOICE_TOO_LONG = "Аудио слишком длинное — макс. {max_sec} сек."

TEXT_TOO_LONG = "Текст слишком длинный — макс. {max_len} символов."

RATE_LIMIT_ERROR = "Подожди минуту — слишком много запросов."

GROQ_ERROR = "Сервер временно недоступен. Попробуй через минуту."

NOT_ALLOWED = "Нет доступа."

MODE_NAMES = {
    "polish": "POLISH",
    "prompt": "PROMPT",
    "humanizer": "HUMANIZER",
    "translator": "TRANSLATOR",
}

STYLE_NAMES = {
    "polish_default": "Default",
    "polish_creative": "Creative",
    "polish_formal": "Formal",
    "polish_embellish": "Embellish",
    "prompt_general": "General",
    "prompt_designer": "Designer",
    "prompt_coder": "Coder",
    "prompt_coder_strict": "Strict",
    "humanize_lite": "Lite",
    "humanize_strong": "Strong",
}
