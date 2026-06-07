from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from src.storage.models import User


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
