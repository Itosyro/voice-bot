import time

import structlog
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.services.polish import run_polish
from src.services.prompt_eng import run_prompt_eng
from src.services.skills_db import SkillsDB
from src.services.transcribe import transcribe
from src.services.translator import run_translator
from src.storage.history import save_request
from src.storage.users import get_or_create_user
from src.ui.keyboards import mode_keyboard, result_voice_keyboard
from src.ui.messages import GROQ_ERROR, HUMANIZER_VOICE_ERROR, VOICE_TOO_LONG

log = structlog.get_logger()
router = Router()

_CHUNK = 3800  # max chars per Telegram message (limit is 4096, leave room for headers)


def _split_text(text: str) -> list[str]:
    """Split text into Telegram-sized chunks at paragraph → sentence → hard boundaries."""
    if len(text) <= _CHUNK:
        return [text]
    parts: list[str] = []
    while text:
        if len(text) <= _CHUNK:
            parts.append(text)
            break
        # Prefer splitting at a blank line (paragraph break)
        split_at = text.rfind("\n\n", 0, _CHUNK)
        if split_at == -1:
            # Fall back to sentence end
            split_at = text.rfind(". ", 0, _CHUNK)
        if split_at == -1:
            split_at = _CHUNK
        else:
            split_at += 1
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    return parts


@router.message(F.voice | F.audio)
async def handle_voice(
    message: Message, bot: Bot, session: AsyncSession, skills_db: SkillsDB, state: FSMContext
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
        await message.answer(HUMANIZER_VOICE_ERROR, reply_markup=mode_keyboard())
        return

    voice = message.voice or message.audio
    if not voice:
        return

    duration = voice.duration or 0
    if duration > settings.max_voice_duration_sec:
        await message.answer(VOICE_TOO_LONG.format(max_sec=settings.max_voice_duration_sec))
        return

    max_bytes = settings.max_voice_file_mb * 1024 * 1024
    if voice.file_size and voice.file_size > max_bytes:
        await message.answer(VOICE_TOO_LONG.format(max_sec=settings.max_voice_duration_sec))
        return

    started = time.monotonic()
    progress_msg = await message.answer(f"🎙️ Распознаю аудио ({duration} сек)…")

    try:
        file = await bot.get_file(voice.file_id)
        if not file.file_path:
            await progress_msg.edit_text("⚠️ Не удалось скачать аудио.")
            return
        file_bytes = await bot.download_file(file.file_path)
        if not file_bytes:
            await progress_msg.edit_text("⚠️ Не удалось скачать аудио.")
            return
        audio_bytes = file_bytes.read()

        groq_key = settings.get_groq_key(mode)
        transcript, stt_ms = await transcribe(
            audio_bytes, api_key=groq_key, file_id=voice.file_id, session=session
        )

        # Remember file_id so "Retranscribe" button can clear the cache entry later
        await state.update_data(last_voice_file_id=voice.file_id)

        mode_label = {"polish": "Полирую", "prompt": "Создаю промпт", "translator": "Перевожу"}
        await progress_msg.edit_text(f"✨ {mode_label.get(mode, 'Обрабатываю')}…")

        result_text = ""
        llm_ms = 0
        model_used = ""
        used_skills: list[str] = []

        if mode == "polish":
            r = await run_polish(transcript, sub_style=style or "polish_default")
            result_text, llm_ms, model_used = r.text, r.llm_ms, r.model
        elif mode == "prompt":
            r2 = await run_prompt_eng(
                transcript, sub_style=style or "prompt_general", skills_db=skills_db
            )
            result_text, llm_ms, model_used = r2.text, r2.llm_ms, r2.model
            used_skills = r2.used_skills
        elif mode == "translator":
            r3 = await run_translator(transcript, target_lang=user.target_lang or "en")
            result_text, llm_ms, model_used = r3.text, r3.llm_ms, r3.model

        total_ms = int((time.monotonic() - started) * 1000)

        await save_request(
            session,
            user_id=user.id,
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
        timing = f"\n\n⏱ STT: {stt_ms}ms | LLM: {llm_ms}ms | Total: {total_ms}ms"

        parts = _split_text(result_text)
        kb = result_voice_keyboard(mode)

        if len(parts) == 1:
            await progress_msg.edit_text(parts[0] + skills_info + timing, reply_markup=kb)
        else:
            total_parts = len(parts)
            await progress_msg.edit_text(f"📝 Часть 1/{total_parts}:\n\n{parts[0]}")
            for i, part in enumerate(parts[1:-1], 2):
                await message.answer(f"📝 Часть {i}/{total_parts}:\n\n{part}")
            await message.answer(
                f"📝 Часть {total_parts}/{total_parts}:\n\n{parts[-1]}{skills_info}{timing}",
                reply_markup=kb,
            )

    except Exception:
        log.exception("voice_handler_error")
        await progress_msg.edit_text(GROQ_ERROR, reply_markup=mode_keyboard())
