#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DB_METHOD_MARKER = "def active_focus_session(self, chat_id: int)"
BOT_MARKER = "Уже идёт другой фокус-раунд"

DB_ANCHOR = """    def start_focus_session(self, chat_id: int, occurrence_id: int | None, source: str, minutes: int) -> int:\n"""
DB_INSERT = """    def active_focus_session(self, chat_id: int):
        with self.conn() as db:
            return db.execute(
                \"\"\"
                SELECT * FROM focus_sessions
                WHERE chat_id=? AND result IS NULL AND due_at_utc>?
                ORDER BY started_at_utc DESC, id DESC
                LIMIT 1
                \"\"\",
                (chat_id, iso(utcnow())),
            ).fetchone()

"""

OCC_OLD = """    _, _, occurrence_id, minutes = callback.data.split(\":\")
    session_id = DB.start_focus_session(callback.message.chat.id, int(occurrence_id), \"reminder\", int(minutes))
"""
OCC_NEW = """    _, _, occurrence_id, minutes = callback.data.split(\":\")
    active = DB.active_focus_session(callback.message.chat.id)
    if active:
        await callback.answer(\"Уже идёт другой фокус-раунд. Сначала закончи его.\", show_alert=True)
        return
    session_id = DB.start_focus_session(callback.message.chat.id, int(occurrence_id), \"reminder\", int(minutes))
"""

RESCUE_OLD = """    raw = int(callback.data.rsplit(\":\", 1)[1])
    occurrence_id = raw or None
    session_id = DB.start_focus_session(callback.message.chat.id, occurrence_id, \"doomscroll_rescue\", 5)
"""
RESCUE_NEW = """    raw = int(callback.data.rsplit(\":\", 1)[1])
    occurrence_id = raw or None
    active = DB.active_focus_session(callback.message.chat.id)
    if active:
        await callback.answer(\"Уже идёт другой фокус-раунд. Сначала закончи его.\", show_alert=True)
        return
    session_id = DB.start_focus_session(callback.message.chat.id, occurrence_id, \"doomscroll_rescue\", 5)
"""


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_db(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if DB_METHOD_MARKER in text:
        return False
    text = replace_once(text, DB_ANCHOR, DB_INSERT + DB_ANCHOR, "db.py")
    path.write_text(text, encoding="utf-8")
    return True


def patch_bot(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if BOT_MARKER in text:
        return False
    text = replace_once(text, OCC_OLD, OCC_NEW, "bot.py occurrence start")
    text = replace_once(text, RESCUE_OLD, RESCUE_NEW, "bot.py rescue start")
    path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default="/opt/dvizh-telegram/telegram_bot")
    args = parser.parse_args()
    package = Path(args.package)
    if not package.is_dir():
        raise SystemExit(f"Telegram package not found: {package}")
    db_changed = patch_db(package / "db.py")
    bot_changed = patch_bot(package / "bot.py")
    print(f"runtime patch: db_changed={db_changed} bot_changed={bot_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
