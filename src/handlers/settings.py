from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.users import get_or_create_user, update_user_settings
from src.ui.keyboards import lang_keyboard, settings_keyboard
from src.ui.messages import MODE_NAMES, STYLE_NAMES

router = Router()


@router.message(Command("settings"))
async def cmd_settings(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    user = await get_or_create_user(session, telegram_user_id=message.from_user.id)

    mode_name = MODE_NAMES.get(user.default_mode or "", "не выбран")
    style_name = STYLE_NAMES.get(user.default_style or "", "не выбран")
    lang = user.target_lang or "en"

    text = (
        f"НАСТРОЙКИ\n\n"
        f"Режим: {mode_name}\n"
        f"Стиль: {style_name}\n"
        f"Язык: {lang.upper()}\n"
        f"Запросов: {user.total_requests}"
    )
    await message.answer(text, reply_markup=settings_keyboard())


@router.message(Command("lang"))
async def cmd_lang(message: Message, session: AsyncSession) -> None:
    if not message.from_user or not message.text:
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Выбери язык:", reply_markup=lang_keyboard())
        return

    lang = parts[1].lower().strip()
    await update_user_settings(
        session,
        telegram_user_id=message.from_user.id,
        target_lang=lang,
    )
    await message.answer(f"🌍 Язык перевода: {lang.upper()}")


@router.message(Command("history"))
async def cmd_history(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    from src.storage.history import get_user_history

    user = await get_or_create_user(session, telegram_user_id=message.from_user.id)
    history = await get_user_history(session, user_id=user.id, limit=10)

    if not history:
        await message.answer("📜 История пуста.")
        return

    lines = ["ИСТОРИЯ\n"]
    for h in history:
        mode_name = MODE_NAMES.get(h.mode, h.mode)
        preview = (h.input_preview or "")[:80]
        lines.append(f"· {mode_name} | {h.input_type} | {preview}")

    await message.answer("\n".join(lines))
