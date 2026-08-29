from datetime import date, datetime
from zoneinfo import ZoneInfo

from telegram_bot.weekly_store import WeeklyStore, weekday_mask

UTC = ZoneInfo("UTC")


def test_weekly_and_once(tmp_path):
    path = tmp_path / "telegram.db"
    store = WeeklyStore(str(path))
    weekly = store.add_weekly(
        chat_id=1,
        title="Работа",
        kind="work",
        weekdays_mask=weekday_mask({0, 2, 4}),
        start_local="10:00",
        duration_minutes=480,
        reminder_minutes=30,
    )
    once = store.add_once(
        chat_id=1,
        title="Документы",
        kind="documents",
        date_local=date(2026, 8, 31),
        start_local="15:30",
        duration_minutes=60,
        reminder_minutes=60,
    )
    assert weekly != once
    created = store.ensure_range(1, date(2026, 8, 29), 7, "Europe/Moscow")
    assert created == 4
    assert store.ensure_range(1, date(2026, 8, 29), 7, "Europe/Moscow") == 0
    rows = store.list_occurrences(1, date(2026, 8, 29), 7)
    assert len(rows) == 4
    assert any(row.title == "Документы" for row in rows)


def test_expire_no_backlog(tmp_path):
    store = WeeklyStore(str(tmp_path / "db.sqlite"))
    store.add_once(
        chat_id=1,
        title="Встреча",
        kind="friend",
        date_local=date(2026, 8, 29),
        start_local="10:00",
        duration_minutes=60,
        reminder_minutes=0,
    )
    store.ensure_range(1, date(2026, 8, 29), 1, "UTC")
    assert store.expire_before(1, date(2026, 8, 30)) == 1
    row = store.list_occurrences(1, date(2026, 8, 29), 1)[0]
    assert row.status == "skipped"


def test_reminder_and_status(tmp_path):
    store = WeeklyStore(str(tmp_path / "db.sqlite"))
    store.add_once(
        chat_id=1,
        title="Дело",
        kind="errand",
        date_local=date(2026, 8, 29),
        start_local="18:00",
        duration_minutes=30,
        reminder_minutes=30,
    )
    store.ensure_range(1, date(2026, 8, 29), 1, "UTC")
    row = store.list_occurrences(1, date(2026, 8, 29), 1)[0]
    due = store.due_for_reminder(1, datetime(2026, 8, 29, 17, 30, tzinfo=UTC))
    assert [item.id for item in due] == [row.id]
    store.mark_reminder_sent(1, row.id)
    assert store.due_for_reminder(1, datetime(2026, 8, 29, 17, 31, tzinfo=UTC)) == []
    assert store.set_occurrence_status(1, row.id, "done") is True
    assert store.set_occurrence_status(1, row.id, "done") is False
