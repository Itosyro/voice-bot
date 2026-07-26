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
    """Навигация не должна затирать результат и не должна падать на .txt-файле."""
    from src.handlers.callbacks import _holds_result

    result_msg = MagicMock(document=None, text="результат")
    result_msg.entities = [MagicMock(type="blockquote"), MagicMock(type="code")]
    assert _holds_result(result_msg) is True

    # .txt-фолбэк: у document нет text — edit_text на нём падает
    document_msg = MagicMock(document=MagicMock(), text=None)
    document_msg.entities = None
    assert _holds_result(document_msg) is True

    nav_msg = MagicMock(document=None, text="Выбери режим")
    nav_msg.entities = [MagicMock(type="bold")]
    assert _holds_result(nav_msg) is False

    plain_msg = MagicMock(document=None, text="обычный текст")
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
    from src.handlers._queue import is_busy, user_lock

    uid = 777
    assert is_busy(uid) is False
    lock = user_lock(uid)
    async with lock:
        assert is_busy(uid) is True
    assert is_busy(uid) is False


@pytest.mark.asyncio
async def test_acquire_or_none_is_atomic_against_double_tap():
    """Даблтап по кнопке: второй захват обязан вернуть None СРАЗУ, без await-окна,
    в котором оба тапа успевали пройти проверку (TOCTOU)."""
    from src.handlers._queue import acquire_or_none

    uid = 778
    first = await acquire_or_none(uid)
    assert first is not None
    second = await acquire_or_none(uid)
    assert second is None  # второй тап отбит
    first.release()
    third = await acquire_or_none(uid)
    assert third is not None
    third.release()


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


# ── раунд 3: атрибуция модели и склейка голосовых ──


def test_recent_transcripts_window_and_cap():
    from src.handlers._last import _transcripts, get_recent_transcripts, save_last_transcript

    _transcripts.clear()
    for i in range(7):
        save_last_transcript(9, f"кусок {i}")
    # хранится не больше _TRANSCRIPTS_PER_CHAT, отдаём последние limit штук
    assert get_recent_transcripts(9, window_sec=600, limit=3) == ["кусок 4", "кусок 5", "кусок 6"]
    # нулевое окно — ничего не считается «соседним»
    assert get_recent_transcripts(9, window_sec=0, limit=3) == []
    _transcripts.clear()


def test_merge_button_only_with_previous_voice():
    from src.ui.keyboards import result_keyboard

    with_merge = result_keyboard("polish", with_transcript=True, with_merge=True)
    labels = [b.text for row in with_merge.inline_keyboard for b in row]
    assert any("Склеить" in label for label in labels)

    without = result_keyboard("polish", with_transcript=True, with_merge=False)
    labels_without = [b.text for row in without.inline_keyboard for b in row]
    assert not any("Склеить" in label for label in labels_without)


@pytest.mark.asyncio
async def test_merge_prev_joins_transcripts_and_runs_mode(monkeypatch):
    """Кнопка склейки обрабатывает несколько голосовых как один текст,
    не запуская Whisper повторно."""
    from src.handlers import callbacks as cb
    from src.handlers._last import _transcripts, save_last_transcript

    _transcripts.clear()
    save_last_transcript(11, "первая часть мысли")
    save_last_transcript(11, "вторая часть мысли")

    run_mode_mock = AsyncMock(return_value=("склеенный результат", 10, "m", []))
    monkeypatch.setattr("src.handlers.voice._run_mode", run_mode_mock)

    callback = MagicMock()
    callback.from_user.id = 11
    callback.answer = AsyncMock()
    callback.message.chat.id = 11
    progress = MagicMock()
    progress.edit_text = AsyncMock()
    callback.message.answer = AsyncMock(return_value=progress)

    with patch.object(cb, "send_result", new=AsyncMock()) as sr:
        await cb.on_merge_prev(callback, MagicMock(), MagicMock())

    run_mode_mock.assert_awaited_once()
    joined = run_mode_mock.call_args.args[0]
    assert "первая часть мысли" in joined
    assert "вторая часть мысли" in joined
    sr.assert_awaited_once()
    _transcripts.clear()


@pytest.mark.asyncio
async def test_merge_prev_refuses_with_single_voice():
    from src.handlers import callbacks as cb
    from src.handlers._last import _transcripts, save_last_transcript

    _transcripts.clear()
    save_last_transcript(12, "одинокое голосовое")

    callback = MagicMock()
    callback.from_user.id = 12
    callback.answer = AsyncMock()
    callback.message.chat.id = 12
    callback.message.answer = AsyncMock()

    await cb.on_merge_prev(callback, MagicMock(), MagicMock())

    callback.message.answer.assert_not_awaited()
    assert "Нечего склеивать" in callback.answer.call_args.args[0]
    _transcripts.clear()


# ── находки критика раунда 3 ──


@pytest.mark.asyncio
async def test_chunk_permanent_failure_keeps_other_chunks(monkeypatch):
    """Устойчиво падающий чанк помечается, но час распознанной речи не теряется."""
    from src.handlers import voice as voice_mod

    monkeypatch.setattr(voice_mod, "split_audio_to_chunks", AsyncMock(return_value=[b"a", b"b"]))
    monkeypatch.setattr(voice_mod, "save_request", AsyncMock())
    monkeypatch.setattr(voice_mod.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(
        voice_mod,
        "run_polish",
        AsyncMock(return_value=MagicMock(text="ok", llm_ms=1, model="m")),
    )
    # Первый чанк ок, второй падает и на ретрае тоже.
    monkeypatch.setattr(
        voice_mod,
        "transcribe",
        AsyncMock(side_effect=[("часть один", 10), RuntimeError("429"), RuntimeError("429")]),
    )

    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.commit = AsyncMock()
    bot = MagicMock()
    bot.get_file = AsyncMock(return_value=MagicMock(file_path="v.ogg"))
    bot.download_file = AsyncMock(return_value=MagicMock(read=MagicMock(return_value=b"x")))

    media = MagicMock(duration=1200, file_id="f", file_size=1000)
    message = MagicMock()
    message.chat.id = 3
    message.answer = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    with patch.object(voice_mod, "send_result", new=AsyncMock()):
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
    transcript = voice_mod.run_polish.call_args.args[0]
    assert "часть один" in transcript
    assert "не распозналась" in transcript  # пропуск помечен явно


def test_request_too_large_raised_on_413_even_if_estimate_missed():
    """413 всегда даёт честную ошибку, а не «сервер недоступен, попробуй позже»."""
    from src.handlers.text import error_message_for
    from src.services.llm import RequestTooLargeError
    from src.ui.messages import REQUEST_TOO_LARGE

    assert error_message_for(RequestTooLargeError("413")) == REQUEST_TOO_LARGE
