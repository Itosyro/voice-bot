#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

MARKER_HTML = '<!-- DVIZH_WEEK_VIEW_V1 -->'
MARKER_JS = 'const DVIZH_WEEK_WEB_V1 = true;'
MARKER_CSS = '/* DVIZH_WEEK_WEB_V1 */'

WEEK_SECTION = r'''      <!-- DVIZH_WEEK_VIEW_V1 -->
      <section class="view" id="view-week" data-view="week">
        <div class="section-heading page-heading">
          <div>
            <p class="eyebrow">НЕДЕЛЯ · БЛИЖАЙШИЕ 7 ДНЕЙ</p>
            <h2>Где жизнь, где дела, где восстановление</h2>
          </div>
          <span class="soft-label" id="weekSyncStatus">синхронизация с Telegram</span>
        </div>

        <article class="panel week-overview-panel">
          <div class="week-overview-head">
            <div>
              <p class="eyebrow">ЕДИНОЕ РАСПИСАНИЕ</p>
              <h3>Telegram и веб показывают одни и те же блоки</h3>
            </div>
            <p>Создавай события в Telegram. На сайте можно видеть неделю и отмечать отдельный блок выполненным или пропущенным.</p>
          </div>
          <div class="week-schedule-grid" id="weekScheduleGrid"></div>
        </article>
      </section>
'''

JS_WEEK_FUNCTIONS = r'''
  const DVIZH_WEEK_WEB_V1 = true;
  const WEEK_KIND = {
    work: ['💼', 'Работа'],
    rest: ['🛋', 'Отдых'],
    friend: ['🤝', 'Встреча'],
    errand: ['📍', 'Дела'],
    documents: ['📄', 'Документы'],
    health: ['🩺', 'Здоровье'],
    gym: ['🏋️', 'Зал'],
    volleyball: ['🏐', 'Волейбол'],
    other: ['•', 'Разное']
  };

  function getWeeklySchedule() {
    const value = state.weeklySchedule;
    if (!value || typeof value !== 'object') {
      return { timezone: 'Europe/Moscow', occurrences: [], syncedAt: null };
    }
    return {
      timezone: value.timezone || 'Europe/Moscow',
      occurrences: Array.isArray(value.occurrences) ? value.occurrences : [],
      syncedAt: value.syncedAt || value.updatedAt || null
    };
  }

  function weekLocalKey(offset = 0) {
    const date = new Date();
    date.setHours(12, 0, 0, 0);
    date.setDate(date.getDate() + offset);
    return localDateKey(date);
  }

  function renderWeek() {
    const root = $('#weekScheduleGrid');
    if (!root) return;
    const weekly = getWeeklySchedule();
    const occurrences = weekly.occurrences;
    const byDay = new Map();
    occurrences.forEach(item => {
      if (!item || !item.dueDate) return;
      if (!byDay.has(item.dueDate)) byDay.set(item.dueDate, []);
      byDay.get(item.dueDate).push(item);
    });

    const days = Array.from({ length: 7 }, (_, offset) => {
      const key = weekLocalKey(offset);
      const date = parseLocalDate(key);
      const items = (byDay.get(key) || []).sort((a, b) => String(a.startLocal || '').localeCompare(String(b.startLocal || '')));
      const weekday = new Intl.DateTimeFormat('ru-RU', { weekday: 'short' }).format(date).replace('.', '').toUpperCase();
      const dayMonth = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' }).format(date);
      const cards = items.length ? items.map(item => {
        const [icon, kind] = WEEK_KIND[item.kind] || WEEK_KIND.other;
        const status = item.status || 'pending';
        const statusLabel = status === 'done' ? 'готово' : status === 'skipped' ? 'пропущено' : '';
        const actions = status === 'pending' ? `
          <div class="week-event-actions">
            <button data-action="week-event-done" data-schedule-occurrence-id="${escapeHtml(item.id)}">✓ Готово</button>
            <button data-action="week-event-skip" data-schedule-occurrence-id="${escapeHtml(item.id)}">— Пропустить</button>
          </div>` : `<span class="week-event-status">${status === 'done' ? '✓' : '—'} ${statusLabel}</span>`;
        return `
          <article class="week-event is-${escapeHtml(status)}" data-kind="${escapeHtml(item.kind || 'other')}">
            <div class="week-event-time">${escapeHtml(item.startLocal || '--:--')}</div>
            <div class="week-event-body">
              <div class="week-event-kind">${icon} ${escapeHtml(kind)}</div>
              <b>${escapeHtml(item.title || 'Событие')}</b>
              <small>${Number(item.durationMinutes || 0)} мин${item.reminderMinutes ? ` · напоминание −${Number(item.reminderMinutes)} мин` : ''}</small>
              ${actions}
            </div>
          </article>`;
      }).join('') : `<div class="week-empty">Свободно. Не нужно заполнять день ради заполнения.</div>`;
      return `
        <section class="week-day ${offset === 0 ? 'is-today' : ''}">
          <header><span>${weekday}</span><b>${dayMonth}</b></header>
          <div class="week-day-events">${cards}</div>
        </section>`;
    }).join('');

    root.innerHTML = days;
    const status = $('#weekSyncStatus');
    if (status) {
      if (!weekly.syncedAt) status.textContent = 'ждём первую синхронизацию';
      else {
        const when = new Date(weekly.syncedAt);
        status.textContent = Number.isNaN(when.getTime())
          ? 'синхронизировано'
          : `обновлено ${new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(when)}`;
      }
    }
  }

  function setWeekOccurrenceStatus(id, status) {
    if (!['done', 'skipped'].includes(status)) return;
    if (!state.weeklySchedule || !Array.isArray(state.weeklySchedule.occurrences)) return;
    const occurrence = state.weeklySchedule.occurrences.find(item => String(item.id) === String(id));
    if (!occurrence || occurrence.status !== 'pending') return;
    occurrence.status = status;
    occurrence.webUpdatedAt = nowIso();
    state.weeklySchedule.webUpdatedAt = nowIso();
    saveState();
    renderWeek();
    showToast(status === 'done' ? 'Блок отмечен выполненным.' : 'Пропущен только этот экземпляр.');
  }
'''

CSS_WEEK = r'''

/* DVIZH_WEEK_WEB_V1 */
.week-overview-panel { padding: clamp(16px, 2.4vw, 26px); }
.week-overview-head { display: flex; justify-content: space-between; gap: 28px; align-items: flex-end; margin-bottom: 18px; }
.week-overview-head h3 { margin: 5px 0 0; font-size: clamp(18px, 2vw, 24px); }
.week-overview-head > p { margin: 0; color: var(--muted); max-width: 560px; font-size: 12px; line-height: 1.5; }
.week-schedule-grid { display: grid; grid-template-columns: repeat(7, minmax(150px, 1fr)); gap: 10px; overflow-x: auto; padding-bottom: 5px; scrollbar-width: thin; }
.week-day { min-width: 150px; border: 1px solid var(--line); background: rgba(255,255,255,.018); border-radius: 16px; padding: 12px; }
.week-day.is-today { border-color: rgba(200,255,53,.42); box-shadow: inset 0 0 0 1px rgba(200,255,53,.08); }
.week-day > header { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
.week-day > header span { color: var(--lime); font-size: 10px; font-weight: 900; letter-spacing: .1em; }
.week-day > header b { color: var(--muted); font-size: 11px; }
.week-day-events { display: grid; gap: 9px; }
.week-event { display: grid; grid-template-columns: auto 1fr; gap: 9px; border-radius: 13px; background: var(--panel-2); border: 1px solid var(--line); padding: 10px; }
.week-event.is-done { opacity: .66; }
.week-event.is-skipped { opacity: .45; }
.week-event-time { color: var(--lime); font-size: 11px; font-weight: 900; padding-top: 2px; }
.week-event-body { min-width: 0; display: grid; gap: 4px; }
.week-event-kind { color: var(--muted); font-size: 9px; font-weight: 850; letter-spacing: .05em; text-transform: uppercase; }
.week-event-body b { font-size: 12px; line-height: 1.25; overflow-wrap: anywhere; }
.week-event-body small { color: var(--faint); font-size: 9px; line-height: 1.35; }
.week-event-actions { display: grid; grid-template-columns: 1fr; gap: 5px; margin-top: 5px; }
.week-event-actions button { border: 1px solid var(--line); background: rgba(255,255,255,.035); color: var(--muted); border-radius: 8px; padding: 6px 7px; font-size: 9px; font-weight: 800; cursor: pointer; text-align: left; }
.week-event-actions button:first-child { color: var(--lime); }
.week-event-status { color: var(--muted); font-size: 9px; font-weight: 800; margin-top: 4px; }
.week-empty { color: var(--faint); font-size: 10px; line-height: 1.45; border: 1px dashed var(--line); border-radius: 11px; padding: 10px; }
@media (max-width: 1100px) {
  .week-schedule-grid { grid-template-columns: repeat(7, minmax(175px, 210px)); }
  .week-overview-head { display: grid; }
}
@media (max-width: 760px) {
  .week-overview-panel { padding: 13px; }
  .week-schedule-grid { margin-right: -13px; padding-right: 13px; grid-template-columns: repeat(7, minmax(190px, 78vw)); scroll-snap-type: x proximity; }
  .week-day { scroll-snap-align: start; }
  .mobile-nav { grid-template-columns: repeat(6, 1fr) !important; }
  .mobile-nav button span { font-size: 18px; }
  .mobile-nav button small { font-size: 8px; }
}
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)


def patch_index(text: str) -> str:
    if MARKER_HTML in text:
        return text
    text = replace_once(
        text,
        '        <button class="nav-item" data-nav="settings"><span>···</span><b>Настройки</b></button>',
        '        <button class="nav-item" data-nav="week"><span>▦</span><b>Неделя</b></button>\n'
        '        <button class="nav-item" data-nav="settings"><span>···</span><b>Настройки</b></button>',
        'sidebar week nav',
    )
    text = replace_once(
        text,
        '      <section class="view" id="view-settings" data-view="settings">',
        WEEK_SECTION + '\n      <section class="view" id="view-settings" data-view="settings">',
        'week section',
    )
    text = replace_once(
        text,
        '      <button data-nav="proof"><span>↗</span><small>Факты</small></button>\n      <button data-nav="settings"><span>···</span><small>Ещё</small></button>',
        '      <button data-nav="proof"><span>↗</span><small>Факты</small></button>\n'
        '      <button data-nav="week"><span>▦</span><small>Неделя</small></button>\n'
        '      <button data-nav="settings"><span>···</span><small>Ещё</small></button>',
        'mobile week nav',
    )
    return text


def patch_app(text: str) -> str:
    if MARKER_JS in text:
        return text
    text = replace_once(
        text,
        "      proof: 'Факты сильнее ощущения «я ничего не делаю».',\n      settings:",
        "      proof: 'Факты сильнее ощущения «я ничего не делаю».',\n      week: 'Неделя без каши: жизнь, дела и восстановление в одном месте.',\n      settings:",
        'direct view copy',
    )
    text = replace_once(
        text,
        "      proof: 'Посмотри на реальные шаги, которые уже были.',\n      settings:",
        "      proof: 'Посмотри на реальные шаги, которые уже были.',\n      week: 'Посмотри на ближайшие семь дней без попытки забить каждый час.',\n      settings:",
        'calm view copy',
    )
    text = replace_once(
        text,
        "    if (!['home', 'tasks', 'focus', 'proof', 'settings'].includes(view)) return;",
        "    if (!['home', 'tasks', 'focus', 'proof', 'week', 'settings'].includes(view)) return;",
        'navigate views',
    )
    text = replace_once(
        text,
        "    if (view === 'proof') renderProof();",
        "    if (view === 'proof') renderProof();\n    if (view === 'week') renderWeek();",
        'navigate render week',
    )
    text = replace_once(
        text,
        '  function renderSettings() {',
        JS_WEEK_FUNCTIONS + '\n  function renderSettings() {',
        'week render functions',
    )
    text = replace_once(
        text,
        '    renderProof();\n    renderSettings();',
        '    renderProof();\n    renderWeek();\n    renderSettings();',
        'render all week',
    )
    text = replace_once(
        text,
        "        'install-app': installApp,\n        'reset-app': resetApp",
        "        'install-app': installApp,\n"
        "        'week-event-done': () => setWeekOccurrenceStatus(actionButton.dataset.scheduleOccurrenceId, 'done'),\n"
        "        'week-event-skip': () => setWeekOccurrenceStatus(actionButton.dataset.scheduleOccurrenceId, 'skipped'),\n"
        "        'reset-app': resetApp",
        'week actions',
    )
    return text


def patch_css(text: str) -> str:
    if MARKER_CSS in text:
        return text
    return text.rstrip() + CSS_WEEK + '\n'


def patch_sw(text: str) -> str:
    if 'dvizh-week-web-v1' in text:
        return text
    patched, count = re.subn(r"const CACHE\s*=\s*['\"][^'\"]+['\"];", "const CACHE = 'dvizh-week-web-v1';", text, count=1)
    if count != 1:
        raise RuntimeError(f'service worker: expected cache anchor, found {count}')
    return patched


def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + '.week-tmp')
    tmp.write_text(content, encoding='utf-8')
    os.chmod(tmp, path.stat().st_mode & 0o777)
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='/opt/dvizh')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = Path(args.root)
    files = {
        'index.html': patch_index,
        'app.js': patch_app,
        'styles.css': patch_css,
        'sw.js': patch_sw,
    }
    results = {}
    for name, patcher in files.items():
        path = root / name
        if not path.is_file():
            raise SystemExit(f'missing {path}')
        original = path.read_text(encoding='utf-8')
        patched = patcher(original)
        results[name] = (path, original, patched)
    assert MARKER_HTML in results['index.html'][2]
    assert MARKER_JS in results['app.js'][2]
    assert MARKER_CSS in results['styles.css'][2]
    assert 'dvizh-week-web-v1' in results['sw.js'][2]
    if args.check:
        print('web patch check=ok')
        return 0
    for _, (path, original, patched) in results.items():
        if patched != original:
            atomic_write(path, patched)
    print('web patch=ok')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
