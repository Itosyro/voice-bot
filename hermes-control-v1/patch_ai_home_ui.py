#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

MARKER_JS = "const DVIZH_AI_HOME_V1 = true;"
MARKER_CSS = "/* DVIZH_AI_HOME_V1 */"
CACHE_NAME = "dvizh-ai-home-v1"

JS = r'''

  const DVIZH_AI_HOME_V1 = true;
  let aiHomeRenderSig = '';
  let aiHomeRecognition = null;
  let aiHomeListening = false;

  function aiHomeData() {
    if (!Array.isArray(state.aiHomeRequests)) state.aiHomeRequests = [];
    if (!Array.isArray(state.aiHomeMessages)) state.aiHomeMessages = [];
    if (!state.aiHomeStatus || typeof state.aiHomeStatus !== 'object') state.aiHomeStatus = {state:'idle'};
    return state;
  }

  function aiHomeEnsureRoot() {
    const home = document.getElementById('view-home');
    if (!home) return null;
    home.classList.add('ai-home-mode');
    let root = document.getElementById('aiHomeShell');
    if (root) return root;
    root = document.createElement('section');
    root.id = 'aiHomeShell';
    root.className = 'ai-home-shell';
    root.innerHTML = `
      <div class="ai-home-topbar">
        <span class="ai-home-brand">ДВИЖ</span>
        <button type="button" class="ai-home-manual" data-ai-home-manual>Ручной режим</button>
      </div>
      <div class="ai-home-center">
        <button type="button" class="ai-home-orb" id="aiHomeOrb" aria-label="Голосовой ввод">
          <span></span><span></span><span></span>
        </button>
        <p class="ai-home-state" id="aiHomeState">Скажи, что сегодня происходит.</p>
        <div class="ai-home-answer" id="aiHomeAnswer" hidden></div>
      </div>
      <form class="ai-home-composer" id="aiHomeComposer">
        <button type="button" class="ai-home-mic" id="aiHomeMic" aria-label="Голосовой ввод">●</button>
        <textarea id="aiHomeInput" rows="1" maxlength="12000" placeholder="Напиши или скажи…"></textarea>
        <button type="submit" class="ai-home-send" aria-label="Отправить">↑</button>
      </form>`;
    home.prepend(root);
    return root;
  }

  function aiHomeLatestAssistant() {
    const rows = Array.isArray(state.aiHomeMessages) ? state.aiHomeMessages : [];
    for (let i = rows.length - 1; i >= 0; i -= 1) {
      const row = rows[i];
      if (row && row.role === 'assistant' && String(row.content || '').trim()) return String(row.content).trim();
    }
    return '';
  }

  function aiHomeBusyState() {
    const rows = Array.isArray(state.aiHomeRequests) ? state.aiHomeRequests : [];
    if (rows.some(row => row && row.status === 'processing')) return 'thinking';
    if (rows.some(row => row && row.status === 'pending')) return 'queued';
    if (state.aiHomeStatus && state.aiHomeStatus.state === 'error') return 'error';
    return 'idle';
  }

  function aiHomeRender() {
    if (typeof state === 'undefined' || !state) return;
    aiHomeData();
    const root = aiHomeEnsureRoot();
    if (!root) return;
    const busy = aiHomeBusyState();
    const answer = aiHomeLatestAssistant();
    const sig = JSON.stringify([busy, answer, aiHomeListening, root.closest('#view-home')?.classList.contains('ai-home-mode')]);
    if (sig === aiHomeRenderSig) return;
    aiHomeRenderSig = sig;
    root.dataset.state = aiHomeListening ? 'listening' : busy;
    const status = document.getElementById('aiHomeState');
    if (status) {
      status.textContent = aiHomeListening ? 'Слушаю…' : busy === 'thinking' ? 'Думаю…' : busy === 'queued' ? 'Собираю контекст…' : busy === 'error' ? 'Не получилось. Можно отправить ещё раз.' : answer ? 'Что дальше?' : 'Скажи, как ты себя чувствуешь и что сегодня важно.';
    }
    const answerBox = document.getElementById('aiHomeAnswer');
    if (answerBox) {
      answerBox.hidden = !answer;
      if (answerBox.textContent !== answer) answerBox.textContent = answer;
    }
    const input = document.getElementById('aiHomeInput');
    const send = root.querySelector('.ai-home-send');
    if (input) input.disabled = busy === 'thinking';
    if (send) send.disabled = busy === 'thinking';
  }

  function aiHomeQueue(text) {
    const clean = String(text || '').trim();
    if (!clean || typeof saveState !== 'function') return;
    aiHomeData();
    const id = `ai-home-${Date.now()}-${Math.random().toString(36).slice(2,9)}`;
    state.aiHomeRequests = [...state.aiHomeRequests.slice(-19), {id, text:clean, status:'pending', createdAt: typeof nowIso === 'function' ? nowIso() : new Date().toISOString()}];
    state.aiHomeMessages = [...state.aiHomeMessages.slice(-22), {role:'user', content:clean}];
    state.aiHomeStatus = {state:'queued', requestId:id, updatedAt: typeof nowIso === 'function' ? nowIso() : new Date().toISOString()};
    saveState();
    const input = document.getElementById('aiHomeInput');
    if (input) input.value = '';
    aiHomeRenderSig = '';
    aiHomeRender();
  }

  function aiHomeRecognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function aiHomeStartVoice() {
    const Ctor = aiHomeRecognitionCtor();
    if (!Ctor) {
      if (typeof showToast === 'function') showToast('Голосовой ввод не поддерживается этим браузером.');
      document.getElementById('aiHomeInput')?.focus();
      return;
    }
    if (aiHomeListening && aiHomeRecognition) {
      try { aiHomeRecognition.stop(); } catch (_) {}
      return;
    }
    const recognition = new Ctor();
    aiHomeRecognition = recognition;
    recognition.lang = 'ru-RU';
    recognition.continuous = false;
    recognition.interimResults = true;
    let finalText = '';
    recognition.onstart = () => { aiHomeListening = true; aiHomeRenderSig=''; aiHomeRender(); };
    recognition.onresult = event => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const text = event.results[i][0]?.transcript || '';
        if (event.results[i].isFinal) finalText += text; else interim += text;
      }
      const input = document.getElementById('aiHomeInput');
      if (input) input.value = (finalText || interim).trim();
    };
    recognition.onerror = () => { aiHomeListening=false; aiHomeRenderSig=''; aiHomeRender(); };
    recognition.onend = () => {
      aiHomeListening = false;
      aiHomeRecognition = null;
      aiHomeRenderSig=''; aiHomeRender();
      const text = finalText.trim() || String(document.getElementById('aiHomeInput')?.value || '').trim();
      if (text) window.setTimeout(() => aiHomeQueue(text), 180);
    };
    try { recognition.start(); }
    catch (_) { aiHomeListening=false; aiHomeRecognition=null; aiHomeRenderSig=''; aiHomeRender(); }
  }

  document.addEventListener('submit', event => {
    if (event.target?.id !== 'aiHomeComposer') return;
    event.preventDefault();
    aiHomeQueue(document.getElementById('aiHomeInput')?.value || '');
  });

  document.addEventListener('keydown', event => {
    if (event.target?.id !== 'aiHomeInput') return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      aiHomeQueue(event.target.value);
    }
  });

  document.addEventListener('click', event => {
    if (event.target.closest('#aiHomeMic, #aiHomeOrb')) {
      event.preventDefault();
      aiHomeStartVoice();
      return;
    }
    const manual = event.target.closest('[data-ai-home-manual]');
    if (manual) {
      event.preventDefault();
      document.getElementById('view-home')?.classList.remove('ai-home-mode');
      aiHomeRenderSig='';
      return;
    }
    const back = event.target.closest('[data-ai-home-back]');
    if (back) {
      event.preventDefault();
      document.getElementById('view-home')?.classList.add('ai-home-mode');
      aiHomeRenderSig=''; aiHomeRender();
    }
  });

  function aiHomeEnsureManualBack() {
    const home = document.getElementById('view-home');
    if (!home || home.querySelector('[data-ai-home-back]')) return;
    const button = document.createElement('button');
    button.type='button'; button.className='ghost small ai-home-back'; button.setAttribute('data-ai-home-back','true'); button.textContent='← AI Home';
    home.appendChild(button);
  }

  function aiHomeBoot() {
    aiHomeEnsureRoot();
    aiHomeEnsureManualBack();
    aiHomeRender();
    window.setInterval(aiHomeRender, 1100);
    window.addEventListener('focus', () => { aiHomeRenderSig=''; aiHomeRender(); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', aiHomeBoot, {once:true});
  else queueMicrotask(aiHomeBoot);
'''

CSS = r'''

/* DVIZH_AI_HOME_V1 */
#view-home.ai-home-mode > :not(#aiHomeShell):not(#aiProposalPanel) { display:none !important; }
#view-home:not(.ai-home-mode) #aiHomeShell { display:none !important; }
#view-home.ai-home-mode .ai-home-back { display:none !important; }
.ai-home-back { position:relative; z-index:4; margin-bottom:10px; }
.ai-home-shell { min-height:calc(100dvh - 175px); display:grid; grid-template-rows:auto 1fr auto; gap:18px; padding:4px 0 12px; }
.ai-home-topbar { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:34px; }
.ai-home-brand { color:var(--faint,#727985); font-size:9px; font-weight:900; letter-spacing:.12em; }
.ai-home-manual { border:0; background:transparent; color:var(--faint,#727985); font:inherit; font-size:9px; font-weight:800; padding:8px; }
.ai-home-center { align-self:center; justify-self:stretch; display:grid; justify-items:center; gap:18px; padding:8vh 6px 3vh; }
.ai-home-orb { position:relative; width:84px; height:84px; border:0; border-radius:999px!important; background:transparent!important; box-shadow:none!important; display:grid; place-items:center; padding:0!important; }
.ai-home-orb span { position:absolute; inset:22px; border-radius:999px; border:1px solid rgba(200,255,53,.30); background:rgba(200,255,53,.035); animation:aiHomeBreath 3.8s ease-in-out infinite; }
.ai-home-orb span:nth-child(2) { inset:14px; opacity:.48; animation-delay:-1.2s; }
.ai-home-orb span:nth-child(3) { inset:5px; opacity:.18; animation-delay:-2.1s; }
.ai-home-shell[data-state="listening"] .ai-home-orb span { animation-duration:.85s; border-color:rgba(200,255,53,.72); }
.ai-home-shell[data-state="thinking"] .ai-home-orb span,
.ai-home-shell[data-state="queued"] .ai-home-orb span { animation-duration:1.45s; border-color:rgba(200,255,53,.52); }
.ai-home-state { margin:0; max-width:34ch; text-align:center; color:var(--muted,#a1a7b1); font-size:13px; line-height:1.45; }
.ai-home-answer { width:min(100%,620px); white-space:pre-wrap; color:#f4f5f6; font-size:16px; line-height:1.55; text-align:left; padding:8px 2px; }
.ai-home-composer { position:sticky; bottom:78px; z-index:7; display:grid; grid-template-columns:42px minmax(0,1fr) 42px; align-items:end; gap:7px; padding:7px; border:1px solid var(--line,rgba(255,255,255,.09)); border-radius:18px; background:rgba(17,19,24,.96); backdrop-filter:blur(16px); }
.ai-home-composer textarea { resize:none; max-height:120px; min-height:42px; border:0!important; background:transparent!important; padding:10px 5px!important; color:#f4f5f6; font:inherit; font-size:14px; line-height:1.45; outline:none; }
.ai-home-mic,.ai-home-send { width:42px; height:42px; min-height:42px!important; border-radius:13px!important; border:0!important; display:grid; place-items:center; padding:0!important; box-shadow:none!important; font-size:18px; }
.ai-home-mic { background:transparent!important; color:var(--muted,#a1a7b1)!important; }
.ai-home-send { background:var(--accent,#c8ff35)!important; color:#111!important; font-weight:900; }
.ai-home-send:disabled { opacity:.35; }
#view-home.ai-home-mode #aiProposalPanel { margin-top:4px; }
@keyframes aiHomeBreath { 0%,100% { transform:scale(.82); opacity:.30; } 50% { transform:scale(1.08); opacity:1; } }
@media (max-width:760px) {
  .ai-home-shell { min-height:calc(100dvh - 150px); }
  .ai-home-center { padding-top:7vh; }
  .ai-home-answer { font-size:15px; }
  .ai-home-composer { bottom:82px; }
}
@media (prefers-reduced-motion: reduce) {
  .ai-home-orb span { animation:none!important; }
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
    original = {name:path.read_text(encoding="utf-8") for name,path in files.items()}
    patched = {"app.js":insert_js(original["app.js"]), "styles.css":patch_css(original["styles.css"]), "sw.js":patch_sw(original["sw.js"])}
    if args.check:
        if MARKER_JS not in patched["app.js"] or MARKER_CSS not in patched["styles.css"] or CACHE_NAME not in patched["sw.js"]:
            raise SystemExit("AI Home marker check failed")
        print("ai home ui patch check=ok")
        return 0
    for name,value in patched.items(): files[name].write_text(value,encoding="utf-8")
    print("ai home ui patch=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
