#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

MARKER_HTML = '<!-- DVIZH_MINIMAL_UI_V1 -->'
MARKER_JS = 'const DVIZH_MINIMAL_UI_V1 = true;'
MARKER_CSS = '/* DVIZH_MINIMAL_UI_V1 */'
CACHE_NAME = 'dvizh-minimal-ui-v1'

SETTINGS_PANEL = r'''        <!-- DVIZH_MINIMAL_UI_V1 -->
        <article class="panel minimal-ui-settings" id="minimalUiSettings">
          <div class="minimal-ui-settings-head">
            <div>
              <p class="eyebrow">ИНТЕРФЕЙС</p>
              <h3>Спокойный режим</h3>
              <p>Меньше крупных заголовков, декоративных карточек и пунктов в нижнем меню. Все функции остаются на месте.</p>
            </div>
            <button type="button" class="ghost small" id="minimalUiToggle" aria-pressed="true">Включён</button>
          </div>
          <div class="minimal-ui-shortcuts" aria-label="Дополнительные разделы">
            <span>Дополнительные разделы</span>
            <div>
              <button type="button" class="ghost" data-minimal-nav="proof">↗ Факты</button>
              <button type="button" class="ghost" data-minimal-nav="training">🏋 Тренировки</button>
              <button type="button" class="ghost" data-minimal-nav="social">📱 Соцсети</button>
            </div>
          </div>
        </article>
'''

JS_MINIMAL = r'''

const DVIZH_MINIMAL_UI_V1 = true;
(() => {
  const STORAGE_KEY = 'dvizh:minimal-ui:v1';
  const root = document.documentElement;
  let observerQueued = false;

  function readEnabled() {
    try { return localStorage.getItem(STORAGE_KEY) !== 'off'; }
    catch (_) { return true; }
  }

  function writeEnabled(enabled) {
    try { localStorage.setItem(STORAGE_KEY, enabled ? 'on' : 'off'); }
    catch (_) {}
  }

  function updateToggle() {
    const button = document.getElementById('minimalUiToggle');
    if (!button) return;
    const enabled = root.classList.contains('dvizh-minimal-ui');
    const label = enabled ? 'Включён' : 'Выключен';
    if (button.textContent !== label) button.textContent = label;
    button.setAttribute('aria-pressed', String(enabled));
    button.title = enabled ? 'Показать полный интерфейс' : 'Включить спокойный интерфейс';
  }

  function markSecondary() {
    const selectors = [
      '#view-training .training-load-card',
      '#view-training .training-lower-grid',
      '#view-training .training-history-panel',
      '#view-training .jump-editor-grid',
      '#view-training .jump-program-card',
      '#view-training .jump-coach-grid',
      '#view-social .social-metrics-card',
      '#view-social .social-window-card',
      '#view-social .social-lower-layout'
    ];
    selectors.forEach(selector => {
      document.querySelectorAll(selector).forEach(node => {
        node.setAttribute('data-minimal-secondary', 'true');
      });
    });
  }

  function ensureDetailsButton(viewSelector, headingSelector) {
    const view = document.querySelector(viewSelector);
    if (!view) return;
    const heading = view.querySelector(headingSelector);
    if (!heading || heading.querySelector('.minimal-details-toggle')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ghost small minimal-details-toggle';
    button.setAttribute('data-minimal-details-toggle', 'true');
    button.textContent = view.dataset.minimalDetails === 'open' ? 'Скрыть детали' : 'Детали';
    heading.appendChild(button);
  }

  function ensureStructure() {
    markSecondary();
    ensureDetailsButton('#view-training', '.training-heading');
    ensureDetailsButton('#view-social', '.social-heading');
    updateToggle();
  }

  function apply(enabled) {
    root.classList.toggle('dvizh-minimal-ui', Boolean(enabled));
    writeEnabled(Boolean(enabled));
    ensureStructure();
  }

  function toggleDetails(button) {
    const view = button.closest('.view');
    if (!view) return;
    const open = view.dataset.minimalDetails !== 'open';
    view.dataset.minimalDetails = open ? 'open' : 'closed';
    button.textContent = open ? 'Скрыть детали' : 'Детали';
  }

  function handleClick(event) {
    const toggle = event.target.closest('#minimalUiToggle');
    if (toggle) {
      event.preventDefault();
      apply(!root.classList.contains('dvizh-minimal-ui'));
      return;
    }

    const details = event.target.closest('[data-minimal-details-toggle]');
    if (details) {
      event.preventDefault();
      toggleDetails(details);
      return;
    }

    const shortcut = event.target.closest('[data-minimal-nav]');
    if (shortcut) {
      event.preventDefault();
      const view = shortcut.getAttribute('data-minimal-nav');
      if (view && typeof navigate === 'function') navigate(view);
    }
  }

  function queueEnsure() {
    if (observerQueued) return;
    observerQueued = true;
    requestAnimationFrame(() => {
      observerQueued = false;
      ensureStructure();
    });
  }

  function boot() {
    root.classList.toggle('dvizh-minimal-ui', readEnabled());
    ensureStructure();
    document.addEventListener('click', handleClick);
    if (document.body && typeof MutationObserver !== 'undefined') {
      new MutationObserver(queueEnsure).observe(document.body, {childList:true, subtree:true});
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
'''

CSS_MINIMAL = r'''

/* DVIZH_MINIMAL_UI_V1 */
.minimal-ui-settings { display:grid; gap:14px; }
.minimal-ui-settings-head { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.minimal-ui-settings-head h3 { margin:4px 0 0; }
.minimal-ui-settings-head p:last-child { margin:8px 0 0; max-width:62ch; color:var(--muted); font-size:11px; line-height:1.5; }
.minimal-ui-shortcuts { display:none; gap:8px; padding-top:12px; border-top:1px solid var(--line); }
.minimal-ui-shortcuts>span { color:var(--faint); font-size:9px; font-weight:850; text-transform:uppercase; letter-spacing:.08em; }
.minimal-ui-shortcuts>div { display:flex; flex-wrap:wrap; gap:8px; }
.minimal-details-toggle { display:none; flex:0 0 auto; }

html.dvizh-minimal-ui {
  --panel: #111318;
  --panel-2: #15181e;
  --line: rgba(255,255,255,.085);
  --muted: #a1a7b1;
  --faint: #727985;
}
html.dvizh-minimal-ui body {
  background:#090a0c !important;
  background-image:none !important;
}
html.dvizh-minimal-ui body::before,
html.dvizh-minimal-ui body::after,
html.dvizh-minimal-ui .ambient,
html.dvizh-minimal-ui .ambient-glow,
html.dvizh-minimal-ui .orb,
html.dvizh-minimal-ui .noise,
html.dvizh-minimal-ui .grain { opacity:0 !important; box-shadow:none !important; }
html.dvizh-minimal-ui .view { gap:12px !important; }
html.dvizh-minimal-ui .section-heading.page-heading { margin-bottom:12px !important; gap:12px; align-items:center; }
html.dvizh-minimal-ui .section-heading.page-heading .eyebrow { display:none; }
html.dvizh-minimal-ui .section-heading.page-heading h2 {
  margin:0 !important;
  max-width:24ch;
  font-size:clamp(28px,5vw,42px) !important;
  line-height:1.04 !important;
  letter-spacing:-.045em !important;
}
html.dvizh-minimal-ui #view-home h1,
html.dvizh-minimal-ui #view-home .hero-title,
html.dvizh-minimal-ui .hero h1 {
  max-width:22ch !important;
  font-size:clamp(32px,6.3vw,48px) !important;
  line-height:1.02 !important;
  letter-spacing:-.05em !important;
}
html.dvizh-minimal-ui .soft-label {
  border:0 !important;
  background:transparent !important;
  padding:0 !important;
  box-shadow:none !important;
  color:var(--faint) !important;
}
html.dvizh-minimal-ui .panel {
  background:var(--panel) !important;
  background-image:none !important;
  border:1px solid var(--line) !important;
  border-radius:15px !important;
  box-shadow:none !important;
}
html.dvizh-minimal-ui .panel::before,
html.dvizh-minimal-ui .panel::after { box-shadow:none !important; filter:none !important; }
html.dvizh-minimal-ui button,
html.dvizh-minimal-ui .primary,
html.dvizh-minimal-ui .ghost {
  box-shadow:none !important;
  text-shadow:none !important;
  border-radius:10px !important;
}
html.dvizh-minimal-ui input,
html.dvizh-minimal-ui select,
html.dvizh-minimal-ui textarea {
  box-shadow:none !important;
  border-radius:10px !important;
}
html.dvizh-minimal-ui .eyebrow { letter-spacing:.055em !important; }
html.dvizh-minimal-ui .minimal-ui-shortcuts { display:grid; }
html.dvizh-minimal-ui .minimal-details-toggle { display:inline-flex; }
html.dvizh-minimal-ui .view:not([data-minimal-details="open"]) [data-minimal-secondary="true"] { display:none !important; }
html.dvizh-minimal-ui #view-week .week-overview-head>p { display:none !important; }
html.dvizh-minimal-ui #view-week .week-overview-head { margin-bottom:12px !important; }
html.dvizh-minimal-ui #view-week .week-overview-head h3 { font-size:18px !important; }
html.dvizh-minimal-ui #view-social .social-heading h2,
html.dvizh-minimal-ui #view-training .training-heading h2 { max-width:22ch; }
html.dvizh-minimal-ui #view-social .social-next-card,
html.dvizh-minimal-ui #view-training .training-readiness-card,
html.dvizh-minimal-ui #view-training .jump-today-card { border-color:rgba(200,255,53,.22) !important; }
html.dvizh-minimal-ui .social-column { background:transparent !important; border-color:rgba(255,255,255,.06) !important; }
html.dvizh-minimal-ui .social-content-card,
html.dvizh-minimal-ui .week-event,
html.dvizh-minimal-ui .jump-exercise,
html.dvizh-minimal-ui .jump-today-row { box-shadow:none !important; }

@media (max-width:760px) {
  html.dvizh-minimal-ui main,
  html.dvizh-minimal-ui .main-content,
  html.dvizh-minimal-ui .app-main { padding-left:14px !important; padding-right:14px !important; }
  html.dvizh-minimal-ui .section-heading.page-heading { display:flex !important; margin-bottom:10px !important; }
  html.dvizh-minimal-ui .section-heading.page-heading h2 {
    font-size:clamp(26px,7.6vw,34px) !important;
    line-height:1.04 !important;
  }
  html.dvizh-minimal-ui #view-home h1,
  html.dvizh-minimal-ui #view-home .hero-title,
  html.dvizh-minimal-ui .hero h1 {
    font-size:clamp(30px,9vw,40px) !important;
    line-height:1.01 !important;
  }
  html.dvizh-minimal-ui .panel { padding:14px !important; border-radius:14px !important; }
  html.dvizh-minimal-ui .primary,
  html.dvizh-minimal-ui .ghost { min-height:42px; padding:10px 12px !important; }
  html.dvizh-minimal-ui .mobile-nav {
    grid-template-columns:repeat(5,minmax(0,1fr)) !important;
    gap:2px !important;
    overflow:visible !important;
    padding:6px 8px !important;
    border-radius:17px !important;
    box-shadow:none !important;
  }
  html.dvizh-minimal-ui .mobile-nav [data-nav="proof"],
  html.dvizh-minimal-ui .mobile-nav [data-nav="training"],
  html.dvizh-minimal-ui .mobile-nav [data-nav="social"] { display:none !important; }
  html.dvizh-minimal-ui .mobile-nav button { min-width:0 !important; padding:6px 3px !important; }
  html.dvizh-minimal-ui .mobile-nav button span { font-size:17px !important; }
  html.dvizh-minimal-ui .mobile-nav button small { font-size:8px !important; letter-spacing:0 !important; }
  html.dvizh-minimal-ui .social-hero-layout,
  html.dvizh-minimal-ui .social-capture-layout,
  html.dvizh-minimal-ui .training-layout,
  html.dvizh-minimal-ui .jump-hero-grid { gap:10px !important; }
  html.dvizh-minimal-ui .social-pipeline { grid-template-columns:repeat(6,minmax(210px,84vw)) !important; gap:8px !important; }
  html.dvizh-minimal-ui .week-schedule-grid { grid-template-columns:repeat(7,minmax(210px,84vw)) !important; gap:8px !important; }
  html.dvizh-minimal-ui .jump-goal-head strong { min-width:60px !important; width:60px !important; height:60px !important; font-size:22px !important; }
  html.dvizh-minimal-ui .jump-metrics { grid-template-columns:repeat(2,minmax(0,1fr)) !important; }
  .minimal-ui-settings-head { display:grid; }
  .minimal-ui-settings-head #minimalUiToggle { justify-self:start; }
  .minimal-ui-shortcuts>div { display:grid; grid-template-columns:1fr; }
}

@media (prefers-reduced-motion: reduce) {
  html.dvizh-minimal-ui *,
  html.dvizh-minimal-ui *::before,
  html.dvizh-minimal-ui *::after { animation-duration:.01ms !important; animation-iteration-count:1 !important; transition-duration:.01ms !important; scroll-behavior:auto !important; }
}
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_index(text: str) -> str:
    if MARKER_HTML in text:
        return text
    anchor = '      <section class="view" id="view-settings" data-view="settings">'
    return replace_once(text, anchor, anchor + '\n' + SETTINGS_PANEL.rstrip(), 'minimal settings panel')


def patch_app(text: str) -> str:
    if MARKER_JS in text:
        return text
    return text.rstrip() + JS_MINIMAL + '\n'


def patch_css(text: str) -> str:
    if MARKER_CSS in text:
        return text
    return text.rstrip() + CSS_MINIMAL + '\n'


def patch_sw(text: str) -> str:
    if CACHE_NAME in text:
        return text
    changed, count = re.subn(r"(const\s+CACHE\s*=\s*['\"])([^'\"]+)(['\"])", rf"\1{CACHE_NAME}\3", text, count=1)
    if count != 1:
        raise RuntimeError('service worker cache anchor not found')
    return changed


def patch_root(root: Path, check_only: bool = False) -> list[str]:
    files = {name: root / name for name in ('index.html', 'app.js', 'styles.css', 'sw.js')}
    for path in files.values():
        if not path.is_file():
            raise SystemExit(f'missing {path}')
    original = {name: path.read_text(encoding='utf-8') for name, path in files.items()}
    patched = {
        'index.html': patch_index(original['index.html']),
        'app.js': patch_app(original['app.js']),
        'styles.css': patch_css(original['styles.css']),
        'sw.js': patch_sw(original['sw.js']),
    }
    required = {
        'index.html': MARKER_HTML,
        'app.js': MARKER_JS,
        'styles.css': MARKER_CSS,
        'sw.js': CACHE_NAME,
    }
    for name, marker in required.items():
        if marker not in patched[name]:
            raise SystemExit(f'{name}: marker missing after patch')
    if check_only:
        print('minimal UI patch check=ok')
        return []
    changed: list[str] = []
    for name, content in patched.items():
        if content != original[name]:
            files[name].write_text(content, encoding='utf-8')
            changed.append(name)
    print('minimal UI patch=ok changed=' + (','.join(changed) if changed else 'none'))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    patch_root(Path(args.root), check_only=args.check)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
