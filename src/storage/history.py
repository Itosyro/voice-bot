from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import RequestHistory, User


async def save_request(
    session: AsyncSession,
    user_id: int,
    mode: str,
    style: str,
    input_type: str,
    input_length: int | None = None,
    input_preview: str | None = None,
    output_text: str | None = None,
    output_length: int | None = None,
    llm_model: str | None = None,
    transcription_ms: int | None = None,
    llm_ms: int | None = None,
    total_ms: int | None = None,
    error: str | None = None,
) -> RequestHistory:
    record = RequestHistory(
        user_id=user_id,
        mode=mode,
        style=style,
        input_type=input_type,
        input_length=input_length,
        input_preview=input_preview,
        output_text=output_text,
        output_length=output_length,
        llm_model=llm_model,
        transcription_ms=transcription_ms,
        llm_ms=llm_ms,
        total_ms=total_ms,
        error=error,
    )
    session.add(record)
    await session.flush()

    # Increment total_requests counter
    stmt = (
        update(User)
        .where(User.id == user_id)
        .values(total_requests=User.total_requests + 1)
    )
    await session.execute(stmt)

    return record


async def get_user_history(
    session: AsyncSession,
    user_id: int,
    limit: int = 10,
) -> list[RequestHistory]:
    stmt = (
        select(RequestHistory)
        .where(RequestHistory.user_id == user_id)
        .order_by(RequestHistory.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
