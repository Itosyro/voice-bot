from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from src.handlers import voice


def _make_message(*, voice_obj=None, audio=None, video_note=None, video=None, user_id=1):
    message = MagicMock(spec=Message)
    message.voice = voice_obj
    message.audio = audio
    message.video_note = video_note
    message.video = video
    message.from_user = MagicMock(id=user_id, username="tester", first_name="Test")
    message.chat = MagicMock(id=123)
    message.answer = AsyncMock()
    return message


def _make_media(duration: int, file_id: str = "file123", file_size: int = 1000):
    media = MagicMock()
    media.duration = duration
    media.file_id = file_id
    media.file_size = file_size
    return media


def _make_user(mode: str = "polish", style: str | None = None, target_lang: str = "en"):
    user = MagicMock()
    user.id = 1
    user.default_mode = mode
    user.default_style = style
    user.target_lang = target_lang
    return user


@pytest.fixture
def common_mocks(monkeypatch):
    """Patch out DB/session/skills dependencies shared by all handler tests."""
    session = MagicMock()
    skills_db = MagicMock()
    bot = MagicMock()

    file_info = MagicMock()
    file_info.file_path = "voice/file_123.ogg"
    bot.get_file = AsyncMock(return_value=file_info)

    file_bytes = MagicMock()
    file_bytes.read = MagicMock(return_value=b"raw-audio-bytes")
    bot.download_file = AsyncMock(return_value=file_bytes)

    monkeypatch.setattr(voice, "save_request", AsyncMock())
    monkeypatch.setattr(voice, "make_draft_callback", lambda *a, **k: AsyncMock())

    return {"session": session, "skills_db": skills_db, "bot": bot}


@pytest.mark.asyncio
async def test_short_voice_uses_single_shot_transcribe(common_mocks, monkeypatch):
    """Duration below chunk_threshold_sec should use the single-shot transcribe path."""
    user = _make_user(mode="polish")
    monkeypatch.setattr(voice, "get_or_create_user", AsyncMock(return_value=user))

    transcribe_mock = AsyncMock(return_value=("hello world", 100))
    split_mock = AsyncMock()
    monkeypatch.setattr(voice, "transcribe", transcribe_mock)
    monkeypatch.setattr(voice, "split_audio_to_chunks", split_mock)

    run_polish_result = MagicMock(text="polished", llm_ms=50, model="m")
    monkeypatch.setattr(voice, "run_polish", AsyncMock(return_value=run_polish_result))

    message = _make_message(voice_obj=_make_media(duration=30))
    message.answer = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    with patch.object(voice, "send_result", new=AsyncMock()):
        await voice.handle_voice(
            message, common_mocks["bot"], common_mocks["session"], common_mocks["skills_db"]
        )

    transcribe_mock.assert_awaited_once()
    assert transcribe_mock.call_args.kwargs.get("file_id") == "file123"
    split_mock.assert_not_called()


@pytest.mark.asyncio
async def test_long_voice_triggers_chunked_pipeline(common_mocks, monkeypatch):
    """Duration above chunk_threshold_sec should split into chunks and transcribe sequentially."""
    user = _make_user(mode="polish")
    monkeypatch.setattr(voice, "get_or_create_user", AsyncMock(return_value=user))

    chunks = [b"chunk1", b"chunk2", b"chunk3"]
    split_mock = AsyncMock(return_value=chunks)
    monkeypatch.setattr(voice, "split_audio_to_chunks", split_mock)

    transcribe_mock = AsyncMock(
        side_effect=[("part one", 100), ("part two", 100), ("part three", 100)]
    )
    monkeypatch.setattr(voice, "transcribe", transcribe_mock)
    monkeypatch.setattr(voice, "asyncio", voice.asyncio)
    monkeypatch.setattr(voice.asyncio, "sleep", AsyncMock())

    run_polish_result = MagicMock(text="polished", llm_ms=50, model="m")
    monkeypatch.setattr(voice, "run_polish", AsyncMock(return_value=run_polish_result))

    duration = voice.settings.chunk_threshold_sec + 1
    message = _make_message(voice_obj=_make_media(duration=duration))
    progress_msg = MagicMock(edit_text=AsyncMock())
    message.answer = AsyncMock(return_value=progress_msg)

    with patch.object(voice, "send_result", new=AsyncMock()) as send_result_mock:
        await voice.handle_voice(
            message, common_mocks["bot"], common_mocks["session"], common_mocks["skills_db"]
        )

    split_mock.assert_awaited_once()
    assert split_mock.call_args.args[1] == voice.settings.chunk_duration_sec

    # Transcribed each chunk sequentially without file_id caching.
    assert transcribe_mock.await_count == 3
    for call in transcribe_mock.call_args_list:
        assert "file_id" not in call.kwargs

    # Progress message updated with chunk progress.
    progress_texts = [c.args[0] for c in progress_msg.edit_text.call_args_list]
    assert any("1/3" in t for t in progress_texts)
    assert any("2/3" in t for t in progress_texts)
    assert any("3/3" in t for t in progress_texts)

    # Concatenated transcript passed to the mode dispatch.
    run_polish_call = voice.run_polish.call_args
    combined_transcript = run_polish_call.args[0]
    assert "part one" in combined_transcript
    assert "part two" in combined_transcript
    assert "part three" in combined_transcript

    send_result_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_voice_exceeding_max_duration_is_rejected(common_mocks, monkeypatch):
    """Duration above max_voice_duration_sec should be rejected with VOICE_TOO_LONG."""
    user = _make_user(mode="polish")
    monkeypatch.setattr(voice, "get_or_create_user", AsyncMock(return_value=user))

    split_mock = AsyncMock()
    transcribe_mock = AsyncMock()
    monkeypatch.setattr(voice, "split_audio_to_chunks", split_mock)
    monkeypatch.setattr(voice, "transcribe", transcribe_mock)

    duration = voice.settings.max_voice_duration_sec + 1
    message = _make_message(voice_obj=_make_media(duration=duration))

    await voice.handle_voice(
        message, common_mocks["bot"], common_mocks["session"], common_mocks["skills_db"]
    )

    message.answer.assert_awaited_once()
    sent_text = message.answer.call_args.args[0]
    assert "слишком длинное" in sent_text

    split_mock.assert_not_called()
    transcribe_mock.assert_not_called()


@pytest.mark.asyncio
async def test_video_note_dispatches_through_same_pipeline(common_mocks, monkeypatch):
    """video_note messages should extract audio and go through the same transcribe pipeline."""
    user = _make_user(mode="translator")
    monkeypatch.setattr(voice, "get_or_create_user", AsyncMock(return_value=user))

    extract_mock = AsyncMock(return_value=b"extracted-audio")
    monkeypatch.setattr(voice, "extract_audio_from_video", extract_mock)

    transcribe_mock = AsyncMock(return_value=("video note transcript", 100))
    split_mock = AsyncMock()
    monkeypatch.setattr(voice, "transcribe", transcribe_mock)
    monkeypatch.setattr(voice, "split_audio_to_chunks", split_mock)

    run_translator_result = MagicMock(text="translated", llm_ms=50, model="m")
    monkeypatch.setattr(voice, "run_translator", AsyncMock(return_value=run_translator_result))

    message = _make_message(video_note=_make_media(duration=20))
    message.answer = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    with patch.object(voice, "send_result", new=AsyncMock()):
        await voice.handle_voice(
            message, common_mocks["bot"], common_mocks["session"], common_mocks["skills_db"]
        )

    extract_mock.assert_awaited_once_with(b"raw-audio-bytes")
    transcribe_mock.assert_awaited_once()
    assert transcribe_mock.call_args.args[0] == b"extracted-audio"
    split_mock.assert_not_called()
    voice.run_translator.assert_awaited_once()
