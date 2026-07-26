import contextlib
import time

import structlog
from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.handlers._last import LastRequest, save_last
from src.handlers._queue import user_lock
from src.handlers._reply import make_draft_streamer, send_result
from src.services.humanizer import run_humanizer
from src.services.llm import ModelUnavailableError, RequestTooLargeError, is_rate_limit_error
from src.services.polish import run_polish
from src.services.prompt_eng import run_prompt_eng
from src.services.skills_db import SkillsDB
from src.services.summary import run_summary
from src.services.translator import run_translator
from src.storage.history import save_request
from src.storage.user_context import load_user_context
from src.ui.keyboards import mode_keyboard, result_keyboard
from src.ui.messages import (
    GROQ_ERROR,
    MODEL_ERROR,
    RATE_LIMIT_ERROR,
    REQUEST_TOO_LARGE,
    TEXT_TOO_LONG,
    TG_SEND_ERROR,
)

log = structlog.get_logger()
router = Router()

MODE_LABEL = {
    "polish": "Полирую",
    "prompt": "Создаю промпт",
    "humanizer": "Очеловечиваю",
    "translator": "Перевожу",
    "summary": "Делаю саммари",
}


def error_message_for(exc: Exception) -> str:
    """Pick a user-facing error text that actually explains what broke."""
    if isinstance(exc, ModelUnavailableError):
        return MODEL_ERROR
    if isinstance(exc, RequestTooLargeError):
        return REQUEST_TOO_LARGE
    if "MESSAGE_TOO_LONG" in str(exc) or "message is too long" in str(exc).lower():
        return TG_SEND_ERROR
    if is_rate_limit_error(exc):
        return RATE_LIMIT_ERROR
    return GROQ_ERROR


async def _process_text(
    message: Message,
    session: AsyncSession,
    skills_db: SkillsDB,
    *,
    text: str,
    mode: str,
    style: str | None,
    target_lang: str,
    db_user_id: int | None,
) -> bool:
    """Run the selected mode on text and deliver the result. Returns True on success."""
    started = time.monotonic()
    progress_msg = await message.answer(f"✨ {MODE_LABEL.get(mode, 'Обрабатываю')}…")
    on_delta = make_draft_streamer(message.bot, message.chat.id) if message.bot else None

    try:
        result_text = ""
        llm_ms = 0
        model_used = ""
        used_skills: list[str] = []

        if mode == "polish":
            r = await run_polish(text, sub_style=style or "polish_default", on_delta=on_delta)
            result_text, llm_ms, model_used = r.text, r.llm_ms, r.model
        elif mode == "prompt":
            r2 = await run_prompt_eng(
                text, sub_style=style or "prompt_general", skills_db=skills_db, on_delta=on_delta
            )
            result_text, llm_ms, model_used = r2.text, r2.llm_ms, r2.model
            used_skills = r2.used_skills
        elif mode == "humanizer":
            r3 = await run_humanizer(text, sub_style=style or "humanize_lite", on_delta=on_delta)
            result_text, llm_ms, model_used = r3.text, r3.llm_ms, r3.model
        elif mode == "translator":
            r4 = await run_translator(text, target_lang=target_lang, on_delta=on_delta)
            result_text, llm_ms, model_used = r4.text, r4.llm_ms, r4.model
        elif mode == "summary":
            r5 = await run_summary(text, on_delta=on_delta)
            result_text, llm_ms, model_used = r5.text, r5.llm_ms, r5.model

        total_ms = int((time.monotonic() - started) * 1000)

        # Deliver the result FIRST — history is best-effort. Раньше падение БД
        # на save_request выбрасывало уже готовый ответ LLM (юзер видел ошибку).
        skills_info = f"\n\n🧠 Skills: {', '.join(used_skills)}" if used_skills else ""
        await send_result(
            message, progress_msg, result_text, skills_info, "", result_keyboard(mode)
        )

        if db_user_id is not None:
            try:
                await save_request(
                    session,
                    user_id=db_user_id,
                    mode=mode,
                    style=style or "default",
                    input_type="text",
                    input_length=len(text),
                    input_preview=text[:200],
                    output_text=result_text[:5000],
                    output_length=len(result_text),
                    llm_model=model_used,
                    llm_ms=llm_ms,
                    total_ms=total_ms,
                )
            except Exception as exc:
                log.warning("save_request_failed", error=str(exc))
                # Не оставляем сессию в failed-состоянии — иначе финальный
                # commit в middleware упадёт с PendingRollbackError.
                with contextlib.suppress(Exception):
                    await session.rollback()
        return True

    except Exception as exc:
        log.exception("text_handler_error")
        await progress_msg.edit_text(error_message_for(exc), reply_markup=mode_keyboard())
        return False


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(message: Message, session: AsyncSession, skills_db: SkillsDB) -> None:
    user_tg = message.from_user
    if not user_tg or not message.text:
        return

    ctx = await load_user_context(
        session,
        telegram_user_id=user_tg.id,
        username=user_tg.username,
        first_name=user_tg.first_name,
    )

    # Дефолт для новичка — полировка: первое сообщение сразу даёт результат,
    # а не тупик «сначала выбери режим».
    mode = ctx.default_mode or "polish"
    style = ctx.default_style

    text = message.text
    if len(text) > settings.max_text_length:
        await message.answer(
            TEXT_TOO_LONG.format(max_len=settings.max_text_length), parse_mode="HTML"
        )
        return

    target_lang = ctx.target_lang
    lock = user_lock(user_tg.id)
    if lock.locked():
        await message.answer("⏳ Обрабатываю предыдущее — это сообщение возьму следом.")
    async with lock:
        ok = await _process_text(
            message,
            session,
            skills_db,
            text=text,
            mode=mode,
            style=style,
            target_lang=target_lang,
            db_user_id=ctx.db_user_id,
        )
    if ok:
        save_last(
            user_tg.id,
            LastRequest(
                input_type="text",
                mode=mode,
                style=style,
                target_lang=target_lang,
                db_user_id=ctx.db_user_id,
                text=text,
            ),
        )


async def regenerate_text(
    message: Message, session: AsyncSession, skills_db: SkillsDB, last: LastRequest
) -> None:
    """Re-run the mode on the last text input, generating a fresh answer."""
    if not last.text:
        return
    await _process_text(
        message,
        session,
        skills_db,
        text=last.text,
        mode=last.mode,
        style=last.style,
        target_lang=last.target_lang,
        db_user_id=last.db_user_id,
    )
