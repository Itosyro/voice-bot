import asyncio
import time

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.services.llm import get_client, is_rate_limit_error
from src.storage.models import TranscriptionCache

log = structlog.get_logger()

_STT_MAX_RETRIES = 2
_STT_RETRY_DELAY = 2.0


async def transcribe(
    audio_bytes: bytes,
    api_key: str,
    file_id: str | None = None,
    session: AsyncSession | None = None,
    model: str | None = None,
) -> tuple[str, int]:
    """Transcribe audio bytes via Groq Whisper with retry. Returns (text, elapsed_ms)."""
    if file_id and session and settings.enable_transcription_cache:
        cached = await session.get(TranscriptionCache, file_id)
        if cached:
            return cached.transcript, 0

    current_key = api_key
    client = get_client(current_key)
    started = time.monotonic()
    last_exc: Exception | None = None

    for attempt in range(_STT_MAX_RETRIES + 1):
        try:
            result = await client.audio.transcriptions.create(
                file=("voice.ogg", audio_bytes),
                model=model or settings.whisper_model,
                prompt=(
                    "Транскрибируй дословно. Не цензурируй. "
                    "Маты и нецензурную лексику пиши как есть."
                ),
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            text = result.text

            if file_id and session and settings.enable_transcription_cache:
                session.add(TranscriptionCache(file_id=file_id, transcript=text))

            return text, elapsed_ms
        except Exception as exc:
            last_exc = exc
            rate_limited = is_rate_limit_error(exc)
            log.warning(
                "stt_retry",
                attempt=attempt + 1,
                error=str(exc),
                rate_limited=rate_limited,
            )
            if attempt < _STT_MAX_RETRIES:
                if rate_limited:
                    alt_keys = [k for k in settings.get_all_groq_keys() if k != current_key]
                    if alt_keys:
                        current_key = alt_keys[attempt % len(alt_keys)]
                        client = get_client(current_key)
                        log.info("stt_key_rotation", attempt=attempt + 1)
                await asyncio.sleep(_STT_RETRY_DELAY * (attempt + 1))

    raise last_exc  # type: ignore[misc]
