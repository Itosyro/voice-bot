#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import logging
import os
import shlex
import signal
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

VERSION = '2026.08.29-web-week.1'
UTC = timezone.utc
LOG = logging.getLogger('dvizh.week.web.bridge')
USER_ID_KEYS = ('DVIZH_WEB_USER_ID', 'user_id', 'userId', 'web_user_id', 'webUserId', 'subject', 'uid')
EMAIL_KEYS = ('DVIZH_WEB_USER_EMAIL', 'email', 'user_email', 'userEmail')
KIND_LABELS = {
    'work': 'Работа', 'rest': 'Отдых', 'friend': 'Встреча', 'errand': 'Дела',
    'documents': 'Документы', 'health': 'Здоровье', 'gym': 'Зал',
    'volleyball': 'Волейбол', 'other': 'Разное',
}


class SyncError(RuntimeError):
    pass


class NotReady(SyncError):
    pass


@dataclass(frozen=True)
class Identity:
    user_id: str
    email: str

    @property
    def masked(self) -> str:
        return hashlib.sha256(self.user_id.encode('utf-8')).hexdigest()[:10]


@dataclass(frozen=True)
class Config:
    telegram_db: str = '/var/lib/dvizh/telegram.db'
    web_api: str = 'http://127.0.0.1:8000'
    bridge_env: str = '/etc/dvizh/bridge.env'
    identity_json: str = '/var/lib/dvizh/auth-identity.json'
    status_path: str = '/var/lib/dvizh/weekly-web-status.json'
    interval_seconds: int = 15
    timeout_seconds: int = 8

    @classmethod
    def from_env(cls) -> 'Config':
        return cls(
            telegram_db=os.environ.get('DVIZH_TELEGRAM_DB', cls.telegram_db),
            web_api=os.environ.get('DVIZH_WEB_API', cls.web_api).rstrip('/'),
            bridge_env=os.environ.get('DVIZH_BRIDGE_ENV', cls.bridge_env),
            identity_json=os.environ.get('DVIZH_AUTH_IDENTITY', cls.identity_json),
            status_path=os.environ.get('DVIZH_WEEK_WEB_STATUS', cls.status_path),
            interval_seconds=max(5, min(120, int(os.environ.get('DVIZH_WEEK_WEB_INTERVAL', '15')))),
            timeout_seconds=max(2, min(30, int(os.environ.get('DVIZH_WEEK_WEB_TIMEOUT', '8')))),
        )


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def iso(value: datetime | None = None) -> str:
    return (value or utcnow()).astimezone(UTC).isoformat()


def parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if not key:
            continue
        try:
            parsed = shlex.split(value, posix=True)
            values[key] = parsed[0] if parsed else ''
        except ValueError:
            values[key] = value.strip('"\'')
    return values


def recursive_value(payload: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, (str, int)) and str(value).strip():
                return str(value).strip()
        for value in payload.values():
            found = recursive_value(value, keys)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = recursive_value(value, keys)
            if found:
                return found
    return None


def load_identity(config: Config) -> Identity:
    env = parse_env(Path(config.bridge_env))
    user_id = (env.get('DVIZH_WEB_USER_ID') or '').strip()
    email = (env.get('DVIZH_WEB_USER_EMAIL') or '').strip()
    identity_path = Path(config.identity_json)
    if identity_path.is_file():
        try:
            payload = json.loads(identity_path.read_text(encoding='utf-8'))
        except Exception as exc:
            if not user_id:
                raise NotReady(f'cannot parse auth identity: {exc}') from exc
        else:
            if not user_id:
                user_id = recursive_value(payload, USER_ID_KEYS) or ''
            if not email:
                email = recursive_value(payload, EMAIL_KEYS) or ''
    if not user_id:
        raise NotReady('stable DVIZH account identity is not ready yet')
    return Identity(user_id=user_id, email=email or 'local-account@dvizh.invalid')


class WebClient:
    def __init__(self, config: Config, identity: Identity):
        self.base = config.web_api
        self.identity = identity
        self.timeout = config.timeout_seconds

    def request(self, path: str, method: str = 'GET', payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = canonical(payload).encode('utf-8') if payload is not None else None
        headers = {
            'Accept': 'application/json',
            'User-Agent': f'DVIZH-WebWeek/{VERSION}',
            'X-ExeDev-UserID': self.identity.user_id,
            'X-ExeDev-Email': self.identity.email,
        }
        if body is not None:
            headers['Content-Type'] = 'application/json'
        request = urllib.request.Request(self.base + path, method=method, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            detail = raw.decode('utf-8', errors='replace')[:500]
            if exc.code == 409:
                raise RevisionConflict(detail) from exc
            raise SyncError(f'web API {method} {path}: HTTP {exc.code}: {detail}') from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise SyncError(f'web API unavailable: {exc}') from exc
        try:
            result = json.loads(raw.decode('utf-8'))
        except Exception as exc:
            raise SyncError('web API returned invalid JSON') from exc
        if not isinstance(result, dict):
            raise SyncError('web API returned non-object JSON')
        return result

    def health(self) -> None:
        payload = self.request('/api/health')
        if payload.get('ok') is not True:
            raise SyncError(f'web health failed: {payload}')

    def get_state(self) -> tuple[int, dict[str, Any]]:
        payload = self.request('/api/state')
        state = payload.get('state')
        if not isinstance(state, dict):
            raise SyncError('web state missing')
        return int(payload.get('revision') or 0), state

    def put_state(self, revision: int, state: dict[str, Any]) -> int:
        payload = self.request('/api/state', 'PUT', {'baseRevision': revision, 'state': state})
        if payload.get('ok') is not True:
            raise SyncError(f'web state write refused: {payload}')
        return int(payload.get('revision') or (revision + 1))


class RevisionConflict(SyncError):
    pass


def connect_db(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=5000')
    return db


def authorized_user(db: sqlite3.Connection) -> sqlite3.Row:
    rows = db.execute('SELECT * FROM users WHERE authorized=1 ORDER BY chat_id').fetchall()
    if len(rows) != 1:
        raise NotReady(f'expected one paired Telegram chat, found {len(rows)}')
    return rows[0]


def table_exists(db: sqlite3.Connection, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def import_web_actions(db: sqlite3.Connection, state: dict[str, Any], chat_id: int) -> dict[str, int]:
    weekly = state.get('weeklySchedule')
    if not isinstance(weekly, dict):
        return {'weekDoneImported': 0, 'weekSkippedImported': 0}
    occurrences = weekly.get('occurrences')
    if not isinstance(occurrences, list):
        return {'weekDoneImported': 0, 'weekSkippedImported': 0}
    done = skipped = 0
    prefix = f'tg-schedule-occ-{chat_id}-'
    for item in occurrences:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get('id') or '')
        status = str(item.get('status') or '')
        if not item_id.startswith(prefix) or status not in {'done', 'skipped'}:
            continue
        try:
            occurrence_id = int(item_id[len(prefix):])
        except ValueError:
            continue
        row = db.execute(
            'SELECT status FROM schedule_occurrences WHERE id=? AND chat_id=?',
            (occurrence_id, chat_id),
        ).fetchone()
        if not row or row['status'] != 'pending':
            continue
        db.execute(
            'UPDATE schedule_occurrences SET status=?,completed_at_utc=? WHERE id=? AND chat_id=? AND status=\'pending\'',
            (status, iso(), occurrence_id, chat_id),
        )
        if table_exists(db, 'event_log'):
            db.execute(
                'INSERT INTO event_log(chat_id,event_type,payload_json,created_at_utc) VALUES(?,?,?,?)',
                (chat_id, f'web_schedule_{status}', canonical({'schedule_occurrence_id': occurrence_id}), iso()),
            )
        if status == 'done':
            done += 1
        else:
            skipped += 1
    return {'weekDoneImported': done, 'weekSkippedImported': skipped}


def project_schedule(db: sqlite3.Connection, user: sqlite3.Row) -> dict[str, Any]:
    if not table_exists(db, 'schedule_items') or not table_exists(db, 'schedule_occurrences'):
        raise NotReady('weekly schedule tables are not installed yet')
    chat_id = int(user['chat_id'])
    timezone_name = str(user['timezone'] or 'Europe/Moscow')
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        timezone_name = 'Europe/Moscow'
        tz = ZoneInfo(timezone_name)
    today = utcnow().astimezone(tz).date()
    end_day = today + timedelta(days=6)

    item_rows = db.execute(
        'SELECT * FROM schedule_items WHERE chat_id=? ORDER BY start_local,id', (chat_id,)
    ).fetchall()
    items = []
    for row in item_rows:
        items.append({
            'id': f'tg-schedule-item-{chat_id}-{int(row["id"])}',
            'title': str(row['title']),
            'kind': str(row['kind']),
            'kindLabel': KIND_LABELS.get(str(row['kind']), 'Разное'),
            'recurrence': str(row['recurrence']),
            'dateLocal': row['date_local'],
            'weekdaysMask': int(row['weekdays_mask']) if row['weekdays_mask'] is not None else None,
            'startLocal': str(row['start_local']),
            'durationMinutes': int(row['duration_minutes']),
            'reminderMinutes': int(row['reminder_minutes']),
            'enabled': bool(row['enabled']),
            'source': 'telegram',
        })

    rows = db.execute(
        '''
        SELECT o.*, i.start_local, i.duration_minutes AS item_duration_minutes
        FROM schedule_occurrences o
        JOIN schedule_items i ON i.id=o.schedule_item_id
        WHERE o.chat_id=? AND o.due_date_local BETWEEN ? AND ?
        ORDER BY o.due_date_local,o.start_at_utc,o.id
        ''',
        (chat_id, today.isoformat(), end_day.isoformat()),
    ).fetchall()
    occurrences = []
    for row in rows:
        occurrence_id = int(row['id'])
        occurrences.append({
            'id': f'tg-schedule-occ-{chat_id}-{occurrence_id}',
            'scheduleItemId': f'tg-schedule-item-{chat_id}-{int(row["schedule_item_id"])}',
            'title': str(row['title']),
            'kind': str(row['kind']),
            'kindLabel': KIND_LABELS.get(str(row['kind']), 'Разное'),
            'dueDate': str(row['due_date_local']),
            'startLocal': str(row['start_local']),
            'startAt': str(row['start_at_utc']),
            'endAt': str(row['end_at_utc']),
            'durationMinutes': int(row['item_duration_minutes']),
            'reminderMinutes': int(row['reminder_minutes']),
            'status': str(row['status']),
            'completedAt': row['completed_at_utc'],
            'source': 'telegram',
        })
    return {
        'version': 1,
        'timezone': timezone_name,
        'rangeStart': today.isoformat(),
        'rangeEnd': end_day.isoformat(),
        'items': items,
        'occurrences': occurrences,
    }


def normalized_week(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {key: value.get(key) for key in ('version', 'timezone', 'rangeStart', 'rangeEnd', 'items', 'occurrences')}


def merge_schedule(state: dict[str, Any], projection: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    current_normalized = normalized_week(state.get('weeklySchedule'))
    changed = canonical(current_normalized) != canonical(projection)
    if not changed:
        return state, False
    merged = json.loads(canonical(state))
    payload = dict(projection)
    payload['syncedAt'] = iso()
    merged['weeklySchedule'] = payload
    return merged, True


def write_status(path: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {'version': VERSION, 'at': iso(), **payload}
    temp = target.with_suffix(target.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    os.chmod(temp, 0o640)
    os.replace(temp, target)


def sync_once(config: Config) -> dict[str, Any]:
    identity = load_identity(config)
    client = WebClient(config, identity)
    client.health()
    for attempt in range(1, 5):
        revision, state = client.get_state()
        with connect_db(config.telegram_db) as db:
            user = authorized_user(db)
            imported = import_web_actions(db, state, int(user['chat_id']))
            db.commit()
            projection = project_schedule(db, user)
        merged, changed = merge_schedule(state, projection)
        if not changed:
            return {
                'ok': True, 'changed': False, 'webRevision': revision, 'webUser': identity.masked,
                'items': len(projection['items']), 'occurrences': len(projection['occurrences']), **imported,
            }
        try:
            new_revision = client.put_state(revision, merged)
        except RevisionConflict:
            time.sleep(0.2 * attempt)
            continue
        return {
            'ok': True, 'changed': True, 'webRevision': new_revision, 'webUser': identity.masked,
            'items': len(projection['items']), 'occurrences': len(projection['occurrences']), **imported,
        }
    raise SyncError('web state kept changing during weekly schedule sync')


def main() -> int:
    logging.basicConfig(level=os.environ.get('DVIZH_LOG_LEVEL', 'INFO'), format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    config = Config.from_env()
    stop = False

    def handle_stop(_sig: int, _frame: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    LOG.info('weekly web bridge %s started interval=%ss', VERSION, config.interval_seconds)
    while not stop:
        try:
            result = sync_once(config)
            write_status(config.status_path, result)
            LOG.info('sync ok changed=%s items=%s occurrences=%s', result['changed'], result['items'], result['occurrences'])
        except NotReady as exc:
            write_status(config.status_path, {'ok': False, 'waiting': True, 'error': str(exc)})
            LOG.warning('waiting: %s', exc)
        except Exception as exc:
            write_status(config.status_path, {'ok': False, 'waiting': False, 'error': str(exc)})
            LOG.exception('weekly web sync failed')
        for _ in range(config.interval_seconds):
            if stop:
                break
            time.sleep(1)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
