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


def _split_escaped(escaped: str, limit: int = _CHUNK_LIMIT) -> list[str]:
    """Split escaped HTML text into chunks that fit in Telegram messages."""
    if len(escaped) <= limit:
        return [escaped]
    chunks: list[str] = []
    while escaped:
        chunks.append(escaped[:limit])
        escaped = escaped[limit:]
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


async def send_chunk(
    target: Message,
    header: str,
    text: str,
    reply_markup: object | None = None,
) -> None:
    """Send one streaming chunk's text as new message(s).

    `header` is HTML-formatted and prepended to the first message. If the
    text exceeds Telegram's per-message limit, it is split into [i/n] parts.
    `reply_markup` is attached to the LAST sub-message only.
    """
    escaped = escape_html(text)
    # Reserve room for header line + worst-case " [99/99]" suffix.
    reserved = len(header) + 1 + len(" [99/99]")
    body_limit = max(200, _CHUNK_LIMIT - reserved)
    chunks = _split_escaped(escaped, limit=body_limit)
    n = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        is_last = i == n
        label = f"{header} [{i}/{n}]" if n > 1 else header
        body = f"{label}\n{_wrap(chunk)}" if label else _wrap(chunk)
        await target.answer(
            body,
            parse_mode="HTML",
            reply_markup=reply_markup if is_last else None,  # type: ignore[arg-type]
        )
