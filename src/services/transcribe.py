import asyncio
import contextlib
import os
import tempfile
import time

import structlog
from groq import AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.services.llm import is_model_unavailable_error, is_rate_limit_error
from src.storage.models import TranscriptionCache

log = structlog.get_logger()

_FFMPEG_TIMEOUT_SEC = 180  # cap ffmpeg time for splitting long audio


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

    On rate-limit errors, retries rotate through other configured Groq keys
    (via settings.get_all_groq_keys()) to spread load across accounts.
    """
    if file_id and session and settings.enable_transcription_cache:
        try:
            if force_retranscribe:
                cached = await session.get(TranscriptionCache, file_id)
                if cached:
                    await session.delete(cached)
                    await session.flush()
            else:
                cached = await session.get(TranscriptionCache, file_id)
                if cached:
                    return cached.transcript, 0
        except Exception as exc:
            # Кэш — оптимизация; мёртвая БД не должна ломать распознавание.
            log.warning("transcription_cache_unavailable", error=str(exc))
            with contextlib.suppress(Exception):
                await session.rollback()
            session = None

    wanted_model = model or settings.whisper_model
    models_to_try = [wanted_model] + [
        m for m in settings.whisper_model_fallbacks_list if m != wanted_model
    ]
    stt_model = models_to_try[0]
    current_key = api_key
    client = AsyncGroq(api_key=current_key)
    started = time.monotonic()
    last_exc: Exception | None = None

    for attempt in range(3):
        try:
            result = await client.audio.transcriptions.create(
                file=("voice.ogg", audio_bytes),
                model=stt_model,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            text = result.text

            if file_id and session and settings.enable_transcription_cache:
                try:
                    existing = await session.get(TranscriptionCache, file_id)
                    if existing:
                        existing.transcript = text
                    else:
                        session.add(TranscriptionCache(file_id=file_id, transcript=text))
                except Exception as exc:
                    # Транскрипт уже получен — падение записи кэша не должно
                    # уводить нас на повторный прогон Whisper.
                    log.warning("transcription_cache_save_failed", error=str(exc))
                    with contextlib.suppress(Exception):
                        await session.rollback()

            return text, elapsed_ms
        except Exception as e:
            last_exc = e
            rate_limited = is_rate_limit_error(e)
            log.warning(
                "stt_retry",
                attempt=attempt + 1,
                error=str(e),
                rate_limited=rate_limited,
            )
            if is_model_unavailable_error(e):
                # Модель STT отключена провайдером — переключаемся на запасную
                # (whisper-large-v3-turbo) вместо бессмысленных ретраев.
                idx = models_to_try.index(stt_model)
                if idx + 1 < len(models_to_try):
                    stt_model = models_to_try[idx + 1]
                    log.warning("stt_fallback_model", model=stt_model)
                    continue
            if attempt < 2:
                if rate_limited:
                    alt_keys = [k for k in settings.get_all_groq_keys() if k != current_key]
                    if alt_keys:
                        current_key = alt_keys[attempt % len(alt_keys)]
                        client = AsyncGroq(api_key=current_key)
                        log.info("stt_key_rotation", attempt=attempt + 1)
                await asyncio.sleep(2 * (attempt + 1))

    raise last_exc  # type: ignore[misc]


async def split_audio_to_chunks(audio_bytes: bytes, chunk_sec: int) -> list[bytes]:
    """Split arbitrary audio into ~chunk_sec slices via ffmpeg segment muxer.

    Returns ogg/opus 64k-encoded byte slices in order. One ffmpeg invocation
    produces all chunks at once (no per-chunk fork overhead). Returns an
    empty list on any failure (caller should handle gracefully).
    """
    in_fd, in_path = tempfile.mkstemp(suffix=".audio")
    os.close(in_fd)
    work_dir = tempfile.mkdtemp(prefix="voice_chunks_")
    pattern = os.path.join(work_dir, "chunk_%04d.ogg")

    async def _run_segment(codec_args: list[str]) -> bool:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            in_path,
            "-vn",
            *codec_args,
            "-f",
            "segment",
            "-segment_time",
            str(chunk_sec),
            "-reset_timestamps",
            "1",
            pattern,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=_FFMPEG_TIMEOUT_SEC)
        except TimeoutError:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            log.error("ffmpeg_split_timeout", timeout=_FFMPEG_TIMEOUT_SEC)
            return False
        if proc.returncode != 0:
            log.warning("ffmpeg_split_failed", returncode=proc.returncode, codec=codec_args)
            return False
        return True

    def _collect() -> list[bytes]:
        files = sorted(f for f in os.listdir(work_dir) if f.startswith("chunk_"))
        out: list[bytes] = []
        for name in files:
            with open(os.path.join(work_dir, name), "rb") as f:
                out.append(f.read())
        return out

    try:
        with open(in_path, "wb") as f:
            f.write(audio_bytes)

        # Телеграмный voice — уже ogg/opus: копирование потока вместо
        # перекодировки на порядок быстрее (критично на слабом CPU Render free,
        # где транскодинг часового аудио не влезал в таймаут).
        if await _run_segment(["-c:a", "copy"]):
            chunks = _collect()
            if chunks:
                return chunks

        # Не-opus вход (mp3-файл, звук из видео) — полноценная перекодировка.
        for name in os.listdir(work_dir):
            with contextlib.suppress(OSError):
                os.remove(os.path.join(work_dir, name))
        if await _run_segment(["-acodec", "libopus", "-b:a", "64k"]):
            return _collect()
        return []
    except Exception:
        log.exception("split_audio_error")
        return []
    finally:
        with contextlib.suppress(OSError):
            os.unlink(in_path)
        if os.path.isdir(work_dir):
            for name in os.listdir(work_dir):
                with contextlib.suppress(OSError):
                    os.unlink(os.path.join(work_dir, name))
        with contextlib.suppress(OSError):
            os.rmdir(work_dir)


async def extract_audio_from_video(video_bytes: bytes) -> bytes | None:
    """Extract the audio track from a video/video_note container via ffmpeg.

    Returns ogg/opus 64k-encoded bytes, or None on failure.
    """
    in_fd, in_path = tempfile.mkstemp(suffix=".mp4")
    out_fd, out_path = tempfile.mkstemp(suffix=".ogg")
    try:
        os.close(out_fd)
        with os.fdopen(in_fd, "wb") as f:
            f.write(video_bytes)

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-i",
            in_path,
            "-vn",
            "-acodec",
            "libopus",
            "-b:a",
            "64k",
            out_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=30)
        except TimeoutError:
            proc.kill()
            with contextlib.suppress(Exception):
                await proc.wait()
            log.error("ffmpeg_extract_timeout", timeout=30)
            return None

        if proc.returncode != 0:
            log.error("ffmpeg_extract_failed", returncode=proc.returncode)
            return None

        with open(out_path, "rb") as f:
            return f.read()
    except Exception:
        log.exception("extract_audio_error")
        return None
    finally:
        for path in (in_path, out_path):
            with contextlib.suppress(OSError):
                os.unlink(path)
