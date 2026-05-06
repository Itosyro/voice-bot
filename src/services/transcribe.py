import time

from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.services.llm import _get_client
from src.storage.models import TranscriptionCache


async def transcribe(
    audio_bytes: bytes,
    api_key: str,
    file_id: str | None = None,
    session: AsyncSession | None = None,
    model: str | None = None,
) -> tuple[str, int]:
    """Transcribe audio bytes via Groq Whisper. Returns (text, elapsed_ms)."""
    if file_id and session and settings.enable_transcription_cache:
        cached = await session.get(TranscriptionCache, file_id)
        if cached:
            return cached.transcript, 0

    client = _get_client(api_key)
    started = time.monotonic()
    result = await client.audio.transcriptions.create(
        file=("voice.ogg", audio_bytes),
        model=model or settings.whisper_model,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)

    text = result.text

    if file_id and session and settings.enable_transcription_cache:
        session.add(TranscriptionCache(file_id=file_id, transcript=text))

    return text, elapsed_ms
