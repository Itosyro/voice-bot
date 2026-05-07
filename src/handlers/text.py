import time

import structlog
from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.services.humanizer import run_humanizer
from src.services.polish import run_polish
from src.services.prompt_eng import run_prompt_eng
from src.services.skills_db import SkillsDB
from src.services.translator import run_translator
from src.storage.history import save_request
from src.storage.users import get_or_create_user, update_user_settings
from src.ui.keyboards import mode_keyboard, result_keyboard
from src.ui.messages import GROQ_ERROR, TEXT_TOO_LONG
from src.utils import escape_html

log = structlog.get_logger()

router = Router()


def _extract_text(message: Message) -> str | None:
    """Extract text from normal or forwarded messages."""
    if message.text:
        return message.text
    if message.caption:
        return message.caption
    return None


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(
    message: Message, session: AsyncSession, skills_db: SkillsDB
) -> None:
    await _process_text(message, session, skills_db)


@router.message(F.forward_date & F.text)
async def handle_forwarded_text(
    message: Message, session: AsyncSession, skills_db: SkillsDB
) -> None:
    await _process_text(message, session, skills_db)


@router.message(F.caption & ~(F.voice | F.audio))
async def handle_caption(
    message: Message, session: AsyncSession, skills_db: SkillsDB
) -> None:
    await _process_text(message, session, skills_db)


async def _process_text(
    message: Message, session: AsyncSession, skills_db: SkillsDB
) -> None:
    user_tg = message.from_user
    if not user_tg:
        return

    text = _extract_text(message)
    if not text or text.startswith("/"):
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

    if len(text) > settings.max_text_length:
        await message.answer(
            TEXT_TOO_LONG.format(max_len=settings.max_text_length)
        )
        return

    started = time.monotonic()
    mode_label = {
        "polish": "Полирую",
        "prompt": "Создаю промпт",
        "humanizer": "Очеловечиваю",
        "translator": "Перевожу",
    }
    progress_msg = await message.answer(
        f"{mode_label.get(mode, 'Обрабатываю')}…"
    )

    try:
        result_text = ""
        llm_ms = 0
        model_used = ""

        if mode == "polish":
            r = await run_polish(
                text, sub_style=style or "polish_default"
            )
            result_text, llm_ms, model_used = r.text, r.llm_ms, r.model
        elif mode == "prompt":
            r2 = await run_prompt_eng(
                text,
                sub_style=style or "prompt_general",
                skills_db=skills_db,
            )
            result_text, llm_ms, model_used = r2.text, r2.llm_ms, r2.model
        elif mode == "humanizer":
            r3 = await run_humanizer(
                text, sub_style=style or "humanize_lite"
            )
            result_text, llm_ms, model_used = r3.text, r3.llm_ms, r3.model
        elif mode == "translator":
            r4 = await run_translator(
                text, target_lang=user.target_lang or "en"
            )
            result_text, llm_ms, model_used = r4.text, r4.llm_ms, r4.model

        if not result_text or not result_text.strip():
            await progress_msg.edit_text(
                "⚠ Не удалось обработать текст. Попробуй ещё раз.",
                reply_markup=mode_keyboard(),
            )
            return

        total_ms = int((time.monotonic() - started) * 1000)

        await save_request(
            session,
            user_id=user.id,
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

        if len(result_text) > 3900:
            result_text = result_text[:3900] + "\n\n… (обрезано)"

        final = (
            f"<blockquote>"
            f"<code>{escape_html(result_text)}</code>"
            f"</blockquote>"
        )
        await progress_msg.edit_text(
            final, reply_markup=result_keyboard(mode), parse_mode="HTML"
        )

    except Exception as exc:
        log.exception("text_handler_error")
        error_msg = GROQ_ERROR
        exc_str = str(exc).lower()
        if "rate" in exc_str or "limit" in exc_str:
            error_msg = "⏳ Лимит Groq API. Подожди минуту и попробуй снова."
        elif "model" in exc_str and "not found" in exc_str:
            error_msg = "⚠ Модель временно недоступна. Попробуй другой режим."
        await progress_msg.edit_text(error_msg, reply_markup=mode_keyboard())
