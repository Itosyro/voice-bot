"""Edge case and stress tests for all components."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Settings
from src.services.skills_db import SkillsDB
from src.storage.models import SkillIndex

# ===== Config edge cases =====


def test_get_groq_key_specific_mode(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("GROQ_API_KEY_POLISH", "polish_key")
    monkeypatch.setenv("GROQ_API_KEY_FALLBACK", "fallback_key")
    s = Settings()
    assert s.get_groq_key("polish") == "polish_key"
    assert s.get_groq_key("translator") == "fallback_key"


def test_get_groq_key_no_key_raises(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.delenv("GROQ_API_KEY_FALLBACK", raising=False)
    monkeypatch.delenv("GROQ_API_KEY_POLISH", raising=False)
    monkeypatch.delenv("GROQ_API_KEY_PROMPT", raising=False)
    monkeypatch.delenv("GROQ_API_KEY_HUMANIZER", raising=False)
    monkeypatch.delenv("GROQ_API_KEY_TRANSLATOR", raising=False)
    s = Settings(
        _env_file=None,  # type: ignore[call-arg]
        telegram_bot_token="x",
        database_url="x",
    )
    with pytest.raises(RuntimeError, match="No Groq API key"):
        s.get_groq_key("polish")


def test_admin_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("ADMIN_USER_IDS", "111,222")
    s = Settings()
    assert s.admin_user_ids_list == [111, 222]


def test_admin_user_ids_empty(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    s = Settings()
    assert s.admin_user_ids_list == []


def test_allowed_user_ids_with_spaces(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("ALLOWED_USER_IDS", "  100 ,  200  , 300  ")
    s = Settings()
    assert s.allowed_user_ids_list == [100, 200, 300]


def test_get_groq_key_unknown_mode_uses_fallback(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("GROQ_API_KEY_FALLBACK", "fb_key")
    s = Settings()
    assert s.get_groq_key("unknown_mode") == "fb_key"


# ===== Skills DB edge cases =====


def _make_skill(
    name: str,
    description: str = "desc",
    body: str = "body",
    repo: str = "test/repo",
) -> SkillIndex:
    return SkillIndex(
        id=0,
        source_repo=repo,
        skill_name=name,
        description=description,
        body=body,
        file_path="test.md",
        tags=None,
    )


def test_search_with_many_skills():
    """Stress test: search with 500 skills."""
    skills = [_make_skill(f"skill_{i}", f"description {i}", f"body text {i}") for i in range(500)]
    db = SkillsDB(skills)
    results = db.search("description 42", top_k=5)
    assert len(results) <= 5
    assert any("42" in s.description for s in results)


def test_search_top_k_limits():
    skills = [_make_skill(f"skill_{i}", f"skill about topic {i}") for i in range(20)]
    db = SkillsDB(skills)
    results = db.search("topic", top_k=3)
    assert len(results) <= 3


def test_search_unicode_query():
    skills = [
        _make_skill(
            "design_skill",
            "Создание красивого дизайна интерфейса",
            "Разработка UI/UX дизайна интерфейса",
        ),
        _make_skill("code_skill", "Programming with Python backend", "Backend development"),
        _make_skill("infra_skill", "DevOps infrastructure", "Cloud deployment"),
        _make_skill("test_skill", "Unit testing framework", "pytest fixtures"),
    ]
    db = SkillsDB(skills)
    # With 4+ docs, BM25 IDF gives positive scores for less frequent terms
    results = db.search("дизайна интерфейса")
    assert len(results) > 0
    assert results[0].skill_name == "design_skill"


def test_format_for_prompt_truncates():
    long_body = "x" * 50000
    skills = [_make_skill("long_skill", "desc", long_body)]
    formatted = SkillsDB.format_for_prompt(skills, max_total_chars=1000)
    assert len(formatted) < 2000


def test_search_all_styles():
    """Test search with each possible sub_style."""
    skills = [
        _make_skill("humanizer", "Remove AI", "human text", repo="blader/humanizer"),
        _make_skill("frontend-design", "Design", "UI skill", repo="anthropics/skills"),
        _make_skill("web-artifacts-builder", "Build web", "artifacts", repo="anthropics/skills"),
        _make_skill("stt_basic_cleanup", "STT cleanup", "cleanup text"),
    ]
    db = SkillsDB(skills)

    for style in [
        "designer",
        "coder",
        "coder_strict",
        "humanize_lite",
        "humanize_strong",
        "polish_default",
        "polish_creative",
        None,
    ]:
        results = db.search("test query", sub_style=style)
        assert isinstance(results, list)


def test_bm25_no_match():
    skills = [_make_skill("alpha", "alpha description", "alpha body")]
    db = SkillsDB(skills)
    results = db.search("zzzzzzzzzzzzzznotfound")
    assert len(results) == 0


# ===== Prompt rendering stress =====


def test_all_polish_prompts_render_with_long_text():
    from src.prompts.polish import POLISH_PROMPTS

    long_text = "Слово " * 5000
    for _name, tmpl in POLISH_PROMPTS.items():
        rendered = tmpl.format(transcript=long_text)
        assert len(rendered) > len(long_text)
        assert "Слово" in rendered


def test_all_humanizer_prompts_render_with_special_chars():
    from src.prompts.humanizer import HUMANIZER_PROMPTS

    text_with_specials = 'Text with {curly} and "quotes" and \\ backslash'
    for _name, tmpl in HUMANIZER_PROMPTS.items():
        rendered = tmpl.format(text=text_with_specials)
        assert "curly" in rendered


def test_translator_all_languages():
    from src.prompts.translator import LANG_NAMES, TRANSLATE_PROMPT

    for code, lang_name in LANG_NAMES.items():
        rendered = TRANSLATE_PROMPT.format(
            target_lang_name=lang_name,
            target_lang_code=code,
            transcript="Hello world",
        )
        assert lang_name in rendered
        assert code in rendered


# ===== Mode services with mocked Groq =====


@pytest.fixture
def mock_groq_client():
    with patch("src.services.llm.AsyncGroq") as mock:
        client = AsyncMock()
        mock.return_value = client

        choice = AsyncMock()
        choice.message.content = "Mocked output"

        response = AsyncMock()
        response.choices = [choice]

        client.chat.completions.create = AsyncMock(return_value=response)
        yield client


async def test_polish_all_styles(mock_groq_client):
    from src.services.polish import run_polish

    for style in ["polish_default", "polish_creative", "polish_formal", "polish_embellish"]:
        result = await run_polish("test text", sub_style=style)
        assert result.text == "Mocked output"
        assert result.llm_ms >= 0
        assert result.model != ""


async def test_polish_invalid_style_falls_back(mock_groq_client):
    from src.services.polish import run_polish

    result = await run_polish("test", sub_style="nonexistent_style")
    assert result.text == "Mocked output"


async def test_prompt_eng_all_styles(mock_groq_client):
    from src.services.prompt_eng import run_prompt_eng

    skills = [_make_skill("test-skill", "A test skill", "Test body")]
    db = SkillsDB(skills)

    for style in ["prompt_general", "prompt_designer", "prompt_coder", "prompt_coder_strict"]:
        result = await run_prompt_eng("build an app", sub_style=style, skills_db=db)
        assert result.text == "Mocked output"
        assert isinstance(result.used_skills, list)


async def test_prompt_eng_invalid_style_falls_back(mock_groq_client):
    from src.services.prompt_eng import run_prompt_eng

    db = SkillsDB([])
    result = await run_prompt_eng("test", sub_style="nonexistent", skills_db=db)
    assert result.text == "Mocked output"


async def test_humanizer_all_styles(mock_groq_client):
    from src.services.humanizer import run_humanizer

    for style in ["humanize_lite", "humanize_strong"]:
        result = await run_humanizer("AI text to humanize", sub_style=style)
        assert result.text == "Mocked output"


async def test_humanizer_invalid_style_falls_back(mock_groq_client):
    from src.services.humanizer import run_humanizer

    result = await run_humanizer("test", sub_style="nonexistent")
    assert result.text == "Mocked output"


async def test_translator_multiple_langs(mock_groq_client):
    from src.services.translator import run_translator

    for lang in ["en", "ru", "es", "fr", "de", "zh", "ja"]:
        result = await run_translator("hello", target_lang=lang)
        assert result.text == "Mocked output"
        assert result.target_lang == lang


async def test_translator_unknown_lang(mock_groq_client):
    from src.services.translator import run_translator

    result = await run_translator("hello", target_lang="xx")
    assert result.text == "Mocked output"
    assert result.target_lang == "xx"


# ===== Rate limiter stress test =====


async def test_rate_limiter_allows_within_limit():
    from src.middlewares.rate_limit import RateLimitMiddleware

    middleware = RateLimitMiddleware()

    handler = AsyncMock(return_value="ok")
    user = MagicMock()
    user.id = 12345

    event = MagicMock()
    data = {"event_from_user": user}

    for i in range(20):
        result = await middleware(handler, event, data)
        assert result == "ok", f"Request {i + 1} should pass"


async def test_rate_limiter_blocks_over_limit():
    from src.middlewares.rate_limit import RateLimitMiddleware

    middleware = RateLimitMiddleware()

    handler = AsyncMock(return_value="ok")
    user = MagicMock()
    user.id = 99999

    event = MagicMock(spec=["answer"])
    event.answer = AsyncMock()
    data = {"event_from_user": user}

    # Fill up the limit
    for _ in range(20):
        await middleware(handler, event, data)

    # 21st request should be blocked
    result = await middleware(handler, event, data)
    assert result is None


async def test_rate_limiter_different_users_independent():
    from src.middlewares.rate_limit import RateLimitMiddleware

    middleware = RateLimitMiddleware()

    handler = AsyncMock(return_value="ok")

    user1 = MagicMock()
    user1.id = 11111
    user2 = MagicMock()
    user2.id = 22222

    event = MagicMock()
    data1 = {"event_from_user": user1}
    data2 = {"event_from_user": user2}

    # Fill up user1's limit
    for _ in range(20):
        await middleware(handler, event, data1)

    # user2 should still be allowed
    result = await middleware(handler, event, data2)
    assert result == "ok"


# ===== Auth middleware =====


async def test_auth_middleware_allows_when_no_restriction(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("ALLOWED_USER_IDS", "")

    from src.middlewares.auth import AuthMiddleware

    middleware = AuthMiddleware()
    handler = AsyncMock(return_value="ok")
    event = MagicMock()
    user = MagicMock()
    user.id = 12345
    data = {"event_from_user": user}

    result = await middleware(handler, event, data)
    assert result == "ok"


# ===== UI keyboards =====


def test_all_keyboards_return_valid_markup():
    from src.ui.keyboards import (
        humanizer_style_keyboard,
        lang_keyboard,
        mode_keyboard,
        polish_style_keyboard,
        prompt_style_keyboard,
        result_keyboard,
        settings_keyboard,
    )

    for kb_fn in [
        mode_keyboard,
        polish_style_keyboard,
        prompt_style_keyboard,
        humanizer_style_keyboard,
        lang_keyboard,
        settings_keyboard,
    ]:
        kb = kb_fn()
        assert kb.inline_keyboard is not None
        assert len(kb.inline_keyboard) > 0
        for row in kb.inline_keyboard:
            for btn in row:
                assert btn.text
                assert btn.callback_data

    for mode in ["polish", "prompt", "humanizer", "translator"]:
        kb = result_keyboard(mode)
        assert kb.inline_keyboard is not None


def test_lang_keyboard_has_all_languages():
    from src.prompts.translator import LANG_NAMES
    from src.ui.keyboards import lang_keyboard

    kb = lang_keyboard()
    all_callbacks = []
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data and btn.callback_data.startswith("lang:"):
                all_callbacks.append(btn.callback_data.split(":")[1])

    for code in LANG_NAMES:
        assert code in all_callbacks, f"Language {code} missing from keyboard"


# ===== Messages module =====


def test_message_constants_exist():
    from src.ui.messages import (
        HELP_MESSAGE,
        HUMANIZER_VOICE_ERROR,
        MODE_NAMES,
        START_MESSAGE,
        STYLE_NAMES,
        TEXT_TOO_LONG,
        VOICE_TOO_LONG,
    )

    assert len(START_MESSAGE) > 0
    assert len(HELP_MESSAGE) > 0
    assert len(HUMANIZER_VOICE_ERROR) > 0
    assert "{max_sec}" in VOICE_TOO_LONG
    assert "{max_len}" in TEXT_TOO_LONG
    assert len(MODE_NAMES) == 4
    assert len(STYLE_NAMES) == 10


# ===== FSM states =====


def test_fsm_states_exist():
    from src.states import ModeSelection

    assert ModeSelection.waiting_for_mode is not None
    assert ModeSelection.waiting_for_style is not None
    assert ModeSelection.waiting_for_lang is not None
    assert ModeSelection.waiting_for_input is not None
