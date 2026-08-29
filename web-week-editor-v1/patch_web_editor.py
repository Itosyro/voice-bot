#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

MARKER_HTML = '<!-- DVIZH_WEEK_EDITOR_V1 -->'
MARKER_JS = 'const DVIZH_WEEK_EDITOR_V1 = true;'
MARKER_CSS = '/* DVIZH_WEEK_EDITOR_V1 */'

EDITOR_HTML = r'''        <!-- DVIZH_WEEK_EDITOR_V1 -->
        <div class="week-editor-bar">
          <button type="button" class="primary small" id="weekEditorNew">＋ Событие</button>
          <span id="weekEditorQueueStatus">Изменения с сайта уходят в Telegram и напоминания автоматически.</span>
        </div>

        <section class="week-editor-panel" id="weekEditorPanel" hidden>
          <form id="weekEditorForm" autocomplete="off">
            <input type="hidden" id="weekEditorItemId" value="">
            <div class="week-editor-head">
              <div>
                <p class="eyebrow">РЕДАКТОР РАСПИСАНИЯ</p>
                <h3 id="weekEditorTitle">Новое событие</h3>
              </div>
              <button type="button" class="ghost small" id="weekEditorCancel">Закрыть</button>
            </div>
            <div class="week-editor-grid">
              <label class="week-field week-field-wide"><span>Название</span><input id="weekEditorName" maxlength="120" required placeholder="Например: Верх тела"></label>
              <label class="week-field"><span>Тип</span><select id="weekEditorKind">
                <option value="work">💼 Работа</option><option value="rest">🛋 Отдых</option><option value="friend">🤝 Встреча</option>
                <option value="errand">📍 Дела</option><option value="documents">📄 Документы</option><option value="health">🩺 Здоровье</option>
                <option value="gym">🏋️ Зал</option><option value="volleyball">🏐 Волейбол</option><option value="other">• Разное</option>
              </select></label>
              <label class="week-field"><span>Повтор</span><select id="weekEditorRecurrence"><option value="once">Один раз</option><option value="weekly">Каждую неделю</option></select></label>
              <label class="week-field" id="weekEditorDateField"><span>Дата</span><input id="weekEditorDate" type="date"></label>
              <div class="week-field week-field-wide" id="weekEditorWeekdaysField" hidden><span>Дни недели</span><div class="week-days-picker">
                <label><input type="checkbox" data-weekday="0">ПН</label><label><input type="checkbox" data-weekday="1">ВТ</label>
                <label><input type="checkbox" data-weekday="2">СР</label><label><input type="checkbox" data-weekday="3">ЧТ</label>
                <label><input type="checkbox" data-weekday="4">ПТ</label><label><input type="checkbox" data-weekday="5">СБ</label>
                <label><input type="checkbox" data-weekday="6">ВС</label>
              </div></div>
              <label class="week-field"><span>Начало</span><input id="weekEditorTime" type="time" required value="18:00"></label>
              <label class="week-field"><span>Длительность, мин</span><input id="weekEditorDuration" type="number" min="5" max="720" step="5" required value="60"></label>
              <label class="week-field"><span>Напомнить</span><select id="weekEditorReminder">
                <option value="0">в момент начала</option><option value="10">за 10 минут</option><option value="30" selected>за 30 минут</option>
                <option value="60">за 1 час</option><option value="120">за 2 часа</option>
              </select></label>
            </div>
            <div class="week-editor-actions"><button type="submit" class="primary">Сохранить</button><span>Обычно Telegram подхватывает изменение за 5–20 секунд.</span></div>
          </form>
        </section>
'''

RULES_HTML = r'''
        <section class="week-rules-panel">
          <div class="week-rules-head"><div><p class="eyebrow">ПРАВИЛА РАСПИСАНИЯ</p><h3>Повторы и разовые события</h3></div><small>Здесь можно редактировать, выключать или удалять правило целиком.</small></div>
          <div class="week-rules-list" id="weekScheduleRules"></div>
        </section>
'''

JS_EDITOR = r'''
  const DVIZH_WEEK_EDITOR_V1 = true;
  const WEEK_EDITOR_DAY_LABELS = ['ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС'];

  function weekStateObject() {
    if (!state.weeklySchedule || typeof state.weeklySchedule !== 'object') {
      state.weeklySchedule = { version: 1, timezone: 'Europe/Moscow', items: [], occurrences: [], webCommands: [] };
    }
    if (!Array.isArray(state.weeklySchedule.items)) state.weeklySchedule.items = [];
    if (!Array.isArray(state.weeklySchedule.occurrences)) state.weeklySchedule.occurrences = [];
    if (!Array.isArray(state.weeklySchedule.webCommands)) state.weeklySchedule.webCommands = [];
    return state.weeklySchedule;
  }

  function weekCommandId() {
    return `web-week-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  }

  function weekEnqueue(action, payload = {}) {
    const weekly = weekStateObject();
    const command = { id: weekCommandId(), action, ...payload, createdAt: nowIso() };
    weekly.webCommands = [...weekly.webCommands.slice(-19), command];
    weekly.webUpdatedAt = nowIso();
    saveState();
    return command;
  }

  function weekDateInCurrentRange(key) {
    const start = weekLocalKey(0);
    const end = weekLocalKey(6);
    return key >= start && key <= end;
  }

  function weekItemApplies(item, key) {
    const d = parseLocalDate(key);
    if (!item || item.enabled === false) return false;
    if (item.recurrence === 'once') return item.dateLocal === key;
    const mask = Number(item.weekdaysMask || 0);
    return Boolean(mask & (1 << d.getDay() === 0 ? 6 : d.getDay() - 1));
  }

  function weekWeekdayIndexFromKey(key) {
    const d = parseLocalDate(key);
    const js = d.getDay();
    return js === 0 ? 6 : js - 1;
  }

  function weekRuleApplies(item, key) {
    if (!item || item.enabled === false) return false;
    if (item.recurrence === 'once') return item.dateLocal === key;
    const mask = Number(item.weekdaysMask || 0);
    return Boolean(mask & (1 << weekWeekdayIndexFromKey(key)));
  }

  function weekRebuildOptimisticOccurrences(item) {
    const weekly = weekStateObject();
    const keep = weekly.occurrences.filter(occ => String(occ.scheduleItemId) !== String(item.id) || occ.status !== 'pending');
    const blocked = new Set(keep.filter(occ => String(occ.scheduleItemId) === String(item.id) && occ.status !== 'pending').map(occ => occ.dueDate));
    const added = [];
    for (let offset = 0; offset < 7; offset += 1) {
      const dueDate = weekLocalKey(offset);
      if (!weekRuleApplies(item, dueDate) || blocked.has(dueDate)) continue;
      added.push({
        id: `web-pending-occ-${item.id}-${dueDate}`,
        scheduleItemId: item.id,
        title: item.title,
        kind: item.kind,
        kindLabel: (WEEK_KIND[item.kind] || WEEK_KIND.other)[1],
        dueDate,
        startLocal: item.startLocal,
        durationMinutes: Number(item.durationMinutes || 0),
        reminderMinutes: Number(item.reminderMinutes || 0),
        status: 'pending',
        source: 'web-pending'
      });
    }
    weekly.occurrences = keep.concat(added);
  }

  function weekOptimisticCreate(command) {
    const weekly = weekStateObject();
    const item = {
      id: `web-temp-${command.id}`,
      title: command.title,
      kind: command.kind,
      kindLabel: (WEEK_KIND[command.kind] || WEEK_KIND.other)[1],
      recurrence: command.recurrence,
      dateLocal: command.dateLocal || null,
      weekdaysMask: command.weekdaysMask || null,
      startLocal: command.startLocal,
      durationMinutes: Number(command.durationMinutes),
      reminderMinutes: Number(command.reminderMinutes),
      enabled: true,
      source: 'web-pending'
    };
    weekly.items.push(item);
    weekRebuildOptimisticOccurrences(item);
  }

  function weekOptimisticUpdate(command) {
    const weekly = weekStateObject();
    const item = weekly.items.find(row => String(row.id) === String(command.itemId));
    if (!item) return;
    Object.assign(item, {
      title: command.title, kind: command.kind, recurrence: command.recurrence,
      dateLocal: command.dateLocal || null, weekdaysMask: command.weekdaysMask || null,
      startLocal: command.startLocal, durationMinutes: Number(command.durationMinutes),
      reminderMinutes: Number(command.reminderMinutes)
    });
    weekRebuildOptimisticOccurrences(item);
  }

  function weekOptimisticEnabled(itemId, enabled) {
    const weekly = weekStateObject();
    const item = weekly.items.find(row => String(row.id) === String(itemId));
    if (!item) return;
    item.enabled = Boolean(enabled);
    weekRebuildOptimisticOccurrences(item);
  }

  function weekOptimisticDelete(itemId) {
    const weekly = weekStateObject();
    weekly.items = weekly.items.filter(item => String(item.id) !== String(itemId));
    weekly.occurrences = weekly.occurrences.filter(item => String(item.scheduleItemId) !== String(itemId));
  }

  function weekEditorToggleRecurrence() {
    const recurrence = $('#weekEditorRecurrence')?.value || 'once';
    const once = $('#weekEditorDateField');
    const weekly = $('#weekEditorWeekdaysField');
    if (once) once.hidden = recurrence !== 'once';
    if (weekly) weekly.hidden = recurrence !== 'weekly';
  }

  function weekEditorResetDays(mask = 0) {
    document.querySelectorAll('#weekEditorWeekdaysField [data-weekday]').forEach(input => {
      input.checked = Boolean(Number(mask || 0) & (1 << Number(input.dataset.weekday)));
    });
  }

  function weekEditorOpen(itemId = '') {
    const panel = $('#weekEditorPanel');
    const form = $('#weekEditorForm');
    if (!panel || !form) return;
    form.reset();
    $('#weekEditorItemId').value = '';
    $('#weekEditorTime').value = '18:00';
    $('#weekEditorDuration').value = '60';
    $('#weekEditorReminder').value = '30';
    $('#weekEditorDate').value = weekLocalKey(0);
    weekEditorResetDays(0);
    let item = null;
    if (itemId) item = weekStateObject().items.find(row => String(row.id) === String(itemId));
    if (item) {
      $('#weekEditorItemId').value = item.id;
      $('#weekEditorName').value = item.title || '';
      $('#weekEditorKind').value = item.kind || 'other';
      $('#weekEditorRecurrence').value = item.recurrence || 'once';
      $('#weekEditorDate').value = item.dateLocal || weekLocalKey(0);
      $('#weekEditorTime').value = item.startLocal || '18:00';
      $('#weekEditorDuration').value = String(item.durationMinutes || 60);
      $('#weekEditorReminder').value = String(item.reminderMinutes ?? 30);
      weekEditorResetDays(item.weekdaysMask || 0);
      $('#weekEditorTitle').textContent = 'Редактировать событие';
    } else {
      $('#weekEditorTitle').textContent = 'Новое событие';
    }
    weekEditorToggleRecurrence();
    panel.hidden = false;
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    setTimeout(() => $('#weekEditorName')?.focus(), 150);
  }

  function weekEditorClose() {
    const panel = $('#weekEditorPanel');
    if (panel) panel.hidden = true;
  }

  function weekEditorPayload() {
    const recurrence = $('#weekEditorRecurrence').value;
    const title = $('#weekEditorName').value.trim();
    if (!title) throw new Error('Напиши название события.');
    const duration = Number($('#weekEditorDuration').value);
    if (!Number.isFinite(duration) || duration < 5 || duration > 720) throw new Error('Длительность: от 5 до 720 минут.');
    let weekdaysMask = null;
    let dateLocal = null;
    if (recurrence === 'once') {
      dateLocal = $('#weekEditorDate').value;
      if (!dateLocal) throw new Error('Выбери дату.');
    } else {
      weekdaysMask = 0;
      document.querySelectorAll('#weekEditorWeekdaysField [data-weekday]:checked').forEach(input => {
        weekdaysMask |= 1 << Number(input.dataset.weekday);
      });
      if (!weekdaysMask) throw new Error('Выбери хотя бы один день недели.');
    }
    return {
      title,
      kind: $('#weekEditorKind').value,
      recurrence,
      dateLocal,
      weekdaysMask,
      startLocal: $('#weekEditorTime').value,
      durationMinutes: duration,
      reminderMinutes: Number($('#weekEditorReminder').value)
    };
  }

  function weekEditorSubmit() {
    try {
      const payload = weekEditorPayload();
      const itemId = $('#weekEditorItemId').value;
      if (itemId) {
        if (String(itemId).startsWith('web-temp-')) {
          showToast('Подожди несколько секунд: это событие ещё сохраняется на сервере.');
          return;
        }
        const command = weekEnqueue('update', { itemId, ...payload });
        weekOptimisticUpdate(command);
        showToast('Изменение отправлено в Telegram.');
      } else {
        const command = weekEnqueue('create', payload);
        weekOptimisticCreate(command);
        showToast('Событие создано. Telegram подхватит его автоматически.');
      }
      saveState();
      weekEditorClose();
      renderWeek();
    } catch (error) {
      showToast(error?.message || 'Проверь поля события.');
    }
  }

  function weekDaysDescription(mask) {
    const value = Number(mask || 0);
    if (value === 127) return 'каждый день';
    return WEEK_EDITOR_DAY_LABELS.filter((_, index) => value & (1 << index)).join(' · ') || 'дни не выбраны';
  }

  function renderWeekEditorManager() {
    const root = $('#weekScheduleRules');
    if (!root) return;
    const weekly = weekStateObject();
    const queue = $('#weekEditorQueueStatus');
    if (queue) {
      const count = weekly.webCommands.length;
      queue.textContent = count ? `${count} изм. отправлено · обычно до 20 секунд` : 'Изменения с сайта уходят в Telegram и напоминания автоматически.';
    }
    const items = weekly.items.slice().sort((a, b) => String(a.startLocal || '').localeCompare(String(b.startLocal || '')));
    if (!items.length) {
      root.innerHTML = '<div class="week-empty">Расписание пока пустое. Добавь первое событие здесь или в Telegram.</div>';
      return;
    }
    root.innerHTML = items.map(item => {
      const [icon, kind] = WEEK_KIND[item.kind] || WEEK_KIND.other;
      const recurrence = item.recurrence === 'once'
        ? `один раз · ${escapeHtml(item.dateLocal || '—')}`
        : `еженедельно · ${escapeHtml(weekDaysDescription(item.weekdaysMask))}`;
      const pending = String(item.id).startsWith('web-temp-');
      const disabled = item.enabled === false;
      return `<article class="week-rule ${disabled ? 'is-disabled' : ''} ${pending ? 'is-pending' : ''}">
        <div class="week-rule-main"><span class="week-rule-icon">${icon}</span><div><b>${escapeHtml(item.title || 'Событие')}</b><small>${escapeHtml(kind)} · ${recurrence}<br>${escapeHtml(item.startLocal || '--:--')} · ${Number(item.durationMinutes || 0)} мин · ${Number(item.reminderMinutes || 0) ? `напомнить −${Number(item.reminderMinutes)} мин` : 'в момент начала'}</small></div></div>
        <div class="week-rule-actions">
          ${pending ? '<span class="week-rule-saving">сохраняется…</span>' : `
          <button type="button" data-week-rule-edit="${escapeHtml(item.id)}">Изменить</button>
          <button type="button" data-week-rule-toggle="${escapeHtml(item.id)}" data-enabled="${disabled ? '1' : '0'}">${disabled ? 'Включить' : 'Пауза'}</button>
          <button type="button" class="danger" data-week-rule-delete="${escapeHtml(item.id)}">Удалить</button>`}
        </div>
      </article>`;
    }).join('');
  }
'''

JS_WRAP = r'''
  const renderWeekWithoutEditor = renderWeek;
  renderWeek = function renderWeekWithEditor() {
    renderWeekWithoutEditor();
    renderWeekEditorManager();
  };

  document.addEventListener('click', event => {
    const target = event.target.closest('button');
    if (!target) return;
    if (target.id === 'weekEditorNew') {
      event.preventDefault(); weekEditorOpen(); return;
    }
    if (target.id === 'weekEditorCancel') {
      event.preventDefault(); weekEditorClose(); return;
    }
    if (target.dataset.weekRuleEdit) {
      event.preventDefault(); weekEditorOpen(target.dataset.weekRuleEdit); return;
    }
    if (target.dataset.weekRuleToggle) {
      event.preventDefault();
      const itemId = target.dataset.weekRuleToggle;
      const enabled = target.dataset.enabled === '1';
      weekEnqueue('set_enabled', { itemId, enabled });
      weekOptimisticEnabled(itemId, enabled);
      saveState(); renderWeek();
      showToast(enabled ? 'Событие снова активно.' : 'Пауза: новые напоминания выключены.');
      return;
    }
    if (target.dataset.weekRuleDelete) {
      event.preventDefault();
      const itemId = target.dataset.weekRuleDelete;
      const item = weekStateObject().items.find(row => String(row.id) === String(itemId));
      if (!confirm(`Удалить «${item?.title || 'событие'}» целиком?`)) return;
      weekEnqueue('delete', { itemId });
      weekOptimisticDelete(itemId);
      saveState(); renderWeek();
      showToast('Событие удаляется из общего расписания.');
    }
  });

  document.addEventListener('change', event => {
    if (event.target?.id === 'weekEditorRecurrence') weekEditorToggleRecurrence();
  });

  document.addEventListener('submit', event => {
    if (event.target?.id !== 'weekEditorForm') return;
    event.preventDefault();
    weekEditorSubmit();
  });
'''

CSS_EDITOR = r'''

/* DVIZH_WEEK_EDITOR_V1 */
.week-editor-bar { display:flex; align-items:center; gap:12px; margin:0 0 14px; }
.week-editor-bar > span { color:var(--faint); font-size:10px; line-height:1.4; }
.week-editor-panel { border:1px solid rgba(200,255,53,.26); background:rgba(200,255,53,.025); border-radius:16px; padding:16px; margin-bottom:16px; }
.week-editor-panel[hidden] { display:none !important; }
.week-editor-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:14px; }
.week-editor-head h3 { margin:4px 0 0; font-size:18px; }
.week-editor-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
.week-field { display:grid; gap:6px; }
.week-field-wide { grid-column:span 2; }
.week-field > span { color:var(--muted); font-size:9px; font-weight:850; letter-spacing:.06em; text-transform:uppercase; }
.week-field input,.week-field select { width:100%; min-width:0; border:1px solid var(--line); background:var(--panel-2); color:var(--text); border-radius:10px; padding:10px 11px; font:inherit; font-size:12px; outline:none; }
.week-field input:focus,.week-field select:focus { border-color:rgba(200,255,53,.55); }
.week-days-picker { display:grid; grid-template-columns:repeat(7,1fr); gap:5px; }
.week-days-picker label { display:flex; align-items:center; justify-content:center; gap:4px; border:1px solid var(--line); background:var(--panel-2); border-radius:9px; padding:9px 4px; color:var(--muted); font-size:9px; font-weight:850; cursor:pointer; }
.week-days-picker input { width:auto; accent-color:var(--lime); }
.week-editor-actions { display:flex; align-items:center; gap:12px; margin-top:14px; }
.week-editor-actions > span { color:var(--faint); font-size:9px; }
.week-editor-panel button.primary,.week-editor-bar button.primary { border:0; border-radius:10px; background:var(--lime); color:#111; font-weight:900; padding:10px 14px; cursor:pointer; }
.week-editor-panel button.ghost { border:1px solid var(--line); border-radius:9px; background:transparent; color:var(--muted); font-weight:800; padding:8px 10px; cursor:pointer; }
.week-editor-panel button.small,.week-editor-bar button.small { padding:8px 11px; font-size:10px; }
.week-rules-panel { margin-top:16px; padding-top:16px; border-top:1px solid var(--line); }
.week-rules-head { display:flex; justify-content:space-between; align-items:end; gap:20px; margin-bottom:10px; }
.week-rules-head h3 { margin:4px 0 0; font-size:16px; }
.week-rules-head small { color:var(--faint); font-size:9px; max-width:360px; line-height:1.4; }
.week-rules-list { display:grid; gap:8px; }
.week-rule { display:flex; justify-content:space-between; align-items:center; gap:12px; border:1px solid var(--line); background:var(--panel-2); border-radius:12px; padding:10px 11px; }
.week-rule.is-disabled { opacity:.55; }
.week-rule.is-pending { border-style:dashed; }
.week-rule-main { display:flex; min-width:0; align-items:flex-start; gap:9px; }
.week-rule-icon { font-size:18px; line-height:1; }
.week-rule-main > div { min-width:0; display:grid; gap:3px; }
.week-rule-main b { font-size:11px; overflow-wrap:anywhere; }
.week-rule-main small { color:var(--faint); font-size:9px; line-height:1.45; }
.week-rule-actions { display:flex; align-items:center; gap:5px; flex-wrap:wrap; justify-content:flex-end; }
.week-rule-actions button { border:1px solid var(--line); background:rgba(255,255,255,.03); color:var(--muted); border-radius:8px; padding:7px 8px; font-size:9px; font-weight:800; cursor:pointer; }
.week-rule-actions button.danger { color:#ff8f8f; }
.week-rule-saving { color:var(--lime); font-size:9px; font-weight:800; }
@media(max-width:900px){.week-editor-grid{grid-template-columns:repeat(2,minmax(0,1fr));}.week-field-wide{grid-column:span 2}.week-rule{align-items:flex-start;display:grid}.week-rule-actions{justify-content:flex-start}}
@media(max-width:600px){.week-editor-bar,.week-editor-actions,.week-rules-head{align-items:flex-start;display:grid}.week-editor-grid{grid-template-columns:1fr}.week-field-wide{grid-column:span 1}.week-days-picker{grid-template-columns:repeat(4,1fr)}.week-editor-panel{padding:12px}}
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_index(text: str) -> str:
    if MARKER_HTML in text:
        return text
    if '<!-- DVIZH_WEEK_VIEW_V1 -->' not in text:
        raise RuntimeError('week v1 HTML marker is missing')
    text = replace_once(text, '        <div class="week-schedule-grid" id="weekScheduleGrid"></div>', EDITOR_HTML + '\n        <div class="week-schedule-grid" id="weekScheduleGrid"></div>' + RULES_HTML, 'editor HTML')
    return text


def patch_app(text: str) -> str:
    if MARKER_JS in text:
        return text
    if 'const DVIZH_WEEK_WEB_V1 = true;' not in text:
        raise RuntimeError('week v1 JS marker is missing')
    text = replace_once(text, '  const DVIZH_WEEK_WEB_V1 = true;', '  const DVIZH_WEEK_WEB_V1 = true;\n' + JS_EDITOR, 'editor helpers')
    text = replace_once(text, '  function setWeekOccurrenceStatus(id, status) {', JS_WRAP + '\n  function setWeekOccurrenceStatus(id, status) {', 'editor render wrapper')
    return text


def patch_css(text: str) -> str:
    if MARKER_CSS in text:
        return text
    if '/* DVIZH_WEEK_WEB_V1 */' not in text:
        raise RuntimeError('week v1 CSS marker is missing')
    return text.rstrip() + CSS_EDITOR + '\n'


def patch_sw(text: str) -> str:
    if 'dvizh-week-editor-v1' in text:
        return text
    updated, count = re.subn(r"const CACHE = ['\"][^'\"]+['\"]", "const CACHE = 'dvizh-week-editor-v1'", text, count=1)
    if count != 1:
        raise RuntimeError('service worker cache anchor not found')
    return updated


def patch_root(root: Path, check_only: bool = False) -> None:
    paths = {name: root / name for name in ('index.html','app.js','styles.css','sw.js')}
    for path in paths.values():
        if not path.is_file():
            raise RuntimeError(f'missing {path}')
    current = {name: path.read_text(encoding='utf-8') for name, path in paths.items()}
    patched = {
        'index.html': patch_index(current['index.html']),
        'app.js': patch_app(current['app.js']),
        'styles.css': patch_css(current['styles.css']),
        'sw.js': patch_sw(current['sw.js']),
    }
    if check_only:
        print('web editor patch check=ok')
        return
    for name, value in patched.items():
        paths[name].write_text(value, encoding='utf-8')
    print('web editor patch=ok')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    patch_root(Path(args.root), args.check)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
