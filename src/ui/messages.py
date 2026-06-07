START_MESSAGE = """\
👋 Привет! Я — Voice Polisher Bot.

Я умею обрабатывать голос и текст в 4 режимах:

✨ **Polish** — транскрипция + очистка текста
🧠 **Prompt Engineer** — превращаю идею в профессиональный промпт
🤖 **Humanizer** — убираю признаки AI из текста (только текст!)
🌍 **Translator** — перевод с сохранением тона

Отправь мне голосовое сообщение или текст, и я обработаю!
Или выбери режим кнопкой ниже."""

HELP_MESSAGE = """\
📖 **Команды бота:**

/start — Приветствие
/help — Эта справка
/modes — Выбор режима
/settings — Настройки
/lang <код> — Быстрая смена языка (пример: /lang en)
/history — Последние 10 запросов
/cancel — Отменить текущее действие

**Режимы:**

✨ **Polish** — Очищает голосовую заметку: убирает слова-паразиты, \
ставит пунктуацию, исправляет грамматику.
- Default — минимальная правка
- Creative — яркий, эмоциональный текст
- Formal — деловой стиль
- Embellish — литературный, богатый язык

🧠 **Prompt Engineer** — Превращает идею в структурированный промпт.
- General — универсальный
- Designer — UI/UX дизайн
- Coder — Full-stack разработка
- Coder Strict — production-grade с полным чеклистом

🤖 **Humanizer** — Убирает AI-маркеры из текста.
- Lite — бережная очистка
- Strong — полное переписывание

🌍 **Translator** — Переводит текст с сохранением тона.
Поддерживает: EN, RU, ES, FR, DE, ZH, JA, KO, AR, TR и другие."""

HUMANIZER_VOICE_ERROR = (
    "🤖 Humanizer работает только с текстом. "
    "Перешли мне текст для очеловечивания, или переключись на режим Polish/Translator для голоса."
)

VOICE_TOO_LONG = "⚠️ Слишком длинное аудио (> {max_sec} секунд). Раздели на части."

TEXT_TOO_LONG = "⚠️ Слишком длинный текст (> {max_len} символов). Сократи или раздели."

RATE_LIMIT_ERROR = "⏳ Слишком много запросов, подожди минуту."

GROQ_ERROR = "⚠️ Сервер AI временно недоступен, попробуй через минуту."

NOT_ALLOWED = "🔒 У тебя нет доступа к этому боту."

RETRANSCRIBE_PROMPT = (
    "🎙️ Кэш очищен. Отправь то же голосовое сообщение ещё раз — "
    "расшифрую заново с нуля."
)

MODE_NAMES = {
    "polish": "✨ Polish",
    "prompt": "🧠 Prompt Engineer",
    "humanizer": "🤖 Humanizer",
    "translator": "🌍 Translator",
}

STYLE_NAMES = {
    "polish_default": "📝 Default",
    "polish_creative": "🎨 Creative",
    "polish_formal": "👔 Formal",
    "polish_embellish": "✍️ Embellish",
    "prompt_general": "🌐 General",
    "prompt_designer": "🎨 Designer",
    "prompt_coder": "💻 Coder",
    "prompt_coder_strict": "🔒 Coder Strict",
    "humanize_lite": "🌿 Lite",
    "humanize_strong": "🔥 Strong",
}
