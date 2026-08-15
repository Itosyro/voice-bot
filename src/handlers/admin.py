import asyncio
import html
import subprocess
from datetime import UTC, datetime, timedelta

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.handlers.callbacks import _edit_or_send
from src.migrate import send_migration
from src.services.skills_db import SkillsDB
from src.storage.db import get_session
from src.storage.models import RequestHistory, SkillIndex, User
from src.storage.users import (
    get_user_by_telegram_id,
    list_users_with_activity,
    set_user_blocked,
)
from src.ui.keyboards import admin_user_keyboard

log = structlog.get_logger()
router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_user_ids_list


def _fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M")


def _user_label(user: User) -> str:
    if user.username:
        return html.escape(f"@{user.username}")
    if user.first_name:
        return html.escape(user.first_name)
    return f"id{user.telegram_user_id}"


@router.message(Command("sync_skills"))
async def cmd_sync_skills(message: Message, skills_db: SkillsDB) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для администраторов.")
        return

    await message.answer("Синхронизирую skills...")

    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["python", "scripts/sync_skills.py"],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        await message.answer("Синхронизация не уложилась в 10 минут — прервана.")
        return

    output = proc.stdout[-2000:] if proc.stdout else ""
    errors = proc.stderr[-500:] if proc.stderr else ""

    if proc.returncode == 0:
        # Перезагружаем in-memory индекс: раньше новые skills подхватывались
        # только после рестарта бота.
        try:
            async with get_session() as session:
                fresh = await SkillsDB.load_from_db(session)
            skills_db.replace_from(fresh)
            reload_note = f"Индекс перезагружен: {len(fresh.skills)} skills."
        except Exception as exc:
            reload_note = f"Индекс НЕ перезагружен (ошибка чтения БД: {exc})."
        # Вывод шлём без parse_mode: markdown-символы в логах ломали отправку.
        await message.answer(f"Skills синхронизированы. {reload_note}\n\n{output}")
    else:
        await message.answer(f"Ошибка:\n{errors}")


@router.message(Command("migrate"))
async def cmd_migrate(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для администраторов.")
        return
    # В архиве лежат токен и ключи — в группу такое отправлять нельзя.
    if message.chat.type != "private":
        await message.answer("Только в личке с ботом.")
        return

    await message.answer("Собираю архив…")
    try:
        await send_migration(message.bot, message.chat.id)  # type: ignore[arg-type]
    except Exception as exc:
        log.warning("migrate_failed", error=str(exc))
        await message.answer(f"Не получилось собрать архив: {exc}")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для администраторов.")
        return

    week_ago = datetime.now(UTC) - timedelta(days=7)

    users_count = (await session.execute(select(func.count(User.id)))).scalar() or 0
    requests_count = (await session.execute(select(func.count(RequestHistory.id)))).scalar() or 0
    skills_count = (await session.execute(select(func.count(SkillIndex.id)))).scalar() or 0
    active_week = (
        await session.execute(
            select(func.count(func.distinct(RequestHistory.user_id))).where(
                RequestHistory.created_at >= week_ago
            )
        )
    ).scalar() or 0

    repo_stats = await session.execute(
        select(SkillIndex.source_repo, func.count(SkillIndex.id)).group_by(SkillIndex.source_repo)
    )
    repo_lines = [f"  {repo}: {cnt}" for repo, cnt in repo_stats]

    mode_stats = await session.execute(
        select(RequestHistory.mode, func.count(RequestHistory.id)).group_by(RequestHistory.mode)
    )
    mode_lines = [f"  {mode}: {cnt}" for mode, cnt in mode_stats]

    stats_text = (
        f"📊 Статистика\n\n"
        f"Пользователей всего: {users_count}\n"
        f"Активных за 7 дней: {active_week}\n"
        f"Запросов всего: {requests_count}\n"
        f"Skills: {skills_count}\n\n"
        f"Skills по репозиториям:\n"
        + "\n".join(repo_lines or ["  (пусто)"])
        + "\n\nЗапросы по режимам:\n"
        + "\n".join(mode_lines or ["  (пусто)"])
    )
    # Без parse_mode: имена репозиториев с "_"/"*" ломали Markdown-парсинг.
    await message.answer(stats_text)


async def _render_user_card(session: AsyncSession, target_id: int) -> tuple[str, object | None]:
    """Build the text + keyboard for a single user's admin card."""
    user = await get_user_by_telegram_id(session, target_id)
    if not user:
        return (f"Пользователь с id {target_id} не найден.", None)

    last_at = (
        await session.execute(
            select(func.max(RequestHistory.created_at)).where(RequestHistory.user_id == user.id)
        )
    ).scalar()

    mode_rows = await session.execute(
        select(RequestHistory.mode, func.count(RequestHistory.id))
        .where(RequestHistory.user_id == user.id)
        .group_by(RequestHistory.mode)
    )
    mode_lines = [f"  {mode}: {cnt}" for mode, cnt in mode_rows] or ["  —"]

    status = "🚫 ЗАБЛОКИРОВАН" if user.is_blocked else "✅ активен"
    admin_mark = " 👑 админ" if _is_admin(user.telegram_user_id) else ""

    text = (
        f"👤 {_user_label(user)}{admin_mark}\n"
        f"Статус: {status}\n\n"
        f"telegram_id: <code>{user.telegram_user_id}</code>\n"
        f"username: {html.escape('@' + user.username) if user.username else '—'}\n"
        f"имя: {html.escape(user.first_name) if user.first_name else '—'}\n"
        f"запросов: {user.total_requests}\n"
        f"голос (сек): {user.total_voice_seconds}\n"
        f"режим/стиль: {user.default_mode or '—'} / {user.default_style or '—'}\n"
        f"зарегистрирован: {_fmt_dt(user.created_at)}\n"
        f"последняя активность: {_fmt_dt(last_at)}\n\n"
        f"По режимам:\n" + "\n".join(mode_lines)
    )
    kb = admin_user_keyboard(user.telegram_user_id, user.is_blocked)
    return (text, kb)


@router.message(Command("users"))
async def cmd_users(message: Message, session: AsyncSession) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для администраторов.")
        return

    rows = await list_users_with_activity(session, limit=50)
    if not rows:
        await message.answer("Пользователей пока нет.")
        return

    lines = [f"👥 Пользователи ({len(rows)}):\n"]
    for user, last_at in rows:
        flag = "🚫" if user.is_blocked else "👑" if _is_admin(user.telegram_user_id) else "•"
        lines.append(
            f"{flag} {_user_label(user)} — {user.total_requests} зап. | "
            f"посл.: {_fmt_dt(last_at)} | id <code>{user.telegram_user_id}</code>"
        )
    lines.append(
        "\nКарточка: /user &lt;id&gt;  ·  бан: /ban &lt;id&gt;  ·  снять: /unban &lt;id&gt;"
    )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("user"))
async def cmd_user(message: Message, session: AsyncSession) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для администраторов.")
        return

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Использование: /user <telegram_id>")
        return

    text, kb = await _render_user_card(session, int(parts[1]))
    await message.answer(text, reply_markup=kb, parse_mode="HTML")  # type: ignore[arg-type]


async def _set_block_and_report(
    message: Message, session: AsyncSession, target_id: int, blocked: bool
) -> None:
    if target_id in settings.admin_user_ids_list and blocked:
        await message.answer("Нельзя заблокировать администратора.")
        return
    ok = await set_user_blocked(session, target_id, blocked)
    if not ok:
        await message.answer(f"Пользователь с id {target_id} не найден.")
        return
    verb = "заблокирован" if blocked else "разблокирован"
    await message.answer(f"Готово: пользователь {target_id} {verb}.")


@router.message(Command("ban"))
async def cmd_ban(message: Message, session: AsyncSession) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для администраторов.")
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Использование: /ban <telegram_id>")
        return
    await _set_block_and_report(message, session, int(parts[1]), blocked=True)


@router.message(Command("unban"))
async def cmd_unban(message: Message, session: AsyncSession) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        await message.answer("Только для администраторов.")
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("Использование: /unban <telegram_id>")
        return
    await _set_block_and_report(message, session, int(parts[1]), blocked=False)


@router.callback_query(F.data.startswith("admin:"))
async def on_admin_action(callback: CallbackQuery, session: AsyncSession) -> None:
    if not callback.from_user or not _is_admin(callback.from_user.id):
        await callback.answer("Только для администраторов.", show_alert=True)
        return
    if not callback.data:
        return

    _, action, raw_id = callback.data.split(":", 2)
    if not raw_id.lstrip("-").isdigit():
        await callback.answer()
        return
    target_id = int(raw_id)

    if action in ("ban", "unban"):
        blocked = action == "ban"
        if blocked and target_id in settings.admin_user_ids_list:
            await callback.answer("Нельзя заблокировать администратора.", show_alert=True)
            return
        await set_user_blocked(session, target_id, blocked)
        await callback.answer("Заблокирован." if blocked else "Разблокирован.")

    text, kb = await _render_user_card(session, target_id)
    # Через общий хелпер: «Обновить» на неизменившейся карточке даёт
    # «message is not modified», а карточка старше 48 часов прилетает
    # InaccessibleMessage — у неё нет edit_text вообще.
    await _edit_or_send(callback.message, text, reply_markup=kb, parse_mode="HTML")
