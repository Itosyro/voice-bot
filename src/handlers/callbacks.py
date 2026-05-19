import structlog
from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.history import get_user_history
from src.storage.users import get_or_create_user, update_user_settings
from src.ui.design import MODE_NAME, STYLE_NAME
from src.ui.keyboards import (
    humanizer_style_keyboard,
    lang_keyboard,
    mode_info_keyboard,
    mode_keyboard,
    polish_style_keyboard,
    prompt_style_keyboard,
    reprocess_mode_keyboard,
    settings_keyboard,
)
from src.ui.messages import CHOOSE_MODE, MODE_INFO, settings_text, style_header
from src.utils import escape_html

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

    if mode == "summary":
        await update_user_settings(
            session,
            telegram_user_id=callback.from_user.id,
            default_mode="summary",
            default_style="summary",
        )
        await callback.message.edit_text(  # type: ignore[union-attr]
            "∑ <b>САММАРИ</b>\n\nОтправь голос или текст",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    kb_fn = STYLE_KEYBOARDS.get(mode)
    if kb_fn:
        await callback.message.edit_text(  # type: ignore[union-attr]
            style_header(mode),
            reply_markup=kb_fn(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data.startswith("style:"))
async def on_style_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.data or not callback.from_user:
        return
    style = callback.data.split(":", 1)[1]

    mode_map = {
        "polish_raw": "polish",
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

    style_name = STYLE_NAME.get(style, style)
    mode_name = MODE_NAME.get(mode, mode)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"{mode_name} · {style_name}\n\nОтправь голос или текст",
        parse_mode="HTML",
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
        f"ПЕРЕВОД → {lang.upper()}\n\nОтправь голос или текст",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Navigation ──


@router.callback_query(F.data == "back:modes")
async def on_back_to_modes(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        CHOOSE_MODE,
        reply_markup=mode_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "back:settings")
async def on_back_to_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.from_user:
        return
    user = await get_or_create_user(session, telegram_user_id=callback.from_user.id)
    text = settings_text(
        user.default_mode,
        user.default_style,
        user.target_lang or "en",
        user.total_requests,
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=settings_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Settings ──


@router.callback_query(F.data == "cmd:settings")
async def on_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.from_user:
        return
    user = await get_or_create_user(session, telegram_user_id=callback.from_user.id)
    text = settings_text(
        user.default_mode,
        user.default_style,
        user.target_lang or "en",
        user.total_requests,
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=settings_keyboard(),
        parse_mode="HTML",
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
    mode_name = MODE_NAME.get(mode, mode)
    await callback.answer(f"Режим {mode_name} установлен по умолчанию!", show_alert=True)


@router.callback_query(F.data == "action:export")
async def on_export(callback: CallbackQuery) -> None:
    """Export the result text as a .txt file."""
    msg = callback.message
    if not msg or not msg.text:
        await callback.answer("Нет текста для экспорта.")
        return

    text_content = msg.text.strip()
    file_bytes = text_content.encode("utf-8")
    doc = BufferedInputFile(file_bytes, filename="result.txt")
    await msg.answer_document(doc)  # type: ignore[union-attr]
    await callback.answer("Готово!")


@router.callback_query(F.data == "action:regenerate")
async def on_regenerate(callback: CallbackQuery) -> None:
    await callback.answer("Отправь сообщение ещё раз для перегенерации.")


@router.callback_query(F.data == "action:other_mode")
async def on_other_mode(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "<b>Другой режим</b>\n\nВыбери режим — отправь тот же голос\nили текст ещё раз:",
        reply_markup=reprocess_mode_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "settings:default_mode")
async def on_settings_default_mode(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        CHOOSE_MODE,
        reply_markup=mode_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "settings:target_lang")
async def on_settings_target_lang(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        style_header("translator"),
        reply_markup=lang_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "settings:mode_info")
async def on_mode_info_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Выбери режим, чтобы узнать подробнее:",
        reply_markup=mode_info_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("info:"))
async def on_mode_info_page(callback: CallbackQuery) -> None:
    if not callback.data:
        return
    mode = callback.data.split(":", 1)[1]
    text = MODE_INFO.get(mode, "Информация недоступна.")
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=mode_info_keyboard(),
        parse_mode="HTML",
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
        CHOOSE_MODE,
        reply_markup=mode_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── History ──


@router.callback_query(F.data == "cmd:history")
async def on_history(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.from_user:
        return
    user = await get_or_create_user(session, telegram_user_id=callback.from_user.id)
    history = await get_user_history(session, user_id=user.id, limit=10)

    if not history:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "История пуста.",
            reply_markup=mode_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    lines = ["<b>Последние запросы</b>\n"]
    for h in history:
        mode_name = MODE_NAME.get(h.mode, h.mode)
        preview = (h.input_preview or "")[:80]
        lines.append(f"• {mode_name} | {h.input_type} | {escape_html(preview)}...")

    await callback.message.edit_text(  # type: ignore[union-attr]
        "\n".join(lines),
        reply_markup=mode_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
