import structlog
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.transcribe import transcribe as _transcribe_fn  # noqa: F401 — for cache clear
from src.storage.history import get_user_history
from src.storage.models import TranscriptionCache
from src.storage.users import get_or_create_user, update_user_settings
from src.ui.keyboards import (
    humanizer_style_keyboard,
    lang_keyboard,
    mode_keyboard,
    polish_style_keyboard,
    prompt_style_keyboard,
    settings_keyboard,
)
from src.ui.messages import MODE_NAMES, RETRANSCRIBE_PROMPT, STYLE_NAMES

log = structlog.get_logger()
router = Router()

STYLE_KEYBOARDS = {
    "polish": polish_style_keyboard,
    "prompt": prompt_style_keyboard,
    "humanizer": humanizer_style_keyboard,
    "translator": lang_keyboard,
}


@router.callback_query(F.data.startswith("mode:"))
async def on_mode_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.data or not callback.from_user:
        return
    mode = callback.data.split(":", 1)[1]

    kb_fn = STYLE_KEYBOARDS.get(mode)
    if kb_fn:
        mode_name = MODE_NAMES.get(mode, mode)
        if mode == "translator":
            await callback.message.edit_text(  # type: ignore[union-attr]
                f"{mode_name} — выбери язык перевода:", reply_markup=kb_fn()
            )
        else:
            await callback.message.edit_text(  # type: ignore[union-attr]
                f"{mode_name} — выбери подстиль:", reply_markup=kb_fn()
            )
    await callback.answer()


@router.callback_query(F.data.startswith("style:"))
async def on_style_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.data or not callback.from_user:
        return
    style = callback.data.split(":", 1)[1]

    mode_map = {
        "polish_default": "polish",
        "polish_creative": "polish",
        "polish_formal": "polish",
        "polish_embellish": "polish",
        "prompt_general": "prompt",
        "prompt_designer": "prompt",
        "prompt_coder": "prompt",
        "prompt_coder_strict": "prompt",
        "humanize_lite": "humanizer",
        "humanize_strong": "humanizer",
    }
    mode = mode_map.get(style, "polish")

    await update_user_settings(
        session,
        telegram_user_id=callback.from_user.id,
        default_mode=mode,
        default_style=style,
    )

    style_name = STYLE_NAMES.get(style, style)
    mode_name = MODE_NAMES.get(mode, mode)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"Режим: {mode_name} | Стиль: {style_name}\n\nТеперь отправь мне голос или текст!"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("lang:"))
async def on_lang_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.data or not callback.from_user:
        return
    lang = callback.data.split(":", 1)[1]

    await update_user_settings(
        session,
        telegram_user_id=callback.from_user.id,
        default_mode="translator",
        default_style="translator",
        target_lang=lang,
    )

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"🌍 Translator → {lang.upper()}\n\nТеперь отправь мне голос или текст для перевода!"
    )
    await callback.answer()


@router.callback_query(F.data == "back:modes")
async def on_back_to_modes(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Выбери режим:", reply_markup=mode_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("action:set_default:"))
async def on_set_default(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.data or not callback.from_user:
        return
    mode = callback.data.split(":", 2)[2]
    await update_user_settings(
        session,
        telegram_user_id=callback.from_user.id,
        default_mode=mode,
    )
    mode_name = MODE_NAMES.get(mode, mode)
    await callback.answer(f"Режим {mode_name} установлен по умолчанию!", show_alert=True)


@router.callback_query(F.data == "action:regenerate")
async def on_regenerate(callback: CallbackQuery) -> None:
    await callback.answer("Отправь сообщение ещё раз для перегенерации.")


@router.callback_query(F.data == "action:retranscribe")
async def on_retranscribe(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    """Clear the cached transcription for the last voice message so next send re-runs Whisper."""
    data = await state.get_data()
    file_id = data.get("last_voice_file_id")
    if file_id:
        cached = await session.get(TranscriptionCache, file_id)
        if cached:
            await session.delete(cached)
            await session.commit()
    await callback.message.answer(RETRANSCRIBE_PROMPT)  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "cmd:settings")
async def on_settings(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "⚙️ Настройки:", reply_markup=settings_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "settings:default_mode")
async def on_settings_default_mode(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Выбери режим по умолчанию:", reply_markup=mode_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "settings:target_lang")
async def on_settings_target_lang(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Выбери язык для переводчика:", reply_markup=lang_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "settings:reset")
async def on_settings_reset(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.from_user:
        return
    await update_user_settings(
        session,
        telegram_user_id=callback.from_user.id,
        default_mode=None,
        default_style=None,
        target_lang="en",
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Настройки сброшены. Выбери режим:", reply_markup=mode_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "cmd:history")
async def on_history(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.from_user:
        return
    user = await get_or_create_user(session, telegram_user_id=callback.from_user.id)
    history = await get_user_history(session, user_id=user.id, limit=10)

    if not history:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "📜 История пуста.", reply_markup=mode_keyboard()
        )
        await callback.answer()
        return

    lines = ["📜 **Последние запросы:**\n"]
    for h in history:
        mode_name = MODE_NAMES.get(h.mode, h.mode)
        preview = (h.input_preview or "")[:80]
        lines.append(f"• {mode_name} | {h.input_type} | {preview}...")

    await callback.message.edit_text(  # type: ignore[union-attr]
        "\n".join(lines), reply_markup=mode_keyboard(), parse_mode="Markdown"
    )
    await callback.answer()
