import html

from aiogram.types import BufferedInputFile, Message

# Telegram sendMessage limit: 4096 chars after entities parsing.
_TG_MSG_LIMIT = 4096
# Overhead: <blockquote><code>...</code></blockquote> + "[3/3]\n" prefix.
_WRAPPER_OVERHEAD = len("<blockquote><code></code></blockquote>") + len("[3/3]\n")
# Max chars of escaped text per chunk.
_CHUNK_LIMIT = _TG_MSG_LIMIT - _WRAPPER_OVERHEAD
# Maximum number of message parts before falling back to file.
_MAX_PARTS = 3


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def _wrap(text: str) -> str:
    return f"<blockquote><code>{text}</code></blockquote>"


def _split_escaped(escaped: str) -> list[str]:
    """Split escaped HTML text into chunks that fit in Telegram messages."""
    if len(escaped) <= _CHUNK_LIMIT:
        return [escaped]
    chunks: list[str] = []
    while escaped:
        chunks.append(escaped[:_CHUNK_LIMIT])
        escaped = escaped[_CHUNK_LIMIT:]
    return chunks


async def send_result(
    progress_msg: Message,
    result_text: str,
    reply_markup: object,
    mode: str,
) -> None:
    """Send result: single message, split into 2-3 parts, or as file."""
    escaped = escape_html(result_text)
    chunks = _split_escaped(escaped)

    # Case 1: fits in one message
    if len(chunks) == 1:
        await progress_msg.edit_text(
            _wrap(chunks[0]),
            reply_markup=reply_markup,  # type: ignore[arg-type]
            parse_mode="HTML",
        )
        return

    # Case 2: too many parts — send as file
    if len(chunks) > _MAX_PARTS:
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
        return

    # Case 3: split into 2-3 parts
    n = len(chunks)
    await progress_msg.edit_text(
        f"📨 Текст разделён на {n} части — отправляю…",
        parse_mode="HTML",
    )
    for i, chunk in enumerate(chunks, 1):
        is_last = i == n
        await progress_msg.answer(
            f"[{i}/{n}]\n{_wrap(chunk)}",
            parse_mode="HTML",
            reply_markup=reply_markup if is_last else None,  # type: ignore[arg-type]
        )
