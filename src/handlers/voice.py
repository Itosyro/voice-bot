import asyncio
import contextlib
import math
import os
import tempfile
import time

import structlog
from aiogram import Bot, F, Router
from aiogram.types import Audio, Message, VideoNote, Voice
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.services.llm import is_rate_limit_error
from src.services.polish import run_polish
from src.services.prompt_eng import run_prompt_eng
from src.services.skills_db import SkillsDB
from src.services.summary import run_summary
from src.services.transcribe import split_audio_to_chunks, transcribe
from src.services.translator import run_translator
from src.storage.history import save_request
from src.storage.models import TranscriptionCache, User
from src.storage.users import get_or_create_user, update_user_settings
from src.ui.keyboards import mode_keyboard, result_keyboard
from src.ui.messages import (
    CHUNK_FINAL_PROCESSING,
    CHUNK_PROCESSING,
    CHUNK_RATE_LIMIT_PAUSE,
    CHUNK_TRANSCRIBING,
    GROQ_ERROR,
    HUMANIZER_VOICE_ERROR,
    LONG_VOICE_DONE,
    LONG_VOICE_NOTICE,
    LONG_VOICE_PARTIAL,
    VOICE_TOO_LONG,
)
from src.utils import send_chunk, send_result

log = structlog.get_logger()

router = Router()

_RATE_LIMIT_PAUSE_SEC = 25


async def _process_voice(
    message: Message,
    voice_message: Message,
    bot: Bot,
    session: AsyncSession,
    skills_db: SkillsDB,
) -> None:
    """Core voice processing logic."""
    user_tg = message.from_user
    if not user_tg:
        return

    user = await get_or_create_user(
        session,
        telegram_user_id=user_tg.id,
        username=user_tg.username,
        first_name=user_tg.first_name,
    )

    mode = user.default_mode
    style = user.default_style

    if not mode:
        mode = "polish"
        style = "polish_default"
        await update_user_settings(
            session,
            telegram_user_id=user_tg.id,
            default_mode=mode,
            default_style=style,
        )

    if mode == "humanizer":
        await message.answer(HUMANIZER_VOICE_ERROR, reply_markup=mode_keyboard(), parse_mode="HTML")
        return

    voice = voice_message.voice or voice_message.audio
    video_note = voice_message.video_note if not voice else None

    if not voice and not video_note:
        return

    duration = (voice.duration if voice else video_note.duration) or 0
    if duration > settings.max_voice_duration_sec:
        await message.answer(
            VOICE_TOO_LONG.format(max_min=settings.max_voice_duration_sec // 60),
            parse_mode="HTML",
        )
        return

    if duration > settings.chunk_threshold_sec:
        await _process_long_voice(
            message=message,
            voice=voice,
            video_note=video_note,
            duration=duration,
            bot=bot,
            session=session,
            user=user,
            mode=mode,
            style=style,
            skills_db=skills_db,
        )
        return

    started = time.monotonic()
    progress_msg = await message.answer(f"Распознаю аудио ({duration} сек)…")

    try:
        file_id = voice.file_id if voice else video_note.file_id  # type: ignore[union-attr]
        file = await bot.get_file(file_id)
        if not file.file_path:
            await progress_msg.edit_text("⚠ Не удалось скачать аудио.")
            return
        file_bytes = await bot.download_file(file.file_path)
        if not file_bytes:
            await progress_msg.edit_text("⚠ Не удалось скачать аудио.")
            return
        raw_bytes = file_bytes.read()

        if video_note:
            audio_bytes = await _extract_audio_from_video(raw_bytes)
            if not audio_bytes:
                await progress_msg.edit_text("⚠ Не удалось извлечь аудио из кружочка.")
                return
        else:
            audio_bytes = raw_bytes

        transcript, stt_ms = await transcribe(
            audio_bytes,
            api_key=settings.get_transcription_key(),
            file_id=file_id,
            session=session,
        )

        if not transcript or not transcript.strip():
            await progress_msg.edit_text(
                "⚠ Не удалось распознать речь. Попробуй записать чётче.",
                reply_markup=mode_keyboard(),
            )
            return

        mode_label = {
            "polish": "Полирую",
            "prompt": "Создаю промпт",
            "translator": "Перевожу",
            "summary": "Создаю саммари",
        }
        await progress_msg.edit_text(f"{mode_label.get(mode, 'Обрабатываю')}…")

        result_text = ""
        llm_ms = 0
        model_used = ""

        if mode == "polish":
            r = await run_polish(transcript, sub_style=style or "polish_default")
            result_text, llm_ms, model_used = r.text, r.llm_ms, r.model
        elif mode == "prompt":
            r2 = await run_prompt_eng(
                transcript,
                sub_style=style or "prompt_general",
                skills_db=skills_db,
            )
            result_text, llm_ms, model_used = r2.text, r2.llm_ms, r2.model
        elif mode == "translator":
            r3 = await run_translator(transcript, target_lang=user.target_lang or "en")
            result_text, llm_ms, model_used = r3.text, r3.llm_ms, r3.model
        elif mode == "summary":
            r4 = await run_summary(transcript)
            result_text, llm_ms, model_used = r4.text, r4.llm_ms, r4.model

        if not result_text or not result_text.strip():
            await progress_msg.edit_text(
                "⚠ Не удалось обработать текст. Попробуй ещё раз.",
                reply_markup=mode_keyboard(),
            )
            return

        total_ms = int((time.monotonic() - started) * 1000)

        input_type = "video_note" if video_note else "voice"
        await save_request(
            session,
            user_id=user.id,
            mode=mode,
            style=style or "default",
            input_type=input_type,
            input_length=duration,
            input_preview=transcript[:200],
            output_text=result_text[:5000],
            output_length=len(result_text),
            llm_model=model_used,
            transcription_ms=stt_ms,
            llm_ms=llm_ms,
            total_ms=total_ms,
        )

        await send_result(progress_msg, result_text, result_keyboard(mode), mode)

    except Exception as exc:
        log.exception("voice_handler_error")
        total_ms = int((time.monotonic() - started) * 1000)
        with contextlib.suppress(Exception):
            await save_request(
                session,
                user_id=user.id,
                mode=mode,
                style=style or "default",
                input_type="video_note" if video_note else "voice",
                total_ms=total_ms,
                error=str(exc)[:500],
            )
        error_msg = GROQ_ERROR
        if is_rate_limit_error(exc):
            error_msg = "⏳ Сервер перегружен. Подожди минуту и попробуй снова."
        elif "model" in str(exc).lower() and "not found" in str(exc).lower():
            error_msg = "⚠ Модель временно недоступна. Попробуй другой режим."
        await progress_msg.edit_text(error_msg, reply_markup=mode_keyboard())


async def _process_long_voice(
    message: Message,
    voice: Voice | Audio | None,
    video_note: VideoNote | None,
    duration: int,
    bot: Bot,
    session: AsyncSession,
    user: User,
    mode: str,
    style: str | None,
    skills_db: SkillsDB,
) -> None:
    """Chunked pipeline for long voices (> chunk_threshold_sec).

    polish/translator: per-chunk LLM, streamed to user as each chunk completes.
    summary/prompt: transcribe all chunks first, then a single LLM call on the
    combined text (these modes need full context).
    On cache hit: fast path — single LLM call on full transcript, send_result.
    """
    started = time.monotonic()
    if voice is not None:
        file_id: str = voice.file_id
    elif video_note is not None:
        file_id = video_note.file_id
    else:
        return

    chunk_sec = settings.chunk_duration_sec
    n_planned = max(1, math.ceil(duration / chunk_sec))
    minutes = max(1, math.ceil(duration / 60))
    chunk_min = max(1, chunk_sec // 60)
    target_lang = user.target_lang or "en"
    input_type = "video_note" if video_note else "voice"

    progress_msg = await message.answer(
        LONG_VOICE_NOTICE.format(minutes=minutes, n=n_planned, chunk_min=chunk_min),
        parse_mode="HTML",
    )

    try:
        if file_id and settings.enable_transcription_cache:
            cached = await session.get(TranscriptionCache, file_id)
            if cached and cached.transcript and cached.transcript.strip():
                await _long_voice_cached_fast_path(
                    progress_msg=progress_msg,
                    cached_transcript=cached.transcript,
                    mode=mode,
                    style=style,
                    target_lang=target_lang,
                    skills_db=skills_db,
                    session=session,
                    user=user,
                    duration=duration,
                    input_type=input_type,
                    started=started,
                )
                return

        file = await bot.get_file(file_id)
        if not file.file_path:
            await progress_msg.edit_text("⚠ Не удалось скачать аудио.")
            return
        file_bytes = await bot.download_file(file.file_path)
        if not file_bytes:
            await progress_msg.edit_text("⚠ Не удалось скачать аудио.")
            return
        raw_bytes = file_bytes.read()

        if video_note is not None:
            audio_bytes = await _extract_audio_from_video(raw_bytes)
            if not audio_bytes:
                await progress_msg.edit_text("⚠ Не удалось извлечь аудио из кружочка.")
                return
        else:
            audio_bytes = raw_bytes

        chunks = await split_audio_to_chunks(audio_bytes, chunk_sec)
        if not chunks:
            await progress_msg.edit_text(
                "⚠ Не удалось разрезать аудио. Попробуй короче или другим форматом.",
                reply_markup=mode_keyboard(),
            )
            return

        n = len(chunks)
        transcripts: list[str] = []
        per_chunk_results: list[str] = []
        final_text = ""
        final_model = ""

        for k, chunk_bytes in enumerate(chunks, 1):
            with contextlib.suppress(Exception):
                await progress_msg.edit_text(
                    CHUNK_TRANSCRIBING.format(k=k, n=n),
                    parse_mode="HTML",
                )

            transcript = await _transcribe_chunk_with_retry(chunk_bytes, k, n, progress_msg)
            if not (transcript and transcript.strip()):
                with contextlib.suppress(Exception):
                    await message.answer(
                        LONG_VOICE_PARTIAL.format(k=k, n=n),
                        parse_mode="HTML",
                    )
                if k < n:
                    await asyncio.sleep(settings.chunk_throttle_sec)
                continue

            transcripts.append(transcript.strip())

            if mode in ("polish", "translator"):
                with contextlib.suppress(Exception):
                    await progress_msg.edit_text(
                        CHUNK_PROCESSING.format(k=k, n=n),
                        parse_mode="HTML",
                    )
                chunk_text, chunk_model = await _run_mode_llm(
                    text=transcript,
                    mode=mode,
                    style=style,
                    target_lang=target_lang,
                    skills_db=skills_db,
                )
                if chunk_text and chunk_text.strip():
                    per_chunk_results.append(chunk_text.strip())
                    if not final_model:
                        final_model = chunk_model
                    is_last = k == n
                    await send_chunk(
                        target=message,
                        header=f"<b>Часть {k}/{n}</b>",
                        text=chunk_text.strip(),
                        reply_markup=result_keyboard(mode) if is_last else None,
                    )

            if k < n:
                await asyncio.sleep(settings.chunk_throttle_sec)

        combined_transcript = "\n\n".join(transcripts)
        if file_id and settings.enable_transcription_cache and combined_transcript.strip():
            try:
                session.add(TranscriptionCache(file_id=file_id, transcript=combined_transcript))
                await session.flush()
            except IntegrityError:
                await session.rollback()
            except Exception:
                log.exception("long_voice_cache_failed")

        if mode in ("summary", "prompt"):
            combined = combined_transcript.strip()
            if not combined:
                await progress_msg.edit_text(
                    "⚠ Не удалось распознать речь. Попробуй чётче.",
                    reply_markup=mode_keyboard(),
                )
                return
            with contextlib.suppress(Exception):
                await progress_msg.edit_text(
                    CHUNK_FINAL_PROCESSING.format(total_chars=len(combined)),
                    parse_mode="HTML",
                )
            final_text, final_model = await _run_mode_llm(
                text=combined,
                mode=mode,
                style=style,
                target_lang=target_lang,
                skills_db=skills_db,
            )
            if not (final_text and final_text.strip()):
                await progress_msg.edit_text(
                    "⚠ Не удалось обработать текст.",
                    reply_markup=mode_keyboard(),
                )
                return
            await send_result(progress_msg, final_text, result_keyboard(mode), mode)
        else:
            n_done = len(per_chunk_results)
            if n_done == 0:
                await progress_msg.edit_text(
                    "⚠ Ни одну часть не удалось обработать. Попробуй ещё раз.",
                    reply_markup=mode_keyboard(),
                )
                return
            with contextlib.suppress(Exception):
                await progress_msg.edit_text(
                    LONG_VOICE_DONE.format(n=n_done),
                    parse_mode="HTML",
                    reply_markup=mode_keyboard(),
                )

        total_ms = int((time.monotonic() - started) * 1000)
        result_text = (
            "\n\n".join(per_chunk_results) if mode in ("polish", "translator") else final_text
        )
        with contextlib.suppress(Exception):
            await save_request(
                session,
                user_id=user.id,
                mode=mode,
                style=style or "default",
                input_type=input_type,
                input_length=duration,
                input_preview=combined_transcript[:200],
                output_text=result_text[:5000],
                output_length=len(result_text),
                llm_model=final_model or settings.llm_model_default,
                transcription_ms=0,
                llm_ms=0,
                total_ms=total_ms,
            )

    except Exception as exc:
        log.exception("long_voice_error")
        with contextlib.suppress(Exception):
            await save_request(
                session,
                user_id=user.id,
                mode=mode,
                style=style or "default",
                input_type=input_type,
                input_length=duration,
                total_ms=int((time.monotonic() - started) * 1000),
                error=str(exc)[:500],
            )
        error_msg = GROQ_ERROR
        if is_rate_limit_error(exc):
            error_msg = "⏳ Сервер перегружен. Подожди минуту и попробуй снова."
        with contextlib.suppress(Exception):
            await progress_msg.edit_text(error_msg, reply_markup=mode_keyboard())


async def _long_voice_cached_fast_path(
    progress_msg: Message,
    cached_transcript: str,
    mode: str,
    style: str | None,
    target_lang: str,
    skills_db: SkillsDB,
    session: AsyncSession,
    user: User,
    duration: int,
    input_type: str,
    started: float,
) -> None:
    """Replay path: STT cached, run mode LLM once on full text and send_result."""
    combined = cached_transcript.strip()
    with contextlib.suppress(Exception):
        await progress_msg.edit_text(
            CHUNK_FINAL_PROCESSING.format(total_chars=len(combined)),
            parse_mode="HTML",
        )
    final_text, final_model = await _run_mode_llm(
        text=combined,
        mode=mode,
        style=style,
        target_lang=target_lang,
        skills_db=skills_db,
    )
    if not (final_text and final_text.strip()):
        await progress_msg.edit_text(
            "⚠ Не удалось обработать текст.",
            reply_markup=mode_keyboard(),
        )
        return
    await send_result(progress_msg, final_text, result_keyboard(mode), mode)
    total_ms = int((time.monotonic() - started) * 1000)
    with contextlib.suppress(Exception):
        await save_request(
            session,
            user_id=user.id,
            mode=mode,
            style=style or "default",
            input_type=input_type,
            input_length=duration,
            input_preview=combined[:200],
            output_text=final_text[:5000],
            output_length=len(final_text),
            llm_model=final_model or settings.llm_model_default,
            transcription_ms=0,
            llm_ms=0,
            total_ms=total_ms,
        )


async def _transcribe_chunk_with_retry(
    chunk_bytes: bytes, k: int, n: int, progress_msg: Message
) -> str:
    """Transcribe one audio chunk; on rate limit, pause once and retry."""
    try:
        text, _ = await transcribe(chunk_bytes, api_key=settings.get_transcription_key())
        return text
    except Exception as exc:
        log.warning("long_voice_chunk_stt_failed", chunk=k, error=str(exc))
        if not is_rate_limit_error(exc):
            return ""
        with contextlib.suppress(Exception):
            await progress_msg.edit_text(
                CHUNK_RATE_LIMIT_PAUSE.format(k=k, n=n, pause=_RATE_LIMIT_PAUSE_SEC),
                parse_mode="HTML",
            )
        await asyncio.sleep(_RATE_LIMIT_PAUSE_SEC)
        try:
            text, _ = await transcribe(chunk_bytes, api_key=settings.get_transcription_key())
            return text
        except Exception:
            log.exception("long_voice_chunk_stt_retry_failed", chunk=k)
            return ""


async def _run_mode_llm(
    text: str,
    mode: str,
    style: str | None,
    target_lang: str,
    skills_db: SkillsDB,
) -> tuple[str, str]:
    """Run mode LLM on full or chunked text. Returns (output, model_used)."""
    try:
        if mode == "polish":
            r = await run_polish(text, sub_style=style or "polish_default")
            return r.text, r.model
        if mode == "translator":
            r3 = await run_translator(text, target_lang=target_lang)
            return r3.text, r3.model
        if mode == "summary":
            r4 = await run_summary(text)
            return r4.text, r4.model
        if mode == "prompt":
            r2 = await run_prompt_eng(
                text, sub_style=style or "prompt_general", skills_db=skills_db
            )
            return r2.text, r2.model
    except Exception:
        log.exception("long_voice_mode_llm_failed", mode=mode)
    return "", ""


async def _extract_audio_from_video(video_bytes: bytes) -> bytes | None:
    """Extract audio from video_note (circle) using ffmpeg."""
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
            log.error("ffmpeg_timeout", timeout=30)
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


@router.message(F.reply_to_message.voice | F.reply_to_message.audio | F.reply_to_message.video_note)
async def handle_reply_to_voice(
    message: Message, bot: Bot, session: AsyncSession, skills_db: SkillsDB
) -> None:
    """Re-transcribe when user replies to any voice/audio/video_note message."""
    reply = message.reply_to_message
    if reply and (reply.voice or reply.audio or reply.video_note):
        await _process_voice(message, reply, bot, session, skills_db)


@router.message(F.voice | F.audio)
async def handle_voice(
    message: Message, bot: Bot, session: AsyncSession, skills_db: SkillsDB
) -> None:
    """Handle direct and forwarded voice/audio messages."""
    await _process_voice(message, message, bot, session, skills_db)


@router.message(F.video_note)
async def handle_video_note(
    message: Message, bot: Bot, session: AsyncSession, skills_db: SkillsDB
) -> None:
    """Handle video notes (circles/кружочки) — extract audio and transcribe."""
    await _process_voice(message, message, bot, session, skills_db)
