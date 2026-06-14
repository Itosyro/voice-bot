from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message

_CHUNK = 3800  # max chars per Telegram message (limit is 4096, leave room for headers)
_MAX_PARTS = 10  # beyond this, send the full text as a .txt file instead


def split_text(text: str) -> list[str]:
    """Split text into Telegram-sized chunks at paragraph → sentence → hard boundaries."""
    if len(text) <= _CHUNK:
        return [text]
    parts: list[str] = []
    while text:
        if len(text) <= _CHUNK:
            parts.append(text)
            break
        split_at = text.rfind("\n\n", 0, _CHUNK)
        if split_at == -1:
            split_at = text.rfind(". ", 0, _CHUNK)
        if split_at == -1:
            split_at = _CHUNK
        else:
            split_at += 1
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    return parts


async def send_result(
    message: Message,
    progress_msg: Message,
    result_text: str,
    skills_info: str,
    timing: str,
    kb: InlineKeyboardMarkup,
) -> None:
    """Send the final result, splitting into parts or falling back to a .txt file."""
    if not result_text or not result_text.strip():
        # Never edit a message to empty text — Telegram rejects it and the user
        # would see a blank reply. Surface a clear error instead.
        await progress_msg.edit_text("⚠ Пустой ответ от модели. Попробуй ещё раз.")
        return

    parts = split_text(result_text)

    if len(parts) == 1:
        await progress_msg.edit_text(parts[0] + skills_info + timing, reply_markup=kb)
        return

    if len(parts) > _MAX_PARTS:
        document = BufferedInputFile(result_text.encode("utf-8"), filename="result.txt")
        await progress_msg.edit_text(
            f"📋 Ответ слишком длинный ({len(result_text)} симв.) — отправляю файлом."
        )
        await message.answer_document(
            document, caption=f"📄 Результат{skills_info}{timing}", reply_markup=kb
        )
        return

    total_parts = len(parts)
    await progress_msg.edit_text(f"📋 Длинный ответ — {total_parts} части:")
    for i, part in enumerate(parts[:-1], 1):
        await message.answer(f"📝 {i}/{total_parts}:\n\n{part}")
    await message.answer(
        f"📝 {total_parts}/{total_parts}:\n\n{parts[-1]}{skills_info}{timing}",
        reply_markup=kb,
    )
