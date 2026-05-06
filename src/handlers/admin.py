import asyncio
import subprocess

import structlog
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.storage.models import RequestHistory, SkillIndex, User

log = structlog.get_logger()
router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_user_ids_list


@router.message(Command("sync_skills"))
async def cmd_sync_skills(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для администраторов.")
        return

    await message.answer("Синхронизирую skills...")

    proc = await asyncio.to_thread(
        subprocess.run,
        ["python", "scripts/sync_skills.py"],
        capture_output=True,
        text=True,
        timeout=600,
    )

    output = proc.stdout[-2000:] if proc.stdout else ""
    errors = proc.stderr[-500:] if proc.stderr else ""

    if proc.returncode == 0:
        msg = f"Skills синхронизированы.\n\n```\n{output}\n```"
        await message.answer(msg, parse_mode="Markdown")
    else:
        msg = f"Ошибка:\n```\n{errors}\n```"
        await message.answer(msg, parse_mode="Markdown")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для администраторов.")
        return

    users_count = (await session.execute(select(func.count(User.id)))).scalar() or 0
    requests_count = (
        await session.execute(select(func.count(RequestHistory.id)))
    ).scalar() or 0
    skills_count = (
        await session.execute(select(func.count(SkillIndex.id)))
    ).scalar() or 0

    repo_stats = await session.execute(
        select(SkillIndex.source_repo, func.count(SkillIndex.id)).group_by(
            SkillIndex.source_repo
        )
    )
    repo_lines = [f"  {repo}: {cnt}" for repo, cnt in repo_stats]

    mode_stats = await session.execute(
        select(RequestHistory.mode, func.count(RequestHistory.id)).group_by(
            RequestHistory.mode
        )
    )
    mode_lines = [f"  {mode}: {cnt}" for mode, cnt in mode_stats]

    stats_text = (
        f"**Статистика:**\n\n"
        f"Пользователей: {users_count}\n"
        f"Запросов: {requests_count}\n"
        f"Skills: {skills_count}\n\n"
        f"**Skills по репозиториям:**\n"
        + "\n".join(repo_lines or ["  (пусто)"])
        + "\n\n**Запросы по режимам:**\n"
        + "\n".join(mode_lines or ["  (пусто)"])
    )
    await message.answer(stats_text, parse_mode="Markdown")
