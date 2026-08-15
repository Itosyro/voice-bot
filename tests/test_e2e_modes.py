"""End-to-end: РЕАЛЬНЫЙ Dispatcher + РЕАЛЬНАЯ SQLite + фейковый Telegram.

Почему это отдельный файл. Все остальные тесты мокают сессию БД и дёргают
хендлеры напрямую — то есть проверяют функции, но не бота. Прод (вариант Б)
работает иначе: aiogram-Dispatcher с тремя middleware, SQLite-файл, и вся
логика «режим/стиль» живёт в цепочке `кнопка → save_user_settings → БД →
следующий апдейт`. Ровно эта цепочка и ломалась («режимы не работают»),
и ровно её здесь и гоняем.

Что здесь настоящее: `create_dispatcher()`, `AuthMiddleware`,
`RateLimitMiddleware`, `DbSessionMiddleware`, все роутеры, SQLite-диалект
(upsert, `func.now()`, WAL-прагмы). Замокано только внешнее: HTTP Telegram
(`FakeSession`), Groq (`AsyncGroq`) и Whisper (`transcribe`).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text as sa_text

from src.config import settings
from src.handlers import _last, _queue
from src.prompts.humanizer import HUMANIZER_PROMPTS
from src.prompts.polish import POLISH_PROMPTS
from src.prompts.prompt_eng import PROMPT_ENG_PROMPTS
from src.prompts.summary import SUMMARY_PROMPT
from src.prompts.translator import LANG_NAMES, TRANSLATE_PROMPT
from src.services import humanizer as humanizer_svc
from src.services import polish as polish_svc
from src.services.skills_db import SkillsDB
from src.storage.db import AsyncSessionMaker, engine, init_db
from src.storage.models import Base, SkillIndex
from src.storage.user_context import reset_memory_store
from src.storage.users import get_or_create_user, get_user_by_telegram_id, set_user_blocked
from src.ui.messages import NOT_ALLOWED, RATE_LIMIT_ERROR, USER_BLOCKED
from tests.conftest import make_groq_stream_response
from tests.e2e_harness import FakeSession, Harness, _bot_user, make_bot

LLM_REPLY = "ГОТОВЫЙ РЕЗУЛЬТАТ"

POLISH_STYLES = [
    "polish_raw",
    "polish_default",
    "polish_creative",
    "polish_formal",
    "polish_embellish",
]
PROMPT_STYLES = ["prompt_general", "prompt_designer", "prompt_coder", "prompt_coder_strict"]
HUMANIZER_STYLES = ["humanize_lite", "humanize_strong"]


# ── фикстуры ──


@pytest.fixture(autouse=True)
async def _clean_state():
    """Каждый тест стартует с пустой базы и пустых in-memory сторов."""
    await init_db()
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(sa_text(f"DELETE FROM {table.name}"))
    reset_memory_store()
    _queue._locks.clear()
    for store in (
        _last._store,
        _last._results,
        _last._results_by_message,
        _last._transcripts,
    ):
        store.clear()
    yield
    # Пул соединений привязан к текущему event loop — не тащим его в следующий тест.
    await engine.dispose()


class LLMRecorder:
    """Ловит вызовы Groq: по системному промпту видно РЕЖИМ и СТИЛЬ."""

    def __init__(self, reply: str = LLM_REPLY) -> None:
        self.calls: list[dict] = []
        self.reply = reply

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return make_groq_stream_response(self.reply)

    def clear(self) -> None:
        self.calls.clear()

    @property
    def system(self) -> str:
        return self.calls[-1]["messages"][0]["content"]

    @property
    def user(self) -> str:
        return self.calls[-1]["messages"][1]["content"]

    @property
    def model(self) -> str:
        return self.calls[-1]["model"]

    @property
    def temperature(self) -> float:
        return self.calls[-1]["temperature"]


@pytest.fixture
def groq():
    recorder = LLMRecorder()

    async def create(**kwargs):
        return await recorder(**kwargs)

    with patch("src.services.llm.AsyncGroq") as mock:
        client = MagicMock()
        client.chat.completions.create = AsyncMock(side_effect=create)
        mock.return_value = client
        yield recorder


@pytest.fixture
def stt():
    mock = AsyncMock(return_value=("тестовый транскрипт", 100))
    with (
        patch("src.services.transcribe.transcribe", mock),
        patch("src.handlers.voice.transcribe", mock),
    ):
        yield mock


def _skills_db() -> SkillsDB:
    return SkillsDB(
        [
            SkillIndex(
                id=1,
                source_repo="test/repo",
                skill_name="test-skill",
                description="A test skill",
                body="Test body content",
                file_path="test.md",
                tags=None,
            )
        ]
    )


def _new_dispatcher():
    """Свежий Dispatcher — как после рестарта контейнера.

    Роутеры в handlers/* — модульные синглтоны: второй `include_router` падает
    с «Router is already attached». Для теста «пережил рестарт» отвязываем их.
    """
    from src.bot import create_dispatcher
    from src.handlers import admin, callbacks, fallback, modes, start, text, voice
    from src.handlers import settings as settings_handler

    for module in (start, modes, settings_handler, admin, callbacks, voice, text, fallback):
        module.router._parent_router = None

    dp = create_dispatcher()
    dp.workflow_data["skills_db"] = _skills_db()
    return dp


@pytest.fixture
def harness(monkeypatch):
    # Лимит 20/мин считает и тапы по кнопкам — сценарии на 30 апдейтов упёрлись
    # бы в него. Отдельный тест ниже проверяет сам лимит по-настоящему.
    monkeypatch.setattr(settings, "rate_limit_per_user_per_min", 500)
    session = FakeSession()
    return Harness(_new_dispatcher(), make_bot(session), session)


# ── помощники ──


async def db_user(telegram_user_id: int = 1):
    async with AsyncSessionMaker() as session:
        return await get_user_by_telegram_id(session, telegram_user_id)


def result_text(harness: Harness) -> str:
    return harness.session.last_text()


def assert_no_error_toast(harness: Harness) -> None:
    bad = [t for t in harness.session.toasts() if "Ошибка" in t]
    assert not bad, f"пользователь увидел тост об ошибке: {bad}"


async def choose(harness: Harness, *taps: str, user_id: int = 1) -> None:
    await harness.send_command("/start", user_id=user_id)
    for data in taps:
        await harness.tap(data, user_id=user_id)


# ── /start и базовое меню ──


async def test_start_creates_user_and_shows_modes(harness):
    await harness.send_command("/start")

    sent = harness.session.sent()[-1]
    assert "VOICE" in sent.text
    modes = {"mode:polish", "mode:prompt", "mode:humanizer", "mode:translator", "mode:summary"}
    assert modes <= set(sent.buttons())
    user = await db_user()
    assert user is not None
    assert user.target_lang == "en"  # клиентский default долетел до SQLite


# ── Polish ──


@pytest.mark.parametrize("style", POLISH_STYLES)
async def test_polish_style_persists_and_drives_llm(harness, groq, style):
    await choose(harness, "mode:polish", f"style:{style}")
    groq.clear()

    await harness.send_text("текст на обработку")

    assert groq.system == POLISH_PROMPTS[style]
    assert groq.temperature == polish_svc.TEMPERATURE_MAP[style]
    assert "текст на обработку" in groq.user
    assert LLM_REPLY in result_text(harness)
    user = await db_user()
    assert (user.default_mode, user.default_style) == ("polish", style)
    assert_no_error_toast(harness)


async def test_mode_button_alone_persists_mode(harness, groq):
    """Без нажатия стиля режим всё равно обязан сохраниться (грабли №15)."""
    await choose(harness, "mode:polish")
    user = await db_user()
    assert user.default_mode == "polish"
    assert user.default_style is None


# ── Prompt ──


@pytest.mark.parametrize("style", PROMPT_STYLES)
async def test_prompt_style_persists_and_drives_llm(harness, groq, style):
    await choose(harness, "mode:prompt", f"style:{style}")
    groq.clear()

    await harness.send_text("хочу лендинг для кофейни")

    head = PROMPT_ENG_PROMPTS[style].split("{skills_context}")[0]
    assert groq.system.startswith(head)
    strict = style == "prompt_coder_strict"
    assert groq.model == (settings.llm_model_strict if strict else settings.llm_model_default)
    assert groq.temperature == (0.3 if strict else 0.4)
    assert groq.calls[-1]["max_completion_tokens"] == 4000
    if strict:
        # gpt-oss без reasoning-параметров отдаёт пустой content (грабли).
        assert groq.calls[-1]["reasoning_effort"] == "low"
        assert groq.calls[-1]["reasoning_format"] == "hidden"
    user = await db_user()
    assert (user.default_mode, user.default_style) == ("prompt", style)
    assert_no_error_toast(harness)


# ── Humanizer ──


@pytest.mark.parametrize("style", HUMANIZER_STYLES)
async def test_humanizer_style_persists_and_drives_llm(harness, groq, style):
    await choose(harness, "mode:humanizer", f"style:{style}")
    groq.clear()

    await harness.send_text("Это несомненно важный аспект данной проблематики.")

    assert groq.system == HUMANIZER_PROMPTS[style]
    assert groq.temperature == humanizer_svc.TEMPERATURE_MAP[style]
    user = await db_user()
    assert (user.default_mode, user.default_style) == ("humanizer", style)
    assert_no_error_toast(harness)


# ── Translator ──


@pytest.mark.parametrize("lang", ["de", "ja", "uk"])
async def test_translator_lang_persists_and_drives_llm(harness, groq, lang):
    await choose(harness, "mode:translator", f"lang:{lang}")
    groq.clear()

    await harness.send_text("привет мир")

    assert groq.system == TRANSLATE_PROMPT.format(
        target_lang_name=LANG_NAMES[lang], target_lang_code=lang
    )
    user = await db_user()
    assert (user.default_mode, user.default_style, user.target_lang) == (
        "translator",
        "translator",
        lang,
    )
    assert_no_error_toast(harness)


# ── Summary ──


async def test_summary_mode_needs_no_style(harness, groq):
    await choose(harness, "mode:summary")
    groq.clear()

    await harness.send_text("длинный рассказ о планах на неделю")

    assert groq.system == SUMMARY_PROMPT
    user = await db_user()
    assert (user.default_mode, user.default_style) == ("summary", "summary")
    assert_no_error_toast(harness)


async def test_switching_mode_drops_previous_style(harness, groq):
    """После Summary выбор ПОЛИРОВКИ не должен тащить style='summary'."""
    await choose(harness, "mode:summary")
    await harness.tap("back:modes")  # экран Summary даёт только «Меню»
    await harness.tap("mode:polish")
    groq.clear()

    await harness.send_text("проверка")

    assert groq.system == POLISH_PROMPTS["polish_default"]
    user = await db_user()
    assert user.default_mode == "polish"
    assert user.default_style is None


# ── Голос ──


@pytest.mark.parametrize(
    ("taps", "expect_system"),
    [
        (("mode:polish", "style:polish_formal"), lambda: POLISH_PROMPTS["polish_formal"]),
        (("mode:summary",), lambda: SUMMARY_PROMPT),
        (
            ("mode:translator", "lang:fr"),
            lambda: TRANSLATE_PROMPT.format(
                target_lang_name=LANG_NAMES["fr"], target_lang_code="fr"
            ),
        ),
    ],
)
async def test_voice_uses_selected_mode(harness, groq, stt, taps, expect_system):
    await choose(harness, *taps)
    groq.clear()

    await harness.send_voice()

    stt.assert_awaited()
    assert groq.system == expect_system()
    assert "тестовый транскрипт" in groq.user
    assert LLM_REPLY in result_text(harness)
    assert_no_error_toast(harness)


async def test_voice_in_prompt_mode(harness, groq, stt):
    await choose(harness, "mode:prompt", "style:prompt_coder")
    groq.clear()

    await harness.send_voice()

    assert groq.system.startswith(PROMPT_ENG_PROMPTS["prompt_coder"].split("{skills_context}")[0])


async def test_voice_in_humanizer_mode_is_refused(harness, groq, stt):
    await choose(harness, "mode:humanizer", "style:humanize_strong")
    groq.clear()

    await harness.send_voice()

    assert "работает только с" in result_text(harness)
    assert not groq.calls
    stt.assert_not_awaited()


async def test_forwarded_voice_is_processed(harness, groq, stt):
    await choose(harness, "mode:summary")
    groq.clear()

    await harness.send_voice(forwarded=True)

    assert groq.system == SUMMARY_PROMPT
    assert LLM_REPLY in result_text(harness)


async def test_reply_to_voice_is_processed(harness, groq, stt):
    await choose(harness, "mode:polish", "style:polish_creative")
    groq.clear()

    await harness.reply_to_voice()

    assert groq.system == POLISH_PROMPTS["polish_creative"]


async def test_text_reply_to_voice_processes_the_text(harness, groq, stt):
    """Юзер ответил ТЕКСТОМ на чужое голосовое — обрабатываем текст, не звук."""
    await choose(harness, "mode:polish", "style:polish_raw")
    groq.clear()

    await harness.reply_to_voice(text="мои собственные слова")

    assert "мои собственные слова" in groq.user
    stt.assert_not_awaited()


# ── Персистентность ──


async def test_settings_survive_restart(harness, groq):
    """Память процесса пропала (рестарт контейнера) — режим берётся из SQLite."""
    await choose(harness, "mode:prompt", "style:prompt_designer")

    reset_memory_store()
    harness.dp = _new_dispatcher()  # «новый процесс» — фолбэки в памяти пусты
    groq.clear()

    await harness.send_text("идея приложения")

    assert groq.system.startswith(
        PROMPT_ENG_PROMPTS["prompt_designer"].split("{skills_context}")[0]
    )


async def test_settings_card_shows_the_choice(harness, groq):
    await choose(harness, "mode:translator", "lang:pl", "back:modes", "cmd:settings")

    card = result_text(harness)
    assert "ПЕРЕВОД" in card
    assert "PL" in card
    assert "не выбран" not in card


async def test_settings_card_after_restart_reads_db(harness):
    await choose(harness, "mode:humanizer", "style:humanize_lite")
    reset_memory_store()
    harness.dp = _new_dispatcher()

    await harness.tap("back:modes")
    await harness.tap("cmd:settings")

    card = result_text(harness)
    assert "ОЧЕЛОВЕЧИТЬ" in card
    assert "Лёгкий" in card


# ── Кнопки под результатом ──


async def test_other_mode_then_rerun_translator(harness, groq):
    await choose(harness, "mode:polish", "style:polish_default")
    await harness.send_text("проверка связи")
    await harness.tap("action:other_mode")
    groq.clear()

    await harness.tap("rerun:translator")

    assert groq.system.startswith("Ты — профессиональный переводчик")
    assert "проверка связи" in groq.user  # прогнали тот же вход, без пересылки
    user = await db_user()
    assert user.default_mode == "translator"
    assert_no_error_toast(harness)


async def test_other_mode_does_not_overwrite_the_result(harness, groq):
    await choose(harness, "mode:polish", "style:polish_default")
    await harness.send_text("важный текст")
    result_call = harness.session.edits()[-1]
    harness.session.clear()

    await harness.tap("action:other_mode")

    assert harness.session.sent(), "«Другой режим» обязан прислать НОВОЕ сообщение"
    assert not harness.session.edits(), "результат нельзя перезаписывать"
    assert (
        harness.session.messages[(result_call.chat_id, result_call.message_id)].text.strip()
        == LLM_REPLY
    )


async def test_regenerate_runs_again(harness, groq):
    await choose(harness, "mode:summary")
    await harness.send_text("исходник")
    groq.clear()

    await harness.tap("action:regenerate")

    assert len(groq.calls) == 1
    assert groq.system == SUMMARY_PROMPT
    assert_no_error_toast(harness)


async def test_regenerate_after_text_reply_to_voice(harness, groq, stt):
    """«Ещё вариант» под ответом-текстом на голосовое повторяет ЭТОТ текст."""
    await choose(harness, "mode:polish", "style:polish_default")
    await harness.reply_to_voice(text="мои собственные слова")
    groq.clear()

    await harness.tap("action:regenerate")

    assert len(groq.calls) == 1
    assert "мои собственные слова" in groq.user
    stt.assert_not_awaited()
    assert_no_error_toast(harness)


async def test_merge_prev_falls_back_from_humanizer(harness, groq, stt):
    """Склейка после текстового humanize не должна давать пустой ответ.

    `voice.py::_run_mode` не знает режима humanizer — раньше склейка молча
    возвращала "" и юзер видел «⚠ Пустой ответ от модели».
    """
    # Два голосовых подряд — под вторым результатом появляется «Склеить».
    await choose(harness, "mode:polish", "style:polish_default")
    stt.return_value = ("первое голосовое", 100)
    await harness.send_voice(file_id="voice-1")
    stt.return_value = ("второе голосовое", 100)
    await harness.send_voice(file_id="voice-2")
    merge_screen = harness.session.find_with_button("action:merge_prev")

    # Дальше юзер ушёл в humanizer текстом — last.mode стал humanizer…
    await harness.tap("back:modes")
    await harness.tap("mode:humanizer")
    await harness.tap("style:humanize_strong")
    await harness.send_text("текст для очеловечивания")

    groq.clear()
    # …и вернулся к старому результату, чтобы склеить голосовые.
    await harness.tap_on(merge_screen, "action:merge_prev")

    assert groq.system == POLISH_PROMPTS["polish_default"]
    assert "первое голосовое" in groq.user
    assert "второе голосовое" in groq.user
    assert LLM_REPLY in result_text(harness)
    assert "Пустой ответ" not in result_text(harness)

    # «Ещё вариант» под склейкой повторяет склейку, а не последнее голосовое.
    groq.clear()
    await harness.tap("action:regenerate")
    assert "первое голосовое" in groq.user
    assert "второе голосовое" in groq.user


async def test_long_transcript_goes_as_document(harness, groq, stt):
    """Заголовок тоже входит в лимит Telegram — гейт меряет обе части."""
    await choose(harness, "mode:polish", "style:polish_default")
    await harness.send_voice()
    _last.save_last_transcript(1, "я" * 3495)
    harness.session.clear()

    await harness.tap("action:transcript")

    assert harness.session.documents(), "длинный транскрипт обязан уйти файлом"
    assert not harness.session.sent()


async def test_export_sends_txt_document(harness, groq):
    await choose(harness, "mode:polish", "style:polish_default")
    await harness.send_text("что-то")
    harness.session.clear()

    await harness.tap("action:export")

    docs = harness.session.documents()
    assert len(docs) == 1
    assert docs[0].payload.document.filename == "result.txt"
    assert "Готово" in harness.session.toasts()[-1]


async def test_transcript_button_shows_raw_whisper(harness, groq, stt):
    await choose(harness, "mode:polish", "style:polish_default")
    await harness.send_voice()
    harness.session.clear()

    await harness.tap("action:transcript")

    assert "тестовый транскрипт" in harness.session.last_text()


async def test_back_modes_on_result_sends_new_message(harness, groq):
    await choose(harness, "mode:polish", "style:polish_default")
    await harness.send_text("текст")
    result_call = harness.session.edits()[-1]
    harness.session.clear()

    await harness.tap("back:modes")

    assert harness.session.sent(), "«Меню» под результатом обязано слать НОВОЕ сообщение"
    assert not harness.session.edits()
    still = harness.session.messages[(result_call.chat_id, result_call.message_id)]
    assert LLM_REPLY in still.text
    assert_no_error_toast(harness)


# ── Сброс ──


async def test_reset_falls_back_to_polish_default(harness, groq):
    await choose(
        harness,
        "mode:translator",
        "lang:de",
        "back:modes",
        "cmd:settings",
        "settings:reset",
        "settings:reset_yes",
    )
    groq.clear()

    await harness.send_text("после сброса")

    assert groq.system == POLISH_PROMPTS["polish_default"]
    user = await db_user()
    assert user.default_mode is None
    assert user.default_style is None
    assert user.target_lang == "en"
    assert_no_error_toast(harness)


# ── Доступ ──


async def test_not_allowed_on_message_and_callback(harness, monkeypatch):
    await harness.send_command("/start")  # пока доступ открыт — есть меню с кнопками
    monkeypatch.setattr(settings, "allowed_user_ids", "999")
    harness.session.clear()

    await harness.send_text("привет")
    await harness.tap("mode:prompt")

    assert harness.session.last_text() == NOT_ALLOWED
    assert NOT_ALLOWED in harness.session.toasts()
    user = await db_user()
    assert user.default_mode is None  # чужой не смог переключить режим


async def test_allowed_user_passes(harness, monkeypatch, groq):
    monkeypatch.setattr(settings, "allowed_user_ids", "1,999")
    await choose(harness, "mode:summary")
    await harness.send_text("привет")
    assert groq.system == SUMMARY_PROMPT


async def test_blocked_user_is_stopped_but_admin_is_not(harness, monkeypatch, groq):
    async with AsyncSessionMaker() as session:
        await get_or_create_user(session, telegram_user_id=7)
        assert await set_user_blocked(session, 7, True)
        await session.commit()

    await harness.send_text("привет", user_id=7)
    assert harness.session.last_text() == USER_BLOCKED
    assert not groq.calls

    # Тот же забаненный id, но он админ — бан-чек его не трогает.
    # Новый Dispatcher = новый AuthMiddleware, т.е. пустой TTL-кэш бана
    # (бан/разбан вступает в силу максимум через BAN_CACHE_TTL секунд).
    monkeypatch.setattr(settings, "admin_user_ids", "7")
    harness.dp = _new_dispatcher()
    harness.session.clear()
    await harness.send_text("привет", user_id=7)
    assert groq.calls, "админа забанить нельзя"


# ── Даблтапы и «message is not modified» ──


async def test_double_tap_on_mode_shows_no_error_toast(harness, groq):
    await harness.send_command("/start")
    state = harness.session.find_with_button("mode:prompt")
    harness.session.clear()

    await harness.tap_on(state, "mode:prompt")
    await harness.tap_on(state, "mode:prompt")  # второй тап по тому же меню

    assert_no_error_toast(harness)
    user = await db_user()
    assert user.default_mode == "prompt"


async def test_same_mode_twice_in_a_row_is_silent(harness, groq):
    await harness.send_command("/start")
    await harness.tap("mode:polish")
    await harness.tap("back:modes")
    harness.session.clear()

    await harness.tap("mode:polish")

    assert_no_error_toast(harness)
    assert "Полировка" in harness.session.last_text()


async def test_settings_default_mode_after_back_modes_is_silent(harness):
    """`settings:default_mode` рисует ровно тот же экран, что и `back:modes`."""
    await harness.send_command("/start")
    await harness.tap("cmd:settings")
    settings_state = harness.session.find_with_button("settings:default_mode")
    await harness.tap_on(settings_state, "settings:default_mode")
    harness.session.clear()

    await harness.tap_on(settings_state, "settings:default_mode")

    assert_no_error_toast(harness)


# ── Кнопки на «недоступном» (старом) сообщении ──


def _inaccessible(chat_id: int = 1, message_id: int = 4321) -> dict:
    """Как Telegram присылает callback на сообщении старше ~48 часов.

    date=0 → aiogram отдаёт `InaccessibleMessage`: ни `text`, ни `entities`,
    ни `edit_text`. Владелец переустанавливает сервер раз в неделю, а меню
    из прошлого /start остаётся в чате — он листает вверх и жмёт «ПРОМПТ»
    именно на таком сообщении.
    """
    return {
        "message_id": message_id,
        "date": 0,
        "chat": {"id": chat_id, "type": "private"},
        "from": _bot_user(),
    }


async def _tap_inaccessible(harness: Harness, data: str, user_id: int = 1):
    return await harness.feed(
        {
            "callback_query": {
                "id": f"cb-old-{data}",
                "from": harness.user(user_id),
                "chat_instance": f"ci-{user_id}",
                "message": _inaccessible(chat_id=user_id),
                "data": data,
            }
        }
    )


@pytest.mark.parametrize(
    ("data", "expect_in_text"),
    [
        ("mode:polish", "Полировка"),
        ("mode:prompt", "Промпт"),
        ("mode:humanizer", "Очеловечить"),
        ("mode:translator", "Перевод"),
        ("mode:summary", "САММАРИ"),
        ("style:polish_creative", "Творческий"),
        ("style:prompt_coder_strict", "Строгий"),
        ("lang:de", "DE"),
        ("back:modes", "Выбери режим"),
        ("cmd:settings", "Настройки"),
        ("back:settings", "Настройки"),
        ("settings:default_mode", "Выбери режим"),
        ("settings:target_lang", "Перевод"),
        ("settings:mode_info", "узнать подробнее"),
        ("info:polish", "ПОЛИРОВКА"),
        ("settings:reset", "Сбросить режим"),
        ("settings:reset_yes", "Выбери режим"),
        ("cmd:history", "История пуста"),
        ("action:other_mode", "Другой режим"),
    ],
)
async def test_button_on_inaccessible_message_still_works(harness, data, expect_in_text):
    await harness.send_command("/start")
    harness.session.clear()

    await _tap_inaccessible(harness, data)

    assert_no_error_toast(harness)
    assert harness.session.sent(), f"{data}: пользователь не получил ни одного сообщения"
    assert expect_in_text in harness.session.last_text()


@pytest.mark.parametrize(
    ("data", "mode", "style"),
    [
        ("mode:prompt", "prompt", None),
        ("mode:summary", "summary", "summary"),
        ("style:polish_embellish", "polish", "polish_embellish"),
        ("lang:ja", "translator", "translator"),
    ],
)
async def test_inaccessible_message_still_persists_the_choice(harness, data, mode, style):
    """Визуальный фолбэк не должен отменять запись в БД."""
    await harness.send_command("/start")

    await _tap_inaccessible(harness, data)

    user = await db_user()
    assert (user.default_mode, user.default_style) == (mode, style)


async def test_mode_picked_on_old_message_changes_the_next_run(harness, groq):
    """Главный сценарий владельца: тап по прошлонедельному меню + новый текст."""
    await choose(harness, "mode:polish", "style:polish_default")
    await _tap_inaccessible(harness, "mode:summary")
    groq.clear()

    await harness.send_text("а теперь саммари")

    assert groq.system == SUMMARY_PROMPT
    assert_no_error_toast(harness)


async def test_export_on_inaccessible_message_does_not_crash(harness, groq):
    await choose(harness, "mode:polish", "style:polish_default")
    await harness.send_text("текст")
    harness.session.clear()

    await _tap_inaccessible(harness, "action:export")

    assert_no_error_toast(harness)
    assert harness.session.documents()


# ── Изоляция пользователей ──


async def test_two_users_do_not_leak_into_each_other(harness, groq):
    await choose(harness, "mode:prompt", "style:prompt_coder", user_id=1)
    await choose(harness, "mode:translator", "lang:es", user_id=2)

    groq.clear()
    await harness.send_text("первый", user_id=1)
    first_system = groq.system
    await harness.send_text("второй", user_id=2)
    second_system = groq.system

    assert first_system.startswith(PROMPT_ENG_PROMPTS["prompt_coder"].split("{skills_context}")[0])
    assert second_system == TRANSLATE_PROMPT.format(
        target_lang_name=LANG_NAMES["es"], target_lang_code="es"
    )
    assert (await db_user(1)).default_mode == "prompt"
    assert (await db_user(2)).default_mode == "translator"


# ── Rate limit (документируем реальное поведение) ──


async def test_rate_limit_counts_button_taps(harness, monkeypatch):
    """20 запросов в минуту — это и сообщения, и КНОПКИ. Владелец, кликая
    по меню, может выбрать лимит и получить «Подожди минуту» на тап."""
    monkeypatch.setattr(settings, "rate_limit_per_user_per_min", 4)
    await harness.send_command("/start")
    state = harness.session.find_with_button("mode:polish")

    for _ in range(5):
        await harness.tap_on(state, "mode:polish")

    assert RATE_LIMIT_ERROR in harness.session.toasts()
