from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import RequestHistory, TranscriptionCache

log = structlog.get_logger()


async def cleanup_old_records(
    session: AsyncSession,
    transcription_ttl_days: int,
    history_ttl_days: int,
) -> tuple[int, int]:
    """Delete records older than the given TTLs.

    Returns (transcripts_deleted, history_deleted). Pass 0 or negative TTL to
    skip a particular table (cleanup disabled for it).
    """
    now = datetime.now(UTC)

    transcripts_deleted = 0
    if transcription_ttl_days > 0:
        cutoff = now - timedelta(days=transcription_ttl_days)
        result = await session.execute(
            delete(TranscriptionCache).where(TranscriptionCache.created_at < cutoff)
        )
        transcripts_deleted = result.rowcount or 0

    history_deleted = 0
    if history_ttl_days > 0:
        cutoff = now - timedelta(days=history_ttl_days)
        result = await session.execute(
            delete(RequestHistory).where(RequestHistory.created_at < cutoff)
        )
        history_deleted = result.rowcount or 0

    if transcripts_deleted or history_deleted:
        log.info(
            "cleanup_deleted",
            transcripts=transcripts_deleted,
            history=history_deleted,
        )

    return transcripts_deleted, history_deleted
