"""Tests for the resilience layer: model fallback chain + dead-DB survival."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import llm
from src.storage import user_context
from src.storage.user_context import (
    load_user_context,
    reset_memory_store,
    save_user_settings,
)


@pytest.fixture(autouse=True)
def _clean_memory_store():
    reset_memory_store()
    yield
    reset_memory_store()


# ── llm.complete: model fallback chain ──


class _FakeModelGoneError(Exception):
    def __init__(self) -> None:
        super().__init__("The model `x` has been decommissioned (model_decommissioned)")
        self.status_code = 400


def _stream_of(text: str):
    async def _gen():
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta.content = text
        yield chunk

    return _gen()


@pytest.mark.asyncio
async def test_complete_falls_back_when_model_decommissioned(monkeypatch):
    """model_decommissioned на основной модели → complete() пробует запасную."""
    called_models: list[str] = []

    async def fake_create(**kwargs):
        called_models.append(kwargs["model"])
        if kwargs["model"] == "dead-model":
            raise _FakeModelGoneError()
        return _stream_of("ok")

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=fake_create)
    monkeypatch.setattr(llm, "AsyncGroq", MagicMock(return_value=client))
    monkeypatch.setattr(
        type(llm.settings), "llm_model_fallbacks_list", property(lambda self: ["live-model"])
    )

    text, _ms = await llm.complete("sys", "user", api_key="k", model="dead-model")

    assert text == "ok"
    assert called_models == ["dead-model", "live-model"]


@pytest.mark.asyncio
async def test_complete_raises_model_unavailable_when_all_models_gone(monkeypatch):
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=_FakeModelGoneError())
    monkeypatch.setattr(llm, "AsyncGroq", MagicMock(return_value=client))
    monkeypatch.setattr(
        type(llm.settings), "llm_model_fallbacks_list", property(lambda self: ["also-dead"])
    )

    with pytest.raises(llm.ModelUnavailableError):
        await llm.complete("sys", "user", api_key="k", model="dead-model")


def test_gpt_oss_gets_reasoning_params_automatically():
    """gpt-oss без reasoning_format возвращает пустой content — параметры обязаны
    подставляться автоматически (грабли из CLAUDE.md)."""
    extra = llm._reasoning_extra("openai/gpt-oss-120b", None)
    assert extra == {"reasoning_effort": "low", "reasoning_format": "hidden"}

    assert llm._reasoning_extra("qwen/qwen3.6-27b", None) == {}
    assert llm._reasoning_extra("openai/gpt-oss-120b", "medium") == {
        "reasoning_effort": "medium",
        "reasoning_format": "hidden",
    }


def test_is_model_unavailable_error_detection():
    assert llm.is_model_unavailable_error(_FakeModelGoneError())
    e404 = Exception("model_not_found")
    assert llm.is_model_unavailable_error(e404)
    plain = Exception("connection reset")
    assert not llm.is_model_unavailable_error(plain)


# ── user_context: dead-DB fallback ──


def _dead_session():
    session = MagicMock()
    session.execute = AsyncMock(side_effect=ConnectionError("db is down"))
    session.commit = AsyncMock(side_effect=ConnectionError("db is down"))
    session.rollback = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_load_user_context_survives_dead_db():
    ctx = await load_user_context(_dead_session(), telegram_user_id=42)
    assert ctx.db_user_id is None
    assert ctx.from_db is False
    assert ctx.default_mode is None


@pytest.mark.asyncio
async def test_save_user_settings_falls_back_to_memory_and_readback():
    """Выбор режима при мёртвой БД сохраняется в память и виден при чтении."""
    session = _dead_session()
    ok = await save_user_settings(session, 42, default_mode="prompt", default_style="prompt_coder")
    assert ok is False

    ctx = await load_user_context(session, telegram_user_id=42)
    assert ctx.default_mode == "prompt"
    assert ctx.default_style == "prompt_coder"
    assert ctx.db_user_id is None


@pytest.mark.asyncio
async def test_memory_settings_resync_to_db_when_it_recovers(monkeypatch):
    """Настройки, сохранённые в память при мёртвой БД, доезжают в БД после её оживления."""
    await save_user_settings(_dead_session(), 42, default_mode="summary")

    live_user = MagicMock()
    live_user.id = 7
    live_user.total_requests = 3
    monkeypatch.setattr(user_context, "get_or_create_user", AsyncMock(return_value=live_user))
    update_mock = AsyncMock()
    monkeypatch.setattr(user_context, "update_user_settings", update_mock)

    session = MagicMock()
    ctx = await load_user_context(session, telegram_user_id=42)

    assert ctx.default_mode == "summary"
    assert ctx.db_user_id == 7
    update_mock.assert_awaited_once()
    assert update_mock.call_args.kwargs["default_mode"] == "summary"


@pytest.mark.asyncio
async def test_save_user_settings_reset_clears_mode_and_style():
    await save_user_settings(_dead_session(), 42, default_mode="polish", default_style="polish_raw")
    await save_user_settings(_dead_session(), 42, reset=True)
    ctx = await load_user_context(_dead_session(), telegram_user_id=42)
    assert ctx.default_mode is None
    assert ctx.default_style is None


# ── text handler: результат доставляется, даже если история не записалась ──


@pytest.mark.asyncio
async def test_text_result_delivered_even_if_save_request_fails(monkeypatch):
    from src.handlers import text as text_handler

    monkeypatch.setattr(
        text_handler,
        "run_polish",
        AsyncMock(return_value=MagicMock(text="polished", llm_ms=5, model="m")),
    )
    monkeypatch.setattr(
        text_handler, "save_request", AsyncMock(side_effect=ConnectionError("db down"))
    )

    message = MagicMock()
    progress = MagicMock()
    progress.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=progress)

    session = MagicMock()
    session.rollback = AsyncMock()

    send_result_mock = AsyncMock()
    with patch.object(text_handler, "send_result", new=send_result_mock):
        ok = await text_handler._process_text(
            message,
            session,
            MagicMock(),
            text="hi",
            mode="polish",
            style="polish_raw",
            target_lang="en",
            db_user_id=1,
        )

    assert ok is True
    send_result_mock.assert_awaited_once()
    assert send_result_mock.call_args.args[2] == "polished"


@pytest.mark.asyncio
async def test_text_skips_history_when_db_user_unknown(monkeypatch):
    """db_user_id=None (БД лежала при чтении юзера) — save_request не зовём вовсе."""
    from src.handlers import text as text_handler

    monkeypatch.setattr(
        text_handler,
        "run_polish",
        AsyncMock(return_value=MagicMock(text="polished", llm_ms=5, model="m")),
    )
    save_mock = AsyncMock()
    monkeypatch.setattr(text_handler, "save_request", save_mock)

    message = MagicMock()
    progress = MagicMock()
    progress.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=progress)

    with patch.object(text_handler, "send_result", new=AsyncMock()):
        ok = await text_handler._process_text(
            message,
            MagicMock(),
            MagicMock(),
            text="hi",
            mode="polish",
            style=None,
            target_lang="en",
            db_user_id=None,
        )

    assert ok is True
    save_mock.assert_not_awaited()


# ── error messages ──


def test_error_message_for_model_unavailable():
    from src.handlers.text import error_message_for
    from src.ui.messages import GROQ_ERROR, MODEL_ERROR

    assert error_message_for(llm.ModelUnavailableError("gone")) == MODEL_ERROR
    assert error_message_for(Exception("boom")) == GROQ_ERROR
