#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

MARKER_JS = "const DVIZH_AI_APPROVAL_UI_V1 = true;"
MARKER_CSS = "/* DVIZH_AI_APPROVAL_UI_V1 */"
CACHE_NAME = "dvizh-ai-approval-v1"

JS = r'''

  const DVIZH_AI_APPROVAL_UI_V1 = true;

  function aiApprovalEsc(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  }

  function aiApprovalActionLabel(action) {
    return ({
      task_create: 'Новая задача',
      task_complete: 'Завершить задачу',
      schedule_move: 'Перенести событие',
      day_plan: 'План дня'
    })[action] || 'Изменение';
  }

  function aiApprovalDetail(proposal) {
    const p = proposal && typeof proposal.payload === 'object' ? proposal.payload : {};
    if (proposal.action === 'task_create') return p.title ? `Добавить «${p.title}»` : proposal.summary;
    if (proposal.action === 'task_complete') {
      const tasks = Array.isArray(state.tasks) ? state.tasks : [];
      const task = tasks.find(item => item && String(item.id) === String(p.task_id));
      return task ? `Отметить «${task.title}» выполненной` : proposal.summary;
    }
    if (proposal.action === 'schedule_move') return p.start_local ? `Новое время: ${p.start_local}` : proposal.summary;
    if (proposal.action === 'day_plan') {
      const count = Array.isArray(p.blocks) ? p.blocks.length : 0;
      return count ? `${count} блоков на день` : proposal.summary;
    }
    return proposal.summary || '';
  }

  function aiApprovalEnsureRoot() {
    let root = document.getElementById('aiProposalPanel');
    if (root) return root;
    const home = document.getElementById('view-home');
    if (!home) return null;
    root = document.createElement('section');
    root.id = 'aiProposalPanel';
    root.className = 'panel ai-proposal-panel';
    root.hidden = true;
    root.setAttribute('aria-live', 'polite');
    const hero = home.querySelector('.hero, .home-hero, .section-heading');
    if (hero && hero.parentElement === home) hero.insertAdjacentElement('afterend', root);
    else home.prepend(root);
    return root;
  }

  function aiApprovalPendingCommand(proposalId) {
    const commands = Array.isArray(state.aiProposalCommands) ? state.aiProposalCommands : [];
    return commands.some(command => command && String(command.proposalId) === String(proposalId));
  }

  function renderAiProposals() {
    if (typeof state === 'undefined' || !state) return;
    const root = aiApprovalEnsureRoot();
    if (!root) return;
    const proposals = Array.isArray(state.aiProposals) ? state.aiProposals.filter(p => p && p.status === 'pending') : [];
    if (!proposals.length) {
      root.hidden = true;
      root.innerHTML = '';
      return;
    }
    root.hidden = false;
    const cards = proposals.slice(0, 4).map(proposal => {
      const pending = aiApprovalPendingCommand(proposal.id);
      const label = aiApprovalActionLabel(proposal.action);
      const summary = proposal.summary || aiApprovalDetail(proposal);
      const detail = aiApprovalDetail(proposal);
      return `<article class="ai-proposal-card" data-ai-proposal-id="${aiApprovalEsc(proposal.id)}">
        <div class="ai-proposal-card-head">
          <div><span class="ai-proposal-kicker">${aiApprovalEsc(label)}</span><h3>${aiApprovalEsc(summary)}</h3></div>
          <span class="ai-proposal-source">Hermes</span>
        </div>
        ${detail && detail !== summary ? `<p>${aiApprovalEsc(detail)}</p>` : ''}
        <div class="ai-proposal-actions">
          <button type="button" class="primary" data-ai-proposal-decision="approve" data-ai-proposal-id="${aiApprovalEsc(proposal.id)}" ${pending ? 'disabled' : ''}>${pending ? 'Отправлено…' : 'Принять'}</button>
          <button type="button" class="ghost" data-ai-proposal-decision="reject" data-ai-proposal-id="${aiApprovalEsc(proposal.id)}" ${pending ? 'disabled' : ''}>Отклонить</button>
        </div>
      </article>`;
    }).join('');
    root.innerHTML = `<div class="ai-proposal-heading">
      <div><p class="eyebrow">ИИ ПРЕДЛАГАЕТ</p><h2>Подтверди изменение</h2></div>
      <span>${proposals.length}</span>
    </div>${cards}`;
  }

  function aiApprovalSend(proposalId, decision) {
    if (typeof state === 'undefined' || !state || typeof saveState !== 'function') return;
    const token = String(state.aiProposalUiToken || '');
    if (token.length < 24 || token === '[REDACTED]') {
      if (typeof showToast === 'function') showToast('Подтверждение ещё синхронизируется. Попробуй через пару секунд.');
      return;
    }
    if (!['approve','reject'].includes(decision)) return;
    const commands = Array.isArray(state.aiProposalCommands) ? state.aiProposalCommands.filter(item => item && typeof item === 'object') : [];
    if (commands.some(command => String(command.proposalId) === String(proposalId))) return;
    const command = {
      id: `ai-ui-${Date.now()}-${Math.random().toString(36).slice(2,9)}`,
      proposalId: String(proposalId),
      decision,
      token,
      createdAt: typeof nowIso === 'function' ? nowIso() : new Date().toISOString()
    };
    state.aiProposalCommands = [...commands.slice(-19), command];
    saveState();
    renderAiProposals();
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-ai-proposal-decision]');
    if (!button) return;
    event.preventDefault();
    aiApprovalSend(button.getAttribute('data-ai-proposal-id'), button.getAttribute('data-ai-proposal-decision'));
  });

  window.setInterval(renderAiProposals, 1400);
  window.addEventListener('focus', renderAiProposals);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', renderAiProposals, {once:true});
  else queueMicrotask(renderAiProposals);
'''

CSS = r'''

/* DVIZH_AI_APPROVAL_UI_V1 */
.ai-proposal-panel { display:grid; gap:10px; border-color:rgba(200,255,53,.26)!important; }
.ai-proposal-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.ai-proposal-heading h2 { margin:3px 0 0; font-size:clamp(19px,4vw,26px); letter-spacing:-.035em; }
.ai-proposal-heading>span { min-width:30px; height:30px; padding:0 9px; display:grid; place-items:center; border-radius:999px; background:rgba(200,255,53,.12); color:var(--accent,#c8ff35); font-weight:850; }
.ai-proposal-card { display:grid; gap:10px; padding:13px 0 0; border-top:1px solid var(--line,rgba(255,255,255,.09)); }
.ai-proposal-card:first-of-type { border-top:0; padding-top:2px; }
.ai-proposal-card-head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.ai-proposal-card-head h3 { margin:3px 0 0; font-size:16px; line-height:1.25; letter-spacing:-.02em; }
.ai-proposal-kicker { color:var(--muted,#a1a7b1); font-size:9px; font-weight:850; letter-spacing:.07em; text-transform:uppercase; }
.ai-proposal-source { color:var(--accent,#c8ff35); font-size:10px; font-weight:800; white-space:nowrap; }
.ai-proposal-card>p { margin:0; color:var(--muted,#a1a7b1); font-size:11px; line-height:1.5; }
.ai-proposal-actions { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.ai-proposal-actions button { min-height:42px; }
.ai-proposal-actions button:disabled { opacity:.55; cursor:wait; }
html.dvizh-minimal-ui .ai-proposal-panel { background:#111318!important; box-shadow:none!important; }
html.dvizh-minimal-ui .ai-proposal-actions .primary { background:var(--accent,#c8ff35)!important; color:#111!important; }
@media (max-width:520px) {
  .ai-proposal-panel { padding:14px!important; }
  .ai-proposal-actions { grid-template-columns:1fr 1fr; }
}
'''


def insert_js(text: str) -> str:
    if MARKER_JS in text:
        return text
    anchor = "  function renderSettings() {"
    count = text.count(anchor)
    if count != 1:
        raise RuntimeError(f"renderSettings anchor count={count}")
    return text.replace(anchor, JS + "\n" + anchor, 1)


def patch_css(text: str) -> str:
    return text if MARKER_CSS in text else text.rstrip() + CSS + "\n"


def patch_sw(text: str) -> str:
    if CACHE_NAME in text:
        return text
    changed, count = re.subn(r"(const\s+CACHE\s*=\s*['\"])([^'\"]+)(['\"])", rf"\1{CACHE_NAME}\3", text, count=1)
    if count != 1:
        raise RuntimeError("service worker cache anchor not found")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    files = {name: root / name for name in ("app.js", "styles.css", "sw.js")}
    for path in files.values():
        if not path.is_file():
            raise SystemExit(f"missing {path}")
    original = {name: path.read_text(encoding="utf-8") for name, path in files.items()}
    patched = {
        "app.js": insert_js(original["app.js"]),
        "styles.css": patch_css(original["styles.css"]),
        "sw.js": patch_sw(original["sw.js"]),
    }
    if args.check:
        if MARKER_JS not in patched["app.js"] or MARKER_CSS not in patched["styles.css"] or CACHE_NAME not in patched["sw.js"]:
            raise SystemExit("AI approval UI marker check failed")
        print("ai approval ui patch check=ok")
        return 0
    for name, value in patched.items():
        files[name].write_text(value, encoding="utf-8")
    print("ai approval ui patch=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
