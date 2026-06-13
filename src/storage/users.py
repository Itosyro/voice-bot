from datetime import datetime

from sqlalchemy import func as sa_func
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.storage.models import RequestHistory, User


async def get_or_create_user(
    session: AsyncSession,
    telegram_user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    language_code: str | None = None,
) -> User:
    stmt = select(User).where(User.telegram_user_id == telegram_user_id)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user:
        return user

    # Atomic insert: if a concurrent request already inserted this user
    # (e.g. several messages sent in quick succession), do nothing instead of
    # raising IntegrityError, then re-fetch the guaranteed-present row.
    insert_stmt = (
        pg_insert(User)
        .values(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            language_code=language_code,
        )
        .on_conflict_do_nothing(index_elements=["telegram_user_id"])
    )
    await session.execute(insert_stmt)
    await session.flush()

    return (
        await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    ).scalar_one()


async def update_user_settings(
    session: AsyncSession,
    telegram_user_id: int,
    **kwargs: str | int | bool | None,
) -> None:
    if not kwargs:
        return
    stmt = (
        update(User)
        .where(User.telegram_user_id == telegram_user_id)
        .values(**kwargs, updated_at=func.now())
    )
    await session.execute(stmt)


async def get_user_by_telegram_id(session: AsyncSession, telegram_user_id: int) -> User | None:
    return (
        await session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    ).scalar_one_or_none()


async def set_user_blocked(session: AsyncSession, telegram_user_id: int, blocked: bool) -> bool:
    """Set the block flag for a user. Returns True if a row was updated."""
    result = await session.execute(
        update(User)
        .where(User.telegram_user_id == telegram_user_id)
        .values(is_blocked=blocked, updated_at=func.now())
    )
    return (result.rowcount or 0) > 0


async def is_user_blocked(session: AsyncSession, telegram_user_id: int) -> bool:
    blocked = (
        await session.execute(
            select(User.is_blocked).where(User.telegram_user_id == telegram_user_id)
        )
    ).scalar_one_or_none()
    return bool(blocked)


async def list_users_with_activity(
    session: AsyncSession, limit: int = 50
) -> list[tuple[User, datetime | None]]:
    """Return users with their last request time, most-active first."""
    last_activity = (
        select(
            RequestHistory.user_id,
            sa_func.max(RequestHistory.created_at).label("last_at"),
        )
        .group_by(RequestHistory.user_id)
        .subquery()
    )
    stmt = (
        select(User, last_activity.c.last_at)
        .outerjoin(last_activity, last_activity.c.user_id == User.id)
        .order_by(User.total_requests.desc(), User.created_at.desc())
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return [(user, last_at) for user, last_at in rows]
