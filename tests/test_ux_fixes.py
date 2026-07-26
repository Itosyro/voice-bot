"""Tests for UX fixes: full-text export store + humanizer text-reply routing."""

from unittest.mock import AsyncMock, MagicMock, patch

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


# ── находки критика: UTF-16 лимиты и защита результата ──


def test_split_text_respects_utf16_units():
    """Текст с эмодзи (2 UTF-16 юнита каждый) не должен пробивать лимит 4096."""
    from src.handlers._reply import split_text, tg_len

    emoji_text = "слово 🔥 " * 700  # ~5600 симв, ~6300 UTF-16 юнитов
    parts = split_text(emoji_text)
    assert len(parts) >= 2
    for part in parts:
        assert tg_len(part) <= 3500


def test_tg_len_counts_emoji_as_two():
    from src.handlers._reply import tg_len

    assert tg_len("абв") == 3
    assert tg_len("🔥") == 2
    assert tg_len("а🔥б") == 4


def test_result_message_detection():
    """Меню не должно затирать сообщения с результатом (blockquote/code entities)."""
    from src.handlers.callbacks import _holds_result

    result_msg = MagicMock()
    result_msg.entities = [MagicMock(type="blockquote"), MagicMock(type="code")]
    assert _holds_result(result_msg) is True

    nav_msg = MagicMock()
    nav_msg.entities = [MagicMock(type="bold")]
    assert _holds_result(nav_msg) is False

    plain_msg = MagicMock()
    plain_msg.entities = None
    assert _holds_result(plain_msg) is False


def test_result_by_message_store_caps_growth():
    from src.handlers._last import (
        _RESULTS_BY_MESSAGE_CAP,
        _results_by_message,
        get_result_for_message,
        save_result_for_message,
    )

    _results_by_message.clear()
    for i in range(_RESULTS_BY_MESSAGE_CAP + 50):
        save_result_for_message(1, i, f"r{i}")
    assert len(_results_by_message) <= _RESULTS_BY_MESSAGE_CAP + 1
    assert get_result_for_message(1, _RESULTS_BY_MESSAGE_CAP + 49) is not None
    _results_by_message.clear()


# ── бэклог раунда 2: очередь юзера и кэш чанкового транскрипта ──


@pytest.mark.asyncio
async def test_user_lock_serializes_and_reports_busy():
    from src.handlers._queue import cleanup_idle_locks, is_busy, user_lock

    uid = 777
    assert is_busy(uid) is False
    lock = user_lock(uid)
    async with lock:
        assert is_busy(uid) is True
    assert is_busy(uid) is False
    cleanup_idle_locks()
    assert is_busy(uid) is False  # после чистки замок пересоздаётся по требованию


@pytest.mark.asyncio
async def test_chunked_voice_uses_cached_transcript(monkeypatch, common_mocks=None):
    """Повторный прогон длинного голосового берёт транскрипт из кэша —
    Whisper и нарезка не запускаются вовсе."""
    from src.handlers import voice as voice_mod

    ctx = MagicMock()
    ctx.default_mode = "polish"
    ctx.default_style = None
    ctx.target_lang = "en"
    ctx.db_user_id = 1

    split_mock = AsyncMock()
    transcribe_mock = AsyncMock()
    monkeypatch.setattr(voice_mod, "split_audio_to_chunks", split_mock)
    monkeypatch.setattr(voice_mod, "transcribe", transcribe_mock)
    monkeypatch.setattr(voice_mod, "save_request", AsyncMock())
    monkeypatch.setattr(
        voice_mod,
        "run_polish",
        AsyncMock(return_value=MagicMock(text="polished", llm_ms=1, model="m")),
    )

    cached_row = MagicMock()
    cached_row.transcript = "cached long transcript"
    session = MagicMock()
    session.get = AsyncMock(return_value=cached_row)
    session.commit = AsyncMock()

    bot = MagicMock()
    file_info = MagicMock()
    file_info.file_path = "voice/f.ogg"
    bot.get_file = AsyncMock(return_value=file_info)
    fb = MagicMock()
    fb.read = MagicMock(return_value=b"bytes")
    bot.download_file = AsyncMock(return_value=fb)

    media = MagicMock()
    media.duration = 1200  # больше chunk_threshold_sec=600 → чанковый путь
    media.file_id = "long1"
    media.file_size = 1000

    message = MagicMock()
    message.chat.id = 5
    progress = MagicMock()
    progress.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=progress)

    with patch.object(voice_mod, "send_result", new=AsyncMock()) as sr:
        ok = await voice_mod._process_media(
            message,
            bot,
            session,
            MagicMock(),
            media=media,
            is_video=False,
            mode="polish",
            style=None,
            target_lang="en",
            db_user_id=1,
            force_retranscribe=False,
        )

    assert ok is True
    split_mock.assert_not_awaited()
    transcribe_mock.assert_not_awaited()
    sr.assert_awaited_once()
