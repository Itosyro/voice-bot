import asyncio
import time

import structlog
from aiogram import Bot, F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.handlers._last import LastRequest, save_last
from src.handlers._reply import send_result
from src.services.polish import run_polish
from src.services.prompt_eng import run_prompt_eng
from src.services.skills_db import SkillsDB
from src.services.summary import run_summary
from src.services.transcribe import extract_audio_from_video, split_audio_to_chunks, transcribe
from src.services.translator import run_translator
from src.storage.history import save_request
from src.storage.users import get_or_create_user
from src.ui.keyboards import mode_keyboard, result_keyboard
from src.ui.messages import (
    CHUNK_TRANSCRIBING,
    EMPTY_TRANSCRIPT,
    GROQ_ERROR,
    HUMANIZER_VOICE_ERROR,
    VOICE_TOO_LONG,
)

log = structlog.get_logger()
router = Router()

# Media may arrive directly, forwarded, or as the message a user replies to.
_HAS_MEDIA = F.voice | F.audio | F.video_note | F.video
_REPLY_HAS_MEDIA = (
    F.reply_to_message.voice
    | F.reply_to_message.audio
    | F.reply_to_message.video_note
    | F.reply_to_message.video
)

MODE_LABEL = {
    "polish": "Полирую",
    "prompt": "Создаю промпт",
    "translator": "Перевожу",
    "summary": "Делаю саммари",
}


def _pick_media(msg: Message | None):
    """Return (media, is_video) from a message's voice/audio/video_note/video, or (None, False)."""
    if msg is None:
        return None, False
    if msg.voice:
        return msg.voice, False
    if msg.audio:
        return msg.audio, False
    if msg.video_note:
        return msg.video_note, True
    if msg.video:
        return msg.video, True
    return None, False


async def _run_mode(
    transcript: str,
    mode: str,
    style: str | None,
    target_lang: str,
    skills_db: SkillsDB,
    on_delta,
) -> tuple[str, int, str, list[str]]:
    """Run the selected mode's LLM step. Returns (text, llm_ms, model, used_skills)."""
    used_skills: list[str] = []

    if mode == "polish":
        r = await run_polish(transcript, sub_style=style or "polish_default", on_delta=on_delta)
        return r.text, r.llm_ms, r.model, used_skills
    if mode == "prompt":
        r2 = await run_prompt_eng(
            transcript,
            sub_style=style or "prompt_general",
            skills_db=skills_db,
            on_delta=on_delta,
        )
        return r2.text, r2.llm_ms, r2.model, r2.used_skills
    if mode == "translator":
        r3 = await run_translator(transcript, target_lang=target_lang, on_delta=on_delta)
        return r3.text, r3.llm_ms, r3.model, used_skills
    if mode == "summary":
        r4 = await run_summary(transcript, on_delta=on_delta)
        return r4.text, r4.llm_ms, r4.model, used_skills

    return "", 0, "", used_skills


async def _process_media(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    skills_db: SkillsDB,
    *,
    media,
    is_video: bool,
    mode: str,
    style: str | None,
    target_lang: str,
    db_user_id: int,
    force_retranscribe: bool,
) -> bool:
    """Transcribe media and run the mode, delivering the result. Returns True on success.

    force_retranscribe=True busts the transcription cache so Whisper re-runs from
    scratch — used by the "Повтор" button to genuinely redo the cycle.
    """
    duration = media.duration or 0
    if duration > settings.max_voice_duration_sec:
        await message.answer(
            VOICE_TOO_LONG.format(max_min=settings.max_voice_duration_sec // 60),
            parse_mode="HTML",
        )
        return False

    max_bytes = settings.max_voice_file_mb * 1024 * 1024
    if media.file_size and media.file_size > max_bytes:
        await message.answer(
            VOICE_TOO_LONG.format(max_min=settings.max_voice_duration_sec // 60),
            parse_mode="HTML",
        )
        return False

    started = time.monotonic()
    progress_msg = await message.answer(f"🎙️ Распознаю аудио ({duration} сек)…")

    try:
        file = await bot.get_file(media.file_id)
        if not file.file_path:
            await progress_msg.edit_text("⚠️ Не удалось скачать аудио.")
            return False
        file_bytes = await bot.download_file(file.file_path)
        if not file_bytes:
            await progress_msg.edit_text("⚠️ Не удалось скачать аудио.")
            return False
        raw_bytes = file_bytes.read()

        if is_video:
            audio_bytes = await extract_audio_from_video(raw_bytes)
            if not audio_bytes:
                await progress_msg.edit_text("⚠️ Не удалось извлечь аудио из видео.")
                return False
        else:
            audio_bytes = raw_bytes

        groq_key = settings.get_groq_key(mode)

        if duration <= settings.chunk_threshold_sec:
            # Single-shot path — caching by file_id; force_retranscribe busts it.
            transcript, stt_ms = await transcribe(
                audio_bytes,
                api_key=groq_key,
                file_id=media.file_id,
                session=session,
                force_retranscribe=force_retranscribe,
            )
        else:
            # Long audio — split into chunks and transcribe sequentially (no cache).
            chunks = await split_audio_to_chunks(audio_bytes, settings.chunk_duration_sec)
            if not chunks:
                await progress_msg.edit_text(
                    "⚠️ Не удалось разрезать длинное аудио. Попробуй короче.",
                    reply_markup=mode_keyboard(),
                )
                return False

            n = len(chunks)
            transcript_parts: list[str] = []
            stt_ms = 0
            for k, chunk_bytes in enumerate(chunks, 1):
                await progress_msg.edit_text(CHUNK_TRANSCRIBING.format(k=k, n=n), parse_mode="HTML")
                chunk_text, chunk_ms = await transcribe(chunk_bytes, api_key=groq_key)
                stt_ms += chunk_ms
                if chunk_text and chunk_text.strip():
                    transcript_parts.append(chunk_text.strip())
                if k < n:
                    await asyncio.sleep(settings.chunk_throttle_sec)

            transcript = "\n\n".join(transcript_parts)

        if not transcript.strip():
            await progress_msg.edit_text(EMPTY_TRANSCRIPT, reply_markup=mode_keyboard())
            return False

        await progress_msg.edit_text(f"✨ {MODE_LABEL.get(mode, 'Обрабатываю')}…")

        result_text, llm_ms, model_used, used_skills = await _run_mode(
            transcript, mode, style, target_lang, skills_db, None
        )

        total_ms = int((time.monotonic() - started) * 1000)

        await save_request(
            session,
            user_id=db_user_id,
            mode=mode,
            style=style or "default",
            input_type="voice",
            input_length=duration,
            input_preview=transcript[:200],
            output_text=result_text[:5000],
            output_length=len(result_text),
            llm_model=model_used,
            transcription_ms=stt_ms,
            llm_ms=llm_ms,
            total_ms=total_ms,
        )

        skills_info = f"\n\n🧠 Skills: {', '.join(used_skills)}" if used_skills else ""
        await send_result(
            message, progress_msg, result_text, skills_info, "", result_keyboard(mode)
        )
        return True

    except Exception:
        log.exception("voice_handler_error")
        await progress_msg.edit_text(GROQ_ERROR, reply_markup=mode_keyboard())
        return False


@router.message(_HAS_MEDIA | _REPLY_HAS_MEDIA)
async def handle_voice(
    message: Message, bot: Bot, session: AsyncSession, skills_db: SkillsDB
) -> None:
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
        await message.answer("Сначала выбери режим:", reply_markup=mode_keyboard())
        return

    if mode == "humanizer":
        await message.answer(HUMANIZER_VOICE_ERROR, reply_markup=mode_keyboard(), parse_mode="HTML")
        return

    # Direct/forwarded media first; otherwise the message the user replied to.
    media, is_video = _pick_media(message)
    if media is None:
        media, is_video = _pick_media(message.reply_to_message)
    if media is None:
        return

    target_lang = user.target_lang or "en"
    ok = await _process_media(
        message,
        bot,
        session,
        skills_db,
        media=media,
        is_video=is_video,
        mode=mode,
        style=style,
        target_lang=target_lang,
        db_user_id=user.id,
        force_retranscribe=False,
    )
    if ok:
        save_last(
            user_tg.id,
            LastRequest(
                input_type="voice",
                mode=mode,
                style=style,
                target_lang=target_lang,
                db_user_id=user.id,
                media=media,
                is_video=is_video,
            ),
        )


async def regenerate_voice(
    message: Message, bot: Bot, session: AsyncSession, skills_db: SkillsDB, last: LastRequest
) -> None:
    """Re-run the full transcription→generation cycle on the last voice, fresh (no cache)."""
    await _process_media(
        message,
        bot,
        session,
        skills_db,
        media=last.media,
        is_video=last.is_video,
        mode=last.mode,
        style=last.style,
        target_lang=last.target_lang,
        db_user_id=last.db_user_id,
        force_retranscribe=True,
    )
