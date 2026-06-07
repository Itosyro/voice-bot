import asyncio
import time

from groq import AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.storage.models import TranscriptionCache


async def transcribe(
    audio_bytes: bytes,
    api_key: str,
    file_id: str | None = None,
    session: AsyncSession | None = None,
    model: str | None = None,
    force_retranscribe: bool = False,
) -> tuple[str, int]:
    """Transcribe audio bytes via Groq Whisper. Returns (text, elapsed_ms).

    If force_retranscribe=True the cache entry is deleted first so Whisper
    always re-runs — useful when the user wants a fresh attempt after a
    poor-quality transcription.
    """
    if file_id and session and settings.enable_transcription_cache:
        if force_retranscribe:
            cached = await session.get(TranscriptionCache, file_id)
            if cached:
                await session.delete(cached)
                await session.flush()
        else:
            cached = await session.get(TranscriptionCache, file_id)
            if cached:
                return cached.transcript, 0

    client = AsyncGroq(api_key=api_key)
    started = time.monotonic()
    last_exc: Exception | None = None

    for attempt in range(2):
        try:
            result = await client.audio.transcriptions.create(
                file=("voice.ogg", audio_bytes),
                model=model or settings.whisper_model,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            text = result.text

            if file_id and session and settings.enable_transcription_cache:
                existing = await session.get(TranscriptionCache, file_id)
                if existing:
                    existing.transcript = text
                else:
                    session.add(TranscriptionCache(file_id=file_id, transcript=text))

            return text, elapsed_ms
        except Exception as e:
            last_exc = e
            if attempt == 0:
                await asyncio.sleep(2)

    raise last_exc  # type: ignore[misc]
