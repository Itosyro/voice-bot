#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

MARKER = "# DVIZH_WEEK_EDITOR_COMMAND_PRESERVE_V1"
OLD = '''def merge_schedule(state: dict[str, Any], projection: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    current_normalized = normalized_week(state.get('weeklySchedule'))
    changed = canonical(current_normalized) != canonical(projection)
    if not changed:
        return state, False
    merged = json.loads(canonical(state))
    payload = dict(projection)
    payload['syncedAt'] = iso()
    merged['weeklySchedule'] = payload
    return merged, True
'''
NEW = '''def merge_schedule(state: dict[str, Any], projection: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    # DVIZH_WEEK_EDITOR_COMMAND_PRESERVE_V1
    current_week = state.get('weeklySchedule') if isinstance(state.get('weeklySchedule'), dict) else {}
    current_normalized = normalized_week(current_week)
    changed = canonical(current_normalized) != canonical(projection)
    if not changed:
        return state, False
    merged = json.loads(canonical(state))
    payload = dict(projection)
    payload['syncedAt'] = iso()
    # Web editor commands are an outbox. Never discard them while publishing a
    # fresh Telegram projection; the editor bridge removes them only after the
    # SQLite mutation has been committed or safely rejected.
    commands = current_week.get('webCommands')
    if isinstance(commands, list) and commands:
        payload['webCommands'] = commands
    if current_week.get('webUpdatedAt'):
        payload['webUpdatedAt'] = current_week.get('webUpdatedAt')
    merged['weeklySchedule'] = payload
    return merged, True
'''


def patch_text(text: str) -> str:
    if MARKER in text:
        return text
    count = text.count(OLD)
    if count != 1:
        raise RuntimeError(f'weekly bridge merge_schedule anchor count={count}')
    return text.replace(OLD, NEW, 1)


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--file',required=True); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    path=Path(args.file)
    if not path.is_file(): raise SystemExit(f'missing {path}')
    current=path.read_text(encoding='utf-8'); patched=patch_text(current)
    if args.check:
        print('week bridge editor preservation check=ok'); return 0
    path.write_text(patched,encoding='utf-8'); print('week bridge editor preservation=ok'); return 0

if __name__ == '__main__':
    raise SystemExit(main())
