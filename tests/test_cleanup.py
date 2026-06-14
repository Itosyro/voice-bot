"""Tests for src.storage.cleanup.cleanup_old_records."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.storage.cleanup import cleanup_old_records


def _make_session(transcripts_rowcount: int, history_rowcount: int) -> AsyncMock:
    """Build a fake AsyncSession whose execute() returns results with given rowcounts,
    in the order: transcription_cache delete first, then request_history delete.
    """
    session = AsyncMock()

    transcripts_result = MagicMock(rowcount=transcripts_rowcount)
    history_result = MagicMock(rowcount=history_rowcount)
    session.execute = AsyncMock(side_effect=[transcripts_result, history_result])
    return session


@pytest.mark.asyncio
async def test_deletes_rows_older_than_ttl():
    session = _make_session(transcripts_rowcount=3, history_rowcount=5)

    transcripts_deleted, history_deleted = await cleanup_old_records(
        session, transcription_ttl_days=1, history_ttl_days=30
    )

    assert transcripts_deleted == 3
    assert history_deleted == 5
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_keeps_newer_rows_returns_zero():
    session = _make_session(transcripts_rowcount=0, history_rowcount=0)

    transcripts_deleted, history_deleted = await cleanup_old_records(
        session, transcription_ttl_days=1, history_ttl_days=30
    )

    assert transcripts_deleted == 0
    assert history_deleted == 0
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_ttl_zero_skips_transcription_table():
    session = AsyncMock()
    history_result = MagicMock(rowcount=2)
    session.execute = AsyncMock(return_value=history_result)

    transcripts_deleted, history_deleted = await cleanup_old_records(
        session, transcription_ttl_days=0, history_ttl_days=30
    )

    assert transcripts_deleted == 0
    assert history_deleted == 2
    # only the history delete should have been executed
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_ttl_negative_skips_history_table():
    session = AsyncMock()
    transcripts_result = MagicMock(rowcount=4)
    session.execute = AsyncMock(return_value=transcripts_result)

    transcripts_deleted, history_deleted = await cleanup_old_records(
        session, transcription_ttl_days=1, history_ttl_days=-1
    )

    assert transcripts_deleted == 4
    assert history_deleted == 0
    assert session.execute.await_count == 1


@pytest.mark.asyncio
async def test_both_ttls_zero_skips_everything():
    session = AsyncMock()
    session.execute = AsyncMock()

    transcripts_deleted, history_deleted = await cleanup_old_records(
        session, transcription_ttl_days=0, history_ttl_days=0
    )

    assert transcripts_deleted == 0
    assert history_deleted == 0
    session.execute.assert_not_awaited()
