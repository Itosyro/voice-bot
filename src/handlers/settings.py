from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.prompts.translator import LANG_NAMES
from src.storage.history import get_user_history
from src.storage.user_context import load_user_context, save_user_settings
from src.storage.users import get_or_create_user
from src.ui.design import MODE_NAME
from src.ui.keyboards import lang_keyboard, settings_keyboard
from src.ui.messages import DB_UNAVAILABLE, settings_text
from src.utils import escape_html

router = Router()


@router.message(Command("settings"))
async def cmd_settings(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    ctx = await load_user_context(session, telegram_user_id=message.from_user.id)

    text = settings_text(
        ctx.default_mode,
        ctx.default_style,
        ctx.target_lang,
        ctx.total_requests,
    )
    await message.answer(text, reply_markup=settings_keyboard(), parse_mode="HTML")


@router.message(Command("lang"))
async def cmd_lang(message: Message, session: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Выбери язык:", reply_markup=lang_keyboard())
        return

    lang = parts[1].lower().strip()
    if lang not in LANG_NAMES and len(lang) > 5:
        await message.answer(
            "⚠ Неизвестный код языка. Выбери из списка:",
            reply_markup=lang_keyboard(),
        )
        return
    await save_user_settings(session, message.from_user.id, target_lang=lang)
    await message.answer(f"⇄ Язык перевода: {lang.upper()}")


@router.message(Command("history"))
async def cmd_history(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return

    try:
        user = await get_or_create_user(session, telegram_user_id=message.from_user.id)
        history = await get_user_history(session, user_id=user.id, limit=10)
    except Exception:
        await message.answer(DB_UNAVAILABLE, parse_mode="HTML")
        return

    if not history:
        await message.answer("История пуста.")
        return

    lines = ["<b>Последние запросы</b>\n"]
    for h in history:
        mode_name = MODE_NAME.get(h.mode, h.mode)
        preview = (h.input_preview or "")[:80]
        lines.append(f"• {mode_name} | {h.input_type} | {escape_html(preview)}")

    await message.answer("\n".join(lines), parse_mode="HTML")
