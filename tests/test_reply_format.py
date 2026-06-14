from unittest.mock import AsyncMock, MagicMock

import pytest

from src.handlers._reply import _block, send_result, split_text


def test_block_is_copyable_quote_and_escapes_html():
    out = _block('say <hi> & "bye"')
    assert out.startswith("<blockquote><code>")
    assert out.endswith("</code></blockquote>")
    # HTML-breaking chars are escaped so parse_mode=HTML can't choke on LLM output.
    assert "&lt;hi&gt;" in out
    assert "&amp;" in out


def test_split_text_keeps_parts_within_limit():
    parts = split_text("word. " * 2000)
    assert len(parts) > 1
    assert all(len(p) <= 3500 for p in parts)


@pytest.mark.asyncio
async def test_send_result_single_part_uses_html_copy_block():
    progress = MagicMock(edit_text=AsyncMock())
    message = MagicMock(answer=AsyncMock())
    kb = MagicMock()

    await send_result(message, progress, "polished text", "", "", kb)

    progress.edit_text.assert_awaited_once()
    sent_text = progress.edit_text.call_args.args[0]
    assert "<blockquote><code>polished text</code></blockquote>" in sent_text
    assert progress.edit_text.call_args.kwargs.get("parse_mode") == "HTML"


@pytest.mark.asyncio
async def test_send_result_blank_shows_error_not_empty():
    progress = MagicMock(edit_text=AsyncMock())
    message = MagicMock(answer=AsyncMock())

    await send_result(message, progress, "   ", "", "", MagicMock())

    sent_text = progress.edit_text.call_args.args[0]
    assert "Пустой ответ" in sent_text
