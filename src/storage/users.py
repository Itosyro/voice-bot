from sqlalchemy import select, update
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
    user = User(
        telegram_user_id=telegram_user_id,
        username=username,
        first_name=first_name,
        language_code=language_code,
    )
    session.add(user)
    await session.flush()
    return user


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
