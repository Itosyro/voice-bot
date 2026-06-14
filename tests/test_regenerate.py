from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.handlers import voice
from src.handlers._last import LastRequest, get_last, save_last


def _make_media(duration=10, file_id="f1", file_size=1000):
    m = MagicMock()
    m.duration = duration
    m.file_id = file_id
    m.file_size = file_size
    return m


@pytest.fixture
def bot_mock():
    bot = MagicMock()
    file_info = MagicMock()
    file_info.file_path = "voice/f.ogg"
    bot.get_file = AsyncMock(return_value=file_info)
    file_bytes = MagicMock()
    file_bytes.read = MagicMock(return_value=b"audio")
    bot.download_file = AsyncMock(return_value=file_bytes)
    return bot


@pytest.mark.asyncio
async def test_regenerate_voice_busts_cache(bot_mock, monkeypatch):
    """Повтор must re-transcribe from scratch (force_retranscribe=True), not reuse cache."""
    transcribe_mock = AsyncMock(return_value=("fresh transcript", 100))
    monkeypatch.setattr(voice, "transcribe", transcribe_mock)
    monkeypatch.setattr(voice, "split_audio_to_chunks", AsyncMock())
    monkeypatch.setattr(voice, "save_request", AsyncMock())
    monkeypatch.setattr(
        voice, "run_polish", AsyncMock(return_value=MagicMock(text="r", llm_ms=1, model="m"))
    )

    message = MagicMock()
    message.answer = AsyncMock(return_value=MagicMock(edit_text=AsyncMock()))

    last = LastRequest(
        input_type="voice",
        mode="polish",
        style="polish_default",
        target_lang="en",
        db_user_id=7,
        media=_make_media(),
        is_video=False,
    )

    with patch.object(voice, "send_result", new=AsyncMock()):
        await voice.regenerate_voice(message, bot_mock, MagicMock(), MagicMock(), last)

    transcribe_mock.assert_awaited_once()
    assert transcribe_mock.call_args.kwargs.get("force_retranscribe") is True


def test_last_request_store_roundtrip():
    req = LastRequest(
        input_type="text", mode="polish", style=None, target_lang="en", db_user_id=1, text="hi"
    )
    save_last(999, req)
    assert get_last(999) is req
    assert get_last(123456789) is None  # unseen user
