"""Tests for UX fixes: full-text export store + humanizer text-reply routing."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.handlers import voice
from src.handlers._last import get_last_result, save_last_result


def test_last_result_store_roundtrip():
    save_last_result(123, "full result text " * 100)
    assert get_last_result(123) == "full result text " * 100
    assert get_last_result(999) is None


@pytest.mark.asyncio
async def test_send_result_saves_full_text_for_export():
    from src.handlers._reply import send_result

    message = MagicMock()
    message.chat.id = 555
    message.answer = AsyncMock()
    progress = MagicMock()
    progress.edit_text = AsyncMock()

    await send_result(message, progress, "the full answer", "", "", MagicMock())

    assert get_last_result(555) == "the full answer"


@pytest.mark.asyncio
async def test_humanizer_processes_text_reply_to_voice(monkeypatch):
    """Реплай ТЕКСТОМ на голосовое в режиме humanizer обрабатывает текст,
    а не показывает ошибку «только текст»."""
    ctx = MagicMock()
    ctx.default_mode = "humanizer"
    ctx.default_style = "humanize_lite"
    ctx.target_lang = "en"
    ctx.db_user_id = 1
    monkeypatch.setattr(voice, "load_user_context", AsyncMock(return_value=ctx))

    process_text_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(voice, "_process_text", process_text_mock)

    message = MagicMock()
    message.from_user.id = 42
    message.text = "очеловечь этот текст"
    # Своего медиа нет — голос только в reply_to_message
    message.voice = None
    message.audio = None
    message.video_note = None
    message.video = None
    reply = MagicMock()
    reply.voice = MagicMock()
    message.reply_to_message = reply
    message.answer = AsyncMock()

    await voice.handle_voice(message, MagicMock(), MagicMock(), MagicMock())

    process_text_mock.assert_awaited_once()
    assert process_text_mock.call_args.kwargs["text"] == "очеловечь этот текст"
    message.answer.assert_not_awaited()  # ошибка HUMANIZER_VOICE_ERROR не показана
