from __future__ import annotations

import hashlib
import html
import hmac
import sqlite3
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

UTC = timezone.utc
VERSION = "2026.08.29-webweek.1"

KIND_LABELS = {
    "work": "💼 Работа",
    "rest": "🛋 Отдых",
    "friend": "🤝 Встреча",
    "errand": "📍 Дела",
    "documents": "📄 Документы",
    "health": "🩺 Здоровье",
    "gym": "🏋️ Зал",
    "volleyball": "🏐 Волейбол",
    "other": "• Разное",
}
WEEKDAY_MAP = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}
WEEKDAY_LABELS = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def iso(value: datetime | None = None) -> str:
    return (value or utcnow()).astimezone(UTC).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_hhmm(value: str) -> tuple[int, int]:
    raw = value.strip()
    parts = raw.split(":", 1)
    if len(parts) != 2:
        raise ValueError("Время должно быть в формате ЧЧ:ММ")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Некорректное время")
    return hour, minute


def local_to_utc(day: date, hhmm: str, timezone_name: str) -> datetime:
    hour, minute = parse_hhmm(hhmm)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(timezone_name)).astimezone(UTC)


def weekday_mask_from_text(value: str) -> int:
    raw = value.strip().lower().replace(",", " ")
    aliases = {
        "каждый день": set(range(7)),
        "ежедневно": set(range(7)),
        "будни": {0, 1, 2, 3, 4},
        "пн ср пт": {0, 2, 4},
        "вт чт сб": {1, 3, 5},
    }
    days = aliases.get(raw)
    if days is None:
        tokens = [token for token in raw.split() if token]
        days = {WEEKDAY_MAP[token] for token in tokens if token in WEEKDAY_MAP}
    if not days:
        raise ValueError("Укажи дни, например: пн ср пт")
    mask = 0
    for day in days:
        mask |= 1 << day
    return mask


def describe_weekdays(mask: int | None) -> str:
    if mask is None:
        return ""
    if mask == 0b1111111:
        return "каждый день"
    if mask == sum(1 << day for day in range(5)):
        return "по будням"
    return " ".join(label for idx, label in enumerate(WEEKDAY_LABELS) if mask & (1 << idx))


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _fmt_duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} мин"
    hours, rest = divmod(minutes, 60)
    return f"{hours} ч" if rest == 0 else f"{hours} ч {rest} мин"


def _status_icon(status: str) -> str:
    return {"pending": "○", "done": "✅", "skipped": "—"}.get(status, "○")


def inject_main_entry(payload: bytes, content_type: str, request_path: str) -> bytes:
    """Inject one small week shortcut into the existing SPA without editing its files."""
    if request_path not in {"/", "/index.html"}:
        return payload
    if "text/html" not in (content_type or "").lower():
        return payload
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload
    marker = 'id="dvizh-week-shortcut"'
    if marker in text or "</body>" not in text:
        return payload
    shortcut = """
<a id="dvizh-week-shortcut" href="/week" aria-label="Открыть недельный график" style="position:fixed;right:16px;bottom:calc(92px + env(safe-area-inset-bottom,0px));z-index:9998;background:#baff24;color:#0b0d08;text-decoration:none;font:800 14px/1 system-ui,-apple-system,Segoe UI,sans-serif;padding:13px 16px;border-radius:999px;box-shadow:0 10px 35px #0008;border:1px solid #d7ff80">🗓 Неделя</a>
"""
    return text.replace("</body>", shortcut + "</body>", 1).encode("utf-8")


@dataclass(frozen=True)
class WebUser:
    chat_id: int
    timezone: str


class WeekStore:
    def __init__(self, path: str):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def user(self) -> WebUser:
        if not self.path.exists():
            raise RuntimeError("Telegram-база пока недоступна")
        with self.connect() as db:
            rows = db.execute("SELECT chat_id,timezone FROM users WHERE authorized=1 ORDER BY chat_id").fetchall()
        if not rows:
            raise RuntimeError("Telegram ещё не привязан к ДВИЖу")
        if len(rows) != 1:
            raise RuntimeError("Найдено несколько Telegram-чатов; веб-неделя v1 ожидает один")
        timezone_name = str(rows[0]["timezone"] or "Europe/Moscow")
        try:
            ZoneInfo(timezone_name)
        except Exception:
            timezone_name = "Europe/Moscow"
        return WebUser(int(rows[0]["chat_id"]), timezone_name)

    def ensure_schema(self) -> None:
        with self.connect() as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = {"schedule_items", "schedule_occurrences"} - tables
            if missing:
                raise RuntimeError("Недельный график в Telegram ещё не установлен")

    def expire_before(self, chat_id: int, day: date) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE schedule_occurrences SET status='skipped',completed_at_utc=? WHERE chat_id=? AND status='pending' AND due_date_local<?",
                (iso(), chat_id, day.isoformat()),
            )

    def ensure_range(self, user: WebUser, start_day: date, days: int) -> None:
        with self.connect() as db:
            items = db.execute("SELECT * FROM schedule_items WHERE chat_id=? AND enabled=1 ORDER BY id", (user.chat_id,)).fetchall()
            for offset in range(days):
                day = start_day + timedelta(days=offset)
                for item in items:
                    recurrence = str(item["recurrence"])
                    if recurrence == "once":
                        if str(item["date_local"] or "") != day.isoformat():
                            continue
                    else:
                        mask = int(item["weekdays_mask"] or 0)
                        if not (mask & (1 << day.weekday())):
                            continue
                    start_at = local_to_utc(day, str(item["start_local"]), user.timezone)
                    end_at = start_at + timedelta(minutes=int(item["duration_minutes"]))
                    db.execute(
                        """
                        INSERT OR IGNORE INTO schedule_occurrences(
                          schedule_item_id,chat_id,due_date_local,title,kind,start_at_utc,end_at_utc,
                          reminder_minutes,created_at_utc
                        ) VALUES(?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            int(item["id"]), user.chat_id, day.isoformat(), str(item["title"]), str(item["kind"]),
                            iso(start_at), iso(end_at), int(item["reminder_minutes"]), iso(),
                        ),
                    )

    def occurrences(self, user: WebUser, start_day: date, days: int = 7) -> list[sqlite3.Row]:
        end_day = start_day + timedelta(days=days - 1)
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM schedule_occurrences WHERE chat_id=? AND due_date_local BETWEEN ? AND ? ORDER BY due_date_local,start_at_utc,id",
                (user.chat_id, start_day.isoformat(), end_day.isoformat()),
            ).fetchall()

    def items(self, user: WebUser) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute("SELECT * FROM schedule_items WHERE chat_id=? ORDER BY enabled DESC,start_local,id", (user.chat_id,)).fetchall()

    def add_item(self, user: WebUser, data: dict[str, str], today: date) -> int:
        title = data.get("title", "").strip()
        if not 2 <= len(title) <= 100:
            raise ValueError("Название должно быть от 2 до 100 символов")
        kind = data.get("kind", "other")
        if kind not in KIND_LABELS:
            raise ValueError("Неизвестная категория")
        recurrence = data.get("recurrence", "once")
        if recurrence not in {"once", "weekly"}:
            raise ValueError("Неизвестный тип повтора")
        time_local = data.get("time_local", "").strip()
        parse_hhmm(time_local)
        try:
            duration = int(data.get("duration", "60"))
            reminder = int(data.get("reminder", "30"))
        except ValueError as exc:
            raise ValueError("Проверь длительность и напоминание") from exc
        if not 5 <= duration <= 720:
            raise ValueError("Длительность: от 5 минут до 12 часов")
        if reminder not in {0, 10, 30, 60, 120}:
            raise ValueError("Недопустимое время напоминания")
        now = iso()
        with self.connect() as db:
            if recurrence == "once":
                try:
                    chosen = date.fromisoformat(data.get("date_local", ""))
                except ValueError as exc:
                    raise ValueError("Выбери дату") from exc
                if chosen < today:
                    raise ValueError("Нельзя создать событие в прошлом")
                cur = db.execute(
                    """
                    INSERT INTO schedule_items(chat_id,title,kind,recurrence,date_local,weekdays_mask,start_local,duration_minutes,reminder_minutes,enabled,created_at_utc,updated_at_utc)
                    VALUES(?,?,?,'once',?,NULL,?,?,?,1,?,?)
                    """,
                    (user.chat_id, title, kind, chosen.isoformat(), time_local, duration, reminder, now, now),
                )
            else:
                mask = weekday_mask_from_text(data.get("weekdays", ""))
                cur = db.execute(
                    """
                    INSERT INTO schedule_items(chat_id,title,kind,recurrence,date_local,weekdays_mask,start_local,duration_minutes,reminder_minutes,enabled,created_at_utc,updated_at_utc)
                    VALUES(?,?,?,'weekly',NULL,?,?,?,?,1,?,?)
                    """,
                    (user.chat_id, title, kind, mask, time_local, duration, reminder, now, now),
                )
            return int(cur.lastrowid)

    def occurrence_action(self, user: WebUser, occurrence_id: int, action: str) -> None:
        with self.connect() as db:
            row = db.execute("SELECT status FROM schedule_occurrences WHERE id=? AND chat_id=?", (occurrence_id, user.chat_id)).fetchone()
            if row is None:
                raise ValueError("Событие не найдено")
            if action in {"done", "skip"}:
                status = "done" if action == "done" else "skipped"
                db.execute(
                    "UPDATE schedule_occurrences SET status=?,completed_at_utc=? WHERE id=? AND chat_id=?",
                    (status, iso(), occurrence_id, user.chat_id),
                )
            elif action in {"snooze10", "snooze30"}:
                minutes = 10 if action == "snooze10" else 30
                db.execute(
                    "UPDATE schedule_occurrences SET snoozed_until_utc=?,reminder_sent_at_utc=NULL WHERE id=? AND chat_id=? AND status='pending'",
                    (iso(utcnow() + timedelta(minutes=minutes)), occurrence_id, user.chat_id),
                )
            else:
                raise ValueError("Неизвестное действие")

    def item_action(self, user: WebUser, item_id: int, action: str) -> None:
        with self.connect() as db:
            if action == "delete":
                db.execute("DELETE FROM schedule_items WHERE id=? AND chat_id=?", (item_id, user.chat_id))
                return
            if action not in {"pause", "resume"}:
                raise ValueError("Неизвестное действие")
            enabled = 0 if action == "pause" else 1
            db.execute(
                "UPDATE schedule_items SET enabled=?,updated_at_utc=? WHERE id=? AND chat_id=?",
                (enabled, iso(), item_id, user.chat_id),
            )
            if not enabled:
                db.execute(
                    "UPDATE schedule_occurrences SET status='skipped',completed_at_utc=? WHERE schedule_item_id=? AND chat_id=? AND status='pending'",
                    (iso(), item_id, user.chat_id),
                )


class WeekWeb:
    def __init__(self, database_path: str = "/var/lib/dvizh/telegram.db"):
        self.store = WeekStore(database_path)
        self.store.ensure_schema()

    def _csrf_ok(self, handler: Any, session: Any, data: dict[str, str]) -> bool:
        return handler.same_origin() and hmac.compare_digest(data.get("csrf", ""), session.csrf_token)

    def _redirect_week(self, handler: Any, start: str = "", message: str = "") -> None:
        query: dict[str, str] = {}
        if start:
            query["start"] = start
        if message:
            query["m"] = message
        target = "/week"
        if query:
            target += "?" + urllib.parse.urlencode(query)
        handler.redirect(target)

    def page(self, session: Any, start_day: date, message: str = "") -> bytes:
        user = self.store.user()
        self.store.expire_before(user.chat_id, utcnow().astimezone(ZoneInfo(user.timezone)).date())
        self.store.ensure_range(user, start_day, 7)
        occurrences = self.store.occurrences(user, start_day, 7)
        items = self.store.items(user)
        tz = ZoneInfo(user.timezone)
        by_day: dict[str, list[sqlite3.Row]] = {}
        for row in occurrences:
            by_day.setdefault(str(row["due_date_local"]), []).append(row)

        cards: list[str] = []
        today = utcnow().astimezone(tz).date()
        for offset in range(7):
            day = start_day + timedelta(days=offset)
            rows = by_day.get(day.isoformat(), [])
            day_label = "СЕГОДНЯ" if day == today else WEEKDAY_LABELS[day.weekday()]
            row_html: list[str] = []
            for row in rows:
                start_at = parse_iso(row["start_at_utc"])
                end_at = parse_iso(row["end_at_utc"])
                start_text = start_at.astimezone(tz).strftime("%H:%M") if start_at else "--:--"
                duration = int((end_at - start_at).total_seconds() // 60) if start_at and end_at else 0
                status = str(row["status"])
                actions = ""
                if status == "pending":
                    actions = f"""
<form class="event-actions" method="post" action="/week/occurrence">
<input type="hidden" name="csrf" value="{_escape(session.csrf_token)}"><input type="hidden" name="id" value="{int(row['id'])}"><input type="hidden" name="start" value="{start_day.isoformat()}">
<button name="action" value="done" class="good">Готово</button><button name="action" value="skip">Пропустить</button><button name="action" value="snooze10">+10</button><button name="action" value="snooze30">+30</button>
</form>"""
                row_html.append(f"""
<div class="event status-{_escape(status)}"><div class="event-time">{_status_icon(status)} {start_text}</div><div class="event-main"><strong>{_escape(row['title'])}</strong><small>{KIND_LABELS.get(str(row['kind']), '• Разное')} · {_fmt_duration(duration)}</small>{actions}</div></div>""")
            if not row_html:
                row_html.append('<div class="empty">Свободно. И это тоже часть плана.</div>')
            cards.append(f"<section class=day-card><div class=day-head><b>{day_label}</b><span>{day.strftime('%d.%m')}</span></div>{''.join(row_html)}</section>")

        item_rows: list[str] = []
        for item in items:
            recurrence = "один раз " + str(item["date_local"]) if item["recurrence"] == "once" else describe_weekdays(int(item["weekdays_mask"] or 0))
            state = "активно" if item["enabled"] else "пауза"
            action = "pause" if item["enabled"] else "resume"
            action_label = "Пауза" if item["enabled"] else "Включить"
            item_rows.append(f"""
<div class="rule"><div><strong>{_escape(item['title'])}</strong><small>{KIND_LABELS.get(str(item['kind']), '• Разное')} · {recurrence} · {_escape(item['start_local'])} · {state}</small></div>
<form method="post" action="/week/item"><input type=hidden name=csrf value="{_escape(session.csrf_token)}"><input type=hidden name=id value="{int(item['id'])}"><input type=hidden name=start value="{start_day.isoformat()}"><button name=action value={action}>{action_label}</button><button name=action value=delete class=danger>Удалить</button></form></div>""")

        prev_day = start_day - timedelta(days=7)
        next_day = start_day + timedelta(days=7)
        current_today = today.isoformat()
        alert = f'<div class="alert">{_escape(message)}</div>' if message else ""
        kinds_options = "".join(f'<option value="{key}">{_escape(label)}</option>' for key, label in KIND_LABELS.items())
        document = f"""<!doctype html><html lang=ru><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name=theme-color content=#090b0f><title>Неделя — ДВИЖ</title>
<style>
:root{{--bg:#090b0f;--panel:#151922;--line:#2a303c;--muted:#9da4b4;--lime:#baff24;--text:#f5f6f8;--danger:#ff7777}}*{{box-sizing:border-box}}body{{margin:0;background:#090b0f;color:var(--text);font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;padding:18px 14px 90px}}.wrap{{max-width:1050px;margin:auto}}header{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:4px 0 20px}}h1{{font-size:clamp(34px,8vw,64px);line-height:.95;margin:6px 0}}p,small{{color:var(--muted)}}a{{color:inherit}}.back{{text-decoration:none;background:#20252f;border:1px solid var(--line);padding:12px 15px;border-radius:15px;font-weight:800}}.nav{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:15px 0}}.nav a{{text-align:center;text-decoration:none;background:#151922;border:1px solid var(--line);padding:12px;border-radius:15px}}.week-grid{{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:10px;overflow-x:auto;padding-bottom:4px}}.day-card{{min-width:190px;background:var(--panel);border:1px solid var(--line);border-radius:20px;padding:14px}}.day-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}}.day-head b{{font-size:13px;letter-spacing:.1em}}.event{{display:grid;grid-template-columns:54px 1fr;gap:8px;border-top:1px solid #252a34;padding:11px 0}}.event-time{{font-weight:850;font-size:13px}}.event-main strong{{display:block;line-height:1.2}}.event-main small{{display:block;margin-top:4px;line-height:1.25}}.status-done{{opacity:.68}}.status-skipped{{opacity:.42}}.event-actions{{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}}button,.button{{border:0;border-radius:10px;background:#2a303b;color:#fff;padding:8px 9px;font:inherit;font-weight:750;cursor:pointer}}button.good,.primary{{background:var(--lime);color:#10130c}}button.danger{{color:#ffc2c2}}.empty{{color:#757c8c;font-size:13px;padding:8px 0}}.panel{{background:var(--panel);border:1px solid var(--line);border-radius:24px;padding:18px;margin-top:18px}}.panel h2{{margin:0 0 4px}}.form-grid{{display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:10px;margin-top:14px}}label{{display:block;color:var(--muted);font-size:12px;font-weight:800;margin-bottom:5px}}input,select{{width:100%;background:#0e1117;border:1px solid var(--line);border-radius:12px;color:#fff;padding:12px;font:inherit}}.span2{{grid-column:span 2}}.form-submit{{align-self:end;height:45px}}.hint{{font-size:12px;color:var(--muted);margin-top:7px}}.rule{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 0;border-top:1px solid #262c37}}.rule strong,.rule small{{display:block}}.rule form{{display:flex;gap:6px;flex-shrink:0}}.alert{{background:#17331b;border:1px solid #2d6134;color:#caffe0;border-radius:14px;padding:12px 14px;margin:10px 0}}@media(max-width:760px){{.week-grid{{display:flex;scroll-snap-type:x mandatory}}.day-card{{width:84vw;min-width:84vw;scroll-snap-align:start}}.form-grid{{grid-template-columns:1fr 1fr}}.span2{{grid-column:span 2}}.rule{{align-items:flex-start;flex-direction:column}}header{{align-items:flex-start}}}}
</style></head><body><div class=wrap><header><div><small>ЕДИНЫЙ ГРАФИК · TELEGRAM + WEB</small><h1>Неделя</h1><p>{_escape(user.timezone)} · изменения сразу пишет в Telegram-расписание</p></div><a class=back href="/">← ДВИЖ</a></header>{alert}
<nav class=nav><a href="/week?start={prev_day.isoformat()}">← Пред.</a><a href="/week?start={current_today}">Сегодня</a><a href="/week?start={next_day.isoformat()}">След. →</a></nav><div class=week-grid>{''.join(cards)}</div>
<section class=panel><h2>Добавить блок</h2><p>Работа, отдых, встреча, дела, документы, здоровье, зал или волейбол — всё здесь и в Telegram.</p>
<form method=post action="/week/new" class=form-grid><input type=hidden name=csrf value="{_escape(session.csrf_token)}"><input type=hidden name=start value="{start_day.isoformat()}">
<div class=span2><label>Название</label><input name=title maxlength=100 placeholder="Например: Смена в кафе" required></div><div><label>Категория</label><select name=kind>{kinds_options}</select></div><div><label>Повтор</label><select name=recurrence><option value=once>Один раз</option><option value=weekly>Каждую неделю</option></select></div>
<div><label>Дата (для разового)</label><input type=date name=date_local value="{today.isoformat()}"></div><div><label>Дни (для еженедельного)</label><input name=weekdays placeholder="пн ср пт"></div><div><label>Начало</label><input type=time name=time_local required></div><div><label>Длительность</label><select name=duration><option value=30>30 мин</option><option value=60 selected>60 мин</option><option value=90>90 мин</option><option value=120>2 часа</option><option value=180>3 часа</option></select></div>
<div><label>Напомнить</label><select name=reminder><option value=0>В момент начала</option><option value=10>За 10 мин</option><option value=30 selected>За 30 мин</option><option value=60>За 1 час</option><option value=120>За 2 часа</option></select></div><button class="primary form-submit" type=submit>+ Добавить</button></form><div class=hint>Для еженедельного блока поле «Дата» игнорируется. Дни: пн вт ср чт пт сб вс.</div></section>
<section class=panel><h2>Правила расписания</h2><p>Пауза прекращает будущие напоминания по блоку. Удаление удаляет сам блок. Отметка «Пропустить» касается только конкретного дня.</p>{''.join(item_rows) if item_rows else '<div class=empty>Пока нет блоков.</div>'}</section>
</div></body></html>"""
        return document.encode("utf-8")

    def handle(self, handler: Any, session: Any, path: str) -> bool:
        if path == "/week" and handler.command in {"GET", "HEAD"}:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query)
            try:
                user = self.store.user()
                today = utcnow().astimezone(ZoneInfo(user.timezone)).date()
                start_day = date.fromisoformat(query.get("start", [today.isoformat()])[-1])
            except Exception:
                start_day = utcnow().date()
            message = query.get("m", [""])[-1][:300]
            handler.send_bytes(200, self.page(session, start_day, message), "text/html; charset=utf-8")
            return True

        if path == "/week/new" and handler.command == "POST":
            data = handler.form()
            if not self._csrf_ok(handler, session, data):
                handler.send_bytes(403, b"forbidden", "text/plain; charset=utf-8")
                return True
            start = data.get("start", "")
            try:
                user = self.store.user()
                today = utcnow().astimezone(ZoneInfo(user.timezone)).date()
                self.store.add_item(user, data, today)
                self.store.ensure_range(user, today, 14)
                self._redirect_week(handler, start, "Блок добавлен. Telegram уже видит его.")
            except Exception as exc:
                self._redirect_week(handler, start, f"Не добавил: {exc}")
            return True

        if path == "/week/occurrence" and handler.command == "POST":
            data = handler.form()
            if not self._csrf_ok(handler, session, data):
                handler.send_bytes(403, b"forbidden", "text/plain; charset=utf-8")
                return True
            start = data.get("start", "")
            try:
                user = self.store.user()
                self.store.occurrence_action(user, int(data.get("id", "0")), data.get("action", ""))
                self._redirect_week(handler, start, "Статус обновлён.")
            except Exception as exc:
                self._redirect_week(handler, start, f"Не изменил: {exc}")
            return True

        if path == "/week/item" and handler.command == "POST":
            data = handler.form()
            if not self._csrf_ok(handler, session, data):
                handler.send_bytes(403, b"forbidden", "text/plain; charset=utf-8")
                return True
            start = data.get("start", "")
            try:
                user = self.store.user()
                self.store.item_action(user, int(data.get("id", "0")), data.get("action", ""))
                self._redirect_week(handler, start, "Расписание обновлено.")
            except Exception as exc:
                self._redirect_week(handler, start, f"Не изменил: {exc}")
            return True
        return False
