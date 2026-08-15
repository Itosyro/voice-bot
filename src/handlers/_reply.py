import contextlib
import time

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message

from src.config import settings
from src.handlers._last import save_last_result, save_result_for_message
from src.services.llm import OnDelta
from src.utils import escape_html

# Telegram считает лимит 4096 в UTF-16 code units, причём ПОСЛЕ парсинга
# сущностей («1-4096 characters after entities parsing»): теги и `&amp;`
# схлопываются, поэтому меряем ИСХОДНЫЙ текст, а не HTML. Кириллица = 1 юнит,
# эмодзи = 2 — поэтому юниты, а не len(). Остаток до 4096 — на «i/N» и футер.
_CHUNK = 3500
_MAX_PARTS = 10  # beyond this, send the full text as a .txt file instead


def tg_len(text: str) -> int:
    """Длина строки в UTF-16 code units — так её считает Telegram."""
    return len(text.encode("utf-16-le")) // 2


def split_text(text: str) -> list[str]:
    """Split text into Telegram-sized chunks at paragraph → sentence → hard boundaries.

    Границы меряем в UTF-16 юнитах: текст с эмодзи через слово раньше пробивал
    лимит 4096 и ронял отправку готового ответа (MESSAGE_TOO_LONG).
    """
    if tg_len(text) <= _CHUNK:
        return [text]
    parts: list[str] = []
    while text:
        if tg_len(text) <= _CHUNK:
            parts.append(text)
            break
        # Максимальный префикс, влезающий в _CHUNK UTF-16 юнитов: len() всегда
        # <= tg_len(), поэтому стартуем с _CHUNK символов и ужимаем.
        window = min(len(text), _CHUNK)
        # window > 1 — страховка от бесконечного цикла: int(1 * 0.9) == 0.
        while window > 1 and tg_len(text[:window]) > _CHUNK:
            window = max(1, int(window * 0.9))
        split_at = text.rfind("\n\n", 0, window)
        if split_at <= 0:
            split_at = text.rfind(". ", 0, window)
        if split_at <= 0:
            # rfind может вернуть 0 (граница в самом начале) — это дало бы
            # часть из одного символа; режем по жёсткой границе.
            split_at = window
        else:
            split_at += 1
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    return parts


def _block(text: str, expandable: bool = False) -> str:
    """Wrap text in a quoted, tap-to-copy block (monospace, copies on tap).

    expandable=True — свёрнутая цитата (для многочастных простыней, чтобы
    результат не занимал три экрана чата).
    """
    tag = "<blockquote expandable>" if expandable else "<blockquote>"
    return f"{tag}<code>{escape_html(text)}</code></blockquote>"


def make_draft_streamer(bot: Bot, chat_id: int) -> OnDelta | None:
    """Стриминг-превью через sendMessageDraft (Bot API 9.5+): эфемерный драфт
    показывает генерацию на лету; финальный ответ доставляется как обычно.

    Опт-ин (enable_draft_streaming=False по умолчанию): включать после проверки
    вживую — прошлая попытка оставляла «осиротевшие» пузыри (грабли №1).
    Ошибки драфта глушим: превью не стоит сломанного ответа.
    """
    if not settings.enable_draft_streaming:
        return None
    if not hasattr(bot, "send_message_draft"):  # aiogram < 3.26
        return None

    draft_id = int(time.monotonic() * 1000) % 2_000_000_000
    last_sent = 0.0

    async def on_delta(accumulated: str) -> None:
        nonlocal last_sent
        now = time.monotonic()
        if now - last_sent < 1.2:  # не душим Telegram апдейтами
            return
        last_sent = now
        with contextlib.suppress(Exception):  # превью best-effort
            await bot.send_message_draft(chat_id, draft_id, text=accumulated[:4000])

    return on_delta


async def send_result(
    message: Message,
    progress_msg: Message,
    result_text: str,
    skills_info: str,
    timing: str,
    kb: InlineKeyboardMarkup,
) -> None:
    """Send the final result as a copyable quote block, splitting or filing if long."""
    if not result_text or not result_text.strip():
        # Never edit a message to empty text — Telegram rejects it and the user
        # would see a blank reply. Surface a clear error instead (с клавиатурой,
        # чтобы юзер не остался без кнопок).
        await progress_msg.edit_text("⚠ Пустой ответ от модели. Попробуй ещё раз.", reply_markup=kb)
        return

    save_last_result(message.chat.id, result_text)

    parts = split_text(result_text)
    # Footer (skills/timing) goes outside the copy block as plain text.
    footer = escape_html(skills_info + timing)

    if len(parts) == 1:
        await progress_msg.edit_text(_block(parts[0]) + footer, reply_markup=kb, parse_mode="HTML")
        save_result_for_message(message.chat.id, progress_msg.message_id, result_text)
        return

    if len(parts) > _MAX_PARTS:
        document = BufferedInputFile(result_text.encode("utf-8"), filename="result.txt")
        await progress_msg.edit_text(
            f"📋 Ответ большой ({len(result_text)} симв.) — отправляю файлом."
        )
        sent_doc = await message.answer_document(
            document, caption=f"📄 Результат{skills_info}{timing}", reply_markup=kb
        )
        # Кнопки под файлом тоже должны отдавать ИМЕННО этот результат, а не
        # последний по чату (грабли №24: фикс не доехал до .txt-фолбэка).
        save_result_for_message(message.chat.id, sent_doc.message_id, result_text)
        return

    total_parts = len(parts)
    await progress_msg.edit_text(
        f"📋 Ответ не влез в одно сообщение — шлю по частям ({total_parts} шт.):"
    )
    for i, part in enumerate(parts[:-1], 1):
        sent = await message.answer(
            f"<b>{i}/{total_parts}</b>\n{_block(part, expandable=True)}", parse_mode="HTML"
        )
        save_result_for_message(message.chat.id, sent.message_id, result_text)
    last_sent = await message.answer(
        f"<b>{total_parts}/{total_parts}</b>\n{_block(parts[-1], expandable=True)}{footer}",
        reply_markup=kb,
        parse_mode="HTML",
    )
    save_result_for_message(message.chat.id, last_sent.message_id, result_text)
