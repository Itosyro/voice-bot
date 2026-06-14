import time

import structlog
from aiogram import Bot, F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.handlers._reply import send_result
from src.services.humanizer import run_humanizer
from src.services.polish import run_polish
from src.services.prompt_eng import run_prompt_eng
from src.services.skills_db import SkillsDB
from src.services.summary import run_summary
from src.services.translator import run_translator
from src.storage.history import save_request
from src.storage.users import get_or_create_user
from src.ui.keyboards import mode_keyboard, result_keyboard
from src.ui.messages import GROQ_ERROR, TEXT_TOO_LONG

log = structlog.get_logger()
router = Router()


@router.message(F.text & ~F.text.startswith("/"))
async def handle_text(
    message: Message, bot: Bot, session: AsyncSession, skills_db: SkillsDB
) -> None:
    user_tg = message.from_user
    if not user_tg or not message.text:
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

    text = message.text
    if len(text) > settings.max_text_length:
        await message.answer(
            TEXT_TOO_LONG.format(max_len=settings.max_text_length), parse_mode="HTML"
        )
        return

    started = time.monotonic()
    mode_label = {
        "polish": "Полирую",
        "prompt": "Создаю промпт",
        "humanizer": "Очеловечиваю",
        "translator": "Перевожу",
        "summary": "Делаю саммари",
    }
    progress_msg = await message.answer(f"✨ {mode_label.get(mode, 'Обрабатываю')}…")

    try:
        # No live streaming preview — sendMessageDraft leaves orphaned ephemeral
        # bubbles in the chat. We show progress, then deliver the final result.
        on_delta = None

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
            r4 = await run_translator(text, target_lang=user.target_lang or "en", on_delta=on_delta)
            result_text, llm_ms, model_used = r4.text, r4.llm_ms, r4.model
        elif mode == "summary":
            r5 = await run_summary(text, on_delta=on_delta)
            result_text, llm_ms, model_used = r5.text, r5.llm_ms, r5.model

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

        skills_info = f"\n\n🧠 Skills: {', '.join(used_skills)}" if used_skills else ""
        timing = ""
        kb = result_keyboard(mode)

        await send_result(message, progress_msg, result_text, skills_info, timing, kb)

    except Exception:
        log.exception("text_handler_error")
        await progress_msg.edit_text(GROQ_ERROR, reply_markup=mode_keyboard())
