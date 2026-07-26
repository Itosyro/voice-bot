import structlog
from aiogram import Bot, F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.handlers._last import (
    get_last,
    get_last_result,
    get_last_transcript,
    get_result_for_message,
)
from src.handlers._queue import is_busy, user_lock
from src.handlers.text import regenerate_text
from src.handlers.voice import regenerate_voice
from src.services.skills_db import SkillsDB
from src.storage.history import get_user_history
from src.storage.user_context import load_user_context, save_user_settings
from src.storage.users import get_or_create_user
from src.ui.design import MODE_NAME, STYLE_NAME
from src.ui.keyboards import (
    humanizer_style_keyboard,
    lang_keyboard,
    menu_keyboard,
    mode_info_keyboard,
    mode_keyboard,
    polish_style_keyboard,
    prompt_style_keyboard,
    reprocess_mode_keyboard,
    settings_keyboard,
)
from src.ui.messages import (
    CHOOSE_MODE,
    DB_UNAVAILABLE,
    HUMANIZER_VOICE_ERROR,
    MODE_INFO,
    settings_text,
    style_header,
)
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
    await callback.answer()  # ack immediately so the button stops spinning
    mode = callback.data.split(":", 1)[1]

    if mode == "summary":
        await save_user_settings(
            session,
            callback.from_user.id,
            default_mode="summary",
            default_style="summary",
        )
        await callback.message.edit_text(  # type: ignore[union-attr]
            "∑ <b>САММАРИ</b>\n\nОтправь голос или текст",
            reply_markup=menu_keyboard(),
            parse_mode="HTML",
        )
        return

    kb_fn = STYLE_KEYBOARDS.get(mode)
    if kb_fn:
        # Персистим режим сразу (стиль сбрасываем на дефолт режима): раньше
        # выбор «ПОЛИРОВКА» после Summary без нажатия стиля оставлял summary.
        await save_user_settings(
            session, callback.from_user.id, default_mode=mode, reset_style=True
        )
        await callback.message.edit_text(  # type: ignore[union-attr]
            style_header(mode),
            reply_markup=kb_fn(),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("style:"))
async def on_style_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.data or not callback.from_user:
        return
    await callback.answer()  # ack immediately so the button stops spinning
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

    await save_user_settings(
        session,
        callback.from_user.id,
        default_mode=mode,
        default_style=style,
    )

    style_name = STYLE_NAME.get(style, style)
    mode_name = MODE_NAME.get(mode, mode)
    await callback.message.edit_text(  # type: ignore[union-attr]
        f"{mode_name} · {style_name}\n\nОтправь голос или текст",
        reply_markup=menu_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("lang:"))
async def on_lang_selected(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.data or not callback.from_user:
        return
    await callback.answer()  # ack immediately so the button stops spinning
    lang = callback.data.split(":", 1)[1]

    await save_user_settings(
        session,
        callback.from_user.id,
        default_mode="translator",
        default_style="translator",
        target_lang=lang,
    )

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"ПЕРЕВОД → {lang.upper()}\n\nОтправь голос или текст",
        reply_markup=menu_keyboard(),
        parse_mode="HTML",
    )


# ── Navigation ──


def _holds_result(msg) -> bool:
    """True, если в сообщении лежит результат (копи-блок) — его нельзя затирать."""
    entities = getattr(msg, "entities", None) or []
    return any(e.type in ("blockquote", "expandable_blockquote", "code", "pre") for e in entities)


@router.callback_query(F.data == "back:modes")
async def on_back_to_modes(callback: CallbackQuery) -> None:
    await callback.answer()  # ack immediately so the button stops spinning
    msg = callback.message
    if msg is None:
        return
    if _holds_result(msg):
        # Раньше «Меню» УНИЧТОЖАЛО результат, редактируя его в список режимов.
        await msg.answer(CHOOSE_MODE, reply_markup=mode_keyboard(), parse_mode="HTML")
        return
    await msg.edit_text(CHOOSE_MODE, reply_markup=mode_keyboard(), parse_mode="HTML")


async def _show_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    """Render the settings card; survive a dead DB with memory-store values."""
    if not callback.from_user:
        return
    await callback.answer()  # ack immediately so the button stops spinning
    ctx = await load_user_context(session, callback.from_user.id)
    if not ctx.from_db:
        log.warning("settings_shown_from_memory", telegram_user_id=callback.from_user.id)
    total = ctx.total_requests if ctx.from_db else None
    text = settings_text(ctx.default_mode, ctx.default_style, ctx.target_lang, total)
    await callback.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=settings_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back:settings")
async def on_back_to_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    await _show_settings(callback, session)


# ── Settings ──


@router.callback_query(F.data == "cmd:settings")
async def on_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    await _show_settings(callback, session)


@router.callback_query(F.data == "action:export")
async def on_export(callback: CallbackQuery) -> None:
    """Export the result text as a .txt file."""
    msg = callback.message
    if not msg:
        await callback.answer("Нет текста для экспорта.")
        return

    # Сначала — результат именно ЭТОГО сообщения (кнопка под старым ответом не
    # должна выгружать более новый), затем последний, затем видимый текст.
    text_content = (
        get_result_for_message(msg.chat.id, msg.message_id)
        or get_last_result(msg.chat.id)
        or (msg.text or "").strip()
    )
    if not text_content:
        await callback.answer("Нет текста для экспорта.")
        return

    doc = BufferedInputFile(text_content.encode("utf-8"), filename="result.txt")
    await msg.answer_document(doc)  # type: ignore[union-attr]
    await callback.answer("Готово!")


@router.callback_query(F.data.startswith("rerun:"))
async def on_rerun_in_mode(
    callback: CallbackQuery, bot: Bot, session: AsyncSession, skills_db: SkillsDB
) -> None:
    """«Другой режим» → выбор режима СРАЗУ прогоняет сохранённый запрос.

    Раньше кнопка честно писала «отправь тот же голос ещё раз» — хотя всё
    нужное уже лежит в _last (а транскрипт — в кэше по file_id).
    """
    if not callback.data or not callback.from_user or not callback.message:
        return
    if is_busy(callback.from_user.id):
        await callback.answer("⏳ Уже обрабатываю — секунду.")
        return
    mode = callback.data.split(":", 1)[1]

    last = get_last(callback.from_user.id)
    # Режим запоминаем в любом случае — это ожидаемый сайд-эффект выбора.
    await save_user_settings(session, callback.from_user.id, default_mode=mode, reset_style=True)

    if last is None:
        await callback.answer()
        await callback.message.answer(  # type: ignore[union-attr]
            "Режим переключил. Отправь голос или текст — обработаю.",
        )
        return

    if mode == "humanizer" and last.input_type == "voice":
        await callback.answer()
        await callback.message.answer(  # type: ignore[union-attr]
            HUMANIZER_VOICE_ERROR, parse_mode="HTML"
        )
        return

    await callback.answer("Прогоняю в новом режиме…")
    async with user_lock(callback.from_user.id):
        if last.input_type == "voice":
            await _process_media_cb(callback, bot, session, skills_db, last, mode)
        else:
            from src.handlers.text import _process_text

            await _process_text(
                callback.message,  # type: ignore[arg-type]
                session,
                skills_db,
                text=last.text or "",
                mode=mode,
                style=None,
                target_lang=last.target_lang,
                db_user_id=last.db_user_id,
            )


async def _process_media_cb(callback, bot, session, skills_db, last, mode: str) -> None:
    from src.handlers.voice import _process_media

    await _process_media(
        callback.message,
        bot,
        session,
        skills_db,
        media=last.media,
        is_video=last.is_video,
        mode=mode,
        style=None,
        target_lang=last.target_lang,
        db_user_id=last.db_user_id,
        force_retranscribe=False,  # транскрипт берём из кэша — мгновенно
    )


@router.callback_query(F.data == "action:transcript")
async def on_transcript(callback: CallbackQuery) -> None:
    """Показать сырой Whisper-транскрипт последнего голосового."""
    await callback.answer()
    msg = callback.message
    if msg is None:
        return
    transcript = get_last_transcript(msg.chat.id)
    if not transcript:
        await msg.answer("Транскрипта нет — пришли голосовое ещё раз.")  # type: ignore[union-attr]
        return
    header = "🎙 <b>Дословный транскрипт</b>\n"
    body = escape_html(transcript[:3500])
    await msg.answer(  # type: ignore[union-attr]
        f"{header}<blockquote expandable><code>{body}</code></blockquote>",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "action:regenerate")
async def on_regenerate(
    callback: CallbackQuery, bot: Bot, session: AsyncSession, skills_db: SkillsDB
) -> None:
    """Re-run the last request from scratch (fresh transcription + fresh generation)."""
    if not callback.from_user or not callback.message:
        return
    if is_busy(callback.from_user.id):
        # Даблтап: раньше два конкурирующих прогона дрались за row-lock кэша.
        await callback.answer("⏳ Уже генерирую — секунду.")
        return
    await callback.answer("Перегенерирую…")

    last = get_last(callback.from_user.id)
    if last is None:
        await callback.message.answer(  # type: ignore[union-attr]
            "Нечего повторять — отправь голос или текст ещё раз."
        )
        return

    async with user_lock(callback.from_user.id):
        if last.input_type == "voice":
            await regenerate_voice(callback.message, bot, session, skills_db, last)  # type: ignore[arg-type]
        else:
            await regenerate_text(callback.message, session, skills_db, last)  # type: ignore[arg-type]


@router.callback_query(F.data == "action:other_mode")
async def on_other_mode(callback: CallbackQuery) -> None:
    await callback.answer()  # ack immediately so the button stops spinning
    msg = callback.message
    if msg is None:
        return
    text = "<b>Другой режим</b>\n\nВыбери — сразу прогоню тот же\nголос или текст ещё раз:"
    if _holds_result(msg):
        await msg.answer(text, reply_markup=reprocess_mode_keyboard(), parse_mode="HTML")
        return
    await msg.edit_text(text, reply_markup=reprocess_mode_keyboard(), parse_mode="HTML")


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
async def on_settings_reset(callback: CallbackQuery) -> None:
    """Сброс — только через подтверждение (раньше сносил всё молча)."""
    await callback.answer()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, сбросить", callback_data="settings:reset_yes"),
                InlineKeyboardButton(text="Отмена", callback_data="back:settings"),
            ]
        ]
    )
    await callback.message.edit_text(  # type: ignore[union-attr]
        "Сбросить режим, стиль и язык перевода на значения по умолчанию?",
        reply_markup=kb,
    )


@router.callback_query(F.data == "settings:reset_yes")
async def on_settings_reset_confirmed(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.from_user:
        return
    await callback.answer("Сброшено")
    await save_user_settings(session, callback.from_user.id, target_lang="en", reset=True)
    await callback.message.edit_text(  # type: ignore[union-attr]
        CHOOSE_MODE,
        reply_markup=mode_keyboard(),
        parse_mode="HTML",
    )


# ── History ──


@router.callback_query(F.data == "cmd:history")
async def on_history(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.from_user:
        return
    await callback.answer()  # ack immediately so the button stops spinning
    try:
        user = await get_or_create_user(session, telegram_user_id=callback.from_user.id)
        history = await get_user_history(session, user_id=user.id, limit=10)
    except Exception as exc:
        log.warning("history_db_unavailable", error=str(exc))
        await callback.message.edit_text(  # type: ignore[union-attr]
            DB_UNAVAILABLE,
            reply_markup=mode_keyboard(),
            parse_mode="HTML",
        )
        return

    if not history:
        await callback.message.edit_text(  # type: ignore[union-attr]
            "История пуста.",
            reply_markup=mode_keyboard(),
            parse_mode="HTML",
        )
        return

    lines = ["<b>Последние запросы</b>\n"]
    type_ru = {"voice": "голос", "text": "текст"}
    for h in history:
        mode_name = MODE_NAME.get(h.mode, h.mode)
        preview = (h.input_preview or "")[:80]
        when = h.created_at.strftime("%d.%m %H:%M") if h.created_at else ""
        kind = type_ru.get(h.input_type, h.input_type)
        lines.append(f"• {when} · {mode_name} · {kind}\n  {escape_html(preview)}…")

    await callback.message.edit_text(  # type: ignore[union-attr]
        "\n".join(lines),
        reply_markup=mode_keyboard(),
        parse_mode="HTML",
    )
