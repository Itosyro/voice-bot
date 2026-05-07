import html

from aiogram.types import BufferedInputFile, Message

# Telegram sendMessage limit: 4096 chars after entities parsing.
# We use a safe threshold accounting for HTML wrapper overhead.
_TG_MSG_LIMIT = 4096
_SAFE_TEXT_LIMIT = 3800


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


async def send_result(
    progress_msg: Message,
    result_text: str,
    reply_markup: object,
    mode: str,
) -> None:
    """Send result as inline message or as .txt file if too long."""
    escaped = escape_html(result_text)
    final = f"<blockquote><code>{escaped}</code></blockquote>"

    if len(final) <= _TG_MSG_LIMIT:
        await progress_msg.edit_text(
            final,
            reply_markup=reply_markup,  # type: ignore[arg-type]
            parse_mode="HTML",
        )
        return

    # Text is too long — send as file
    await progress_msg.edit_text(
        "📄 Текст слишком длинный — отправляю файлом…",
        parse_mode="HTML",
    )
    file_bytes = result_text.encode("utf-8")
    doc = BufferedInputFile(file_bytes, filename=f"{mode}_result.txt")
    await progress_msg.answer_document(
        doc,
        caption="📄 Результат в файле (текст превысил лимит Telegram)",
        reply_markup=reply_markup,  # type: ignore[arg-type]
    )
