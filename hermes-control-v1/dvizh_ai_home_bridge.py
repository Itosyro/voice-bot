#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import logging
import os
import signal
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "2026.09.05-ai-home.1"
UTC = timezone.utc
LOG = logging.getLogger("dvizh.ai.home")

IDENTITY_PATH = Path("/var/lib/dvizh/auth-identity.json")
STATUS_PATH = Path("/var/lib/dvizh/ai-home-status.json")
WEB_API = os.environ.get("DVIZH_WEB_API", "http://127.0.0.1:8000").rstrip("/")
HERMES_API = os.environ.get("HERMES_API_URL", "http://127.0.0.1:8642/v1").rstrip("/")
HERMES_API_KEY = os.environ.get("HERMES_API_KEY", "").strip()
HERMES_MODEL = os.environ.get("HERMES_API_MODEL", "hermes-agent").strip() or "hermes-agent"
INTERVAL = max(1, min(10, int(os.environ.get("DVIZH_AI_HOME_INTERVAL", "2"))))
WEB_TIMEOUT = max(2, min(20, int(os.environ.get("DVIZH_AI_HOME_WEB_TIMEOUT", "8"))))
HERMES_TIMEOUT = max(20, min(300, int(os.environ.get("DVIZH_AI_HOME_HERMES_TIMEOUT", "180"))))
STOP = False

SYSTEM_PROMPT = """Ты — ИИ-мозг приложения ДВИЖ. Отвечай по-русски, компактно и практично.
Всегда используй skill dvizh-server и dvizhctl, когда вопрос зависит от текущих задач, недели, тренировок, Jump Lab, соцсетей или состояния ДВИЖа. Читай самый узкий нужный context.
Если пользователь просит что-то изменить в ДВИЖе — НЕ меняй напрямую. Создай только разрешённый proposal через dvizhctl и ясно скажи, что его нужно подтвердить в приложении.
Если пользователь просто делится самочувствием, выходным/рабочим днём, свободным временем или целями на день — помоги собрать реалистичный план без перегруза. Не заставляй заполнять анкету: извлекай детали из естественной речи. Задавай максимум один уточняющий вопрос только если без него нельзя дать полезный ответ.
Не читай секреты и не обходи безопасный слой dvizhctl.
"""


class BridgeError(RuntimeError):
    pass


class RevisionConflict(BridgeError):
    pass


def iso(value: datetime | None = None) -> str:
    return (value or datetime.now(tz=UTC)).astimezone(UTC).isoformat()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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


def load_identity() -> tuple[str, str]:
    try:
        payload = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise BridgeError("stable DVIZH identity unavailable") from exc
    user_id = recursive_value(payload, ("DVIZH_WEB_USER_ID", "user_id", "userId", "web_user_id", "webUserId", "subject", "uid", "id")) or ""
    email = recursive_value(payload, ("DVIZH_WEB_USER_EMAIL", "email", "user_email", "userEmail")) or ""
    if not user_id:
        raise BridgeError("stable DVIZH identity has no user id")
    return user_id, email or "local-account@dvizh.invalid"


class WebClient:
    def __init__(self, user_id: str, email: str):
        self.user_id = user_id
        self.email = email

    def request(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = canonical(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/json",
            "User-Agent": f"DVIZH-AI-Home/{VERSION}",
            "X-ExeDev-UserID": self.user_id,
            "X-ExeDev-Email": self.email,
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(WEB_API + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=WEB_TIMEOUT) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            if exc.code == 409:
                raise RevisionConflict(detail) from exc
            raise BridgeError(f"web API HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise BridgeError("web API unavailable") from exc
        try:
            result = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise BridgeError("web API returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise BridgeError("web API returned non-object")
        return result

    def get_state(self) -> tuple[int, dict[str, Any]]:
        result = self.request("/api/state")
        state = result.get("state")
        if not isinstance(state, dict):
            raise BridgeError("web state missing")
        return int(result.get("revision") or 0), state

    def put_state(self, revision: int, state: dict[str, Any]) -> int:
        result = self.request("/api/state", "PUT", {"baseRevision": revision, "state": state})
        if result.get("ok") is not True:
            raise BridgeError("web state update refused")
        return int(result.get("revision") or revision + 1)


def normalize_messages(value: Any) -> list[dict[str, str]]:
    rows = value if isinstance(value, list) else []
    out: list[dict[str, str]] = []
    for row in rows[-16:]:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role") or "")
        content = str(row.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        out.append({"role": role, "content": content[:8000]})
    return out


def request_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    value = state.get("aiHomeRequests")
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def next_request(state: dict[str, Any]) -> dict[str, Any] | None:
    now_ts = time.time()
    for row in request_rows(state):
        status = str(row.get("status") or "pending")
        if status == "pending":
            return row
        if status == "processing":
            started = row.get("startedAtEpoch")
            try:
                stale = now_ts - float(started) > 240
            except Exception:
                stale = True
            if stale:
                return row
    return None


def hermes_messages(state: dict[str, Any], request: dict[str, Any]) -> list[dict[str, str]]:
    text = str(request.get("text") or "").strip()
    if not text:
        raise BridgeError("empty AI Home request")
    history = normalize_messages(state.get("aiHomeMessages"))
    # UI normally appends the current user message before queueing. Avoid duplicating it.
    if history and history[-1]["role"] == "user" and history[-1]["content"] == text:
        history = history[:-1]
    return [{"role": "system", "content": SYSTEM_PROMPT}, *history[-10:], {"role": "user", "content": text[:12000]}]


def call_hermes(messages: list[dict[str, str]]) -> str:
    if len(HERMES_API_KEY) < 20:
        raise BridgeError("Hermes API key is not configured")
    payload = {
        "model": HERMES_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        HERMES_API + "/chat/completions",
        data=canonical(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + HERMES_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"DVIZH-AI-Home/{VERSION}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HERMES_TIMEOUT) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise BridgeError(f"Hermes API HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise BridgeError("Hermes API unavailable or timed out") from exc
    try:
        result = json.loads(raw.decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
    except Exception as exc:
        raise BridgeError("Hermes API returned invalid response") from exc
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        text = "\n".join(str(part.get("text") or "") for part in content if isinstance(part, dict)).strip()
    else:
        text = str(content or "").strip()
    if not text:
        raise BridgeError("Hermes returned an empty answer")
    return text[:20000]


def update_request_state(client: WebClient, request_id: str, updater) -> dict[str, Any]:
    for attempt in range(1, 8):
        revision, state = client.get_state()
        updated = copy.deepcopy(state)
        rows = request_rows(updated)
        found = False
        for row in rows:
            if str(row.get("id") or "") == request_id:
                updater(updated, row)
                found = True
                break
        if not found:
            raise BridgeError("AI Home request disappeared")
        updated["aiHomeRequests"] = rows[-30:]
        try:
            client.put_state(revision, updated)
            return updated
        except RevisionConflict:
            time.sleep(0.1 * attempt)
    raise BridgeError("web state kept changing")


def mark_processing(client: WebClient, request_id: str) -> dict[str, Any]:
    def mutate(state: dict[str, Any], row: dict[str, Any]) -> None:
        row["status"] = "processing"
        row["startedAt"] = iso()
        row["startedAtEpoch"] = time.time()
        state["aiHomeStatus"] = {"state": "thinking", "requestId": request_id, "updatedAt": iso()}
    return update_request_state(client, request_id, mutate)


def mark_done(client: WebClient, request_id: str, answer: str) -> None:
    def mutate(state: dict[str, Any], row: dict[str, Any]) -> None:
        row["status"] = "done"
        row["finishedAt"] = iso()
        messages = normalize_messages(state.get("aiHomeMessages"))
        messages.append({"role": "assistant", "content": answer})
        state["aiHomeMessages"] = messages[-24:]
        state["aiHomeStatus"] = {"state": "ready", "requestId": request_id, "updatedAt": iso()}
    update_request_state(client, request_id, mutate)


def mark_error(client: WebClient, request_id: str, error: str) -> None:
    def mutate(state: dict[str, Any], row: dict[str, Any]) -> None:
        row["status"] = "error"
        row["finishedAt"] = iso()
        row["error"] = error[:300]
        state["aiHomeStatus"] = {"state": "error", "requestId": request_id, "message": error[:300], "updatedAt": iso()}
    update_request_state(client, request_id, mutate)


def write_status(payload: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": VERSION, "at": iso(), **payload}, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o640)
    os.replace(tmp, STATUS_PATH)


def sync_once() -> dict[str, Any]:
    user_id, email = load_identity()
    client = WebClient(user_id, email)
    _revision, state = client.get_state()
    request = next_request(state)
    if request is None:
        payload = {"ok": True, "busy": False, "model": HERMES_MODEL}
        write_status(payload)
        return payload
    request_id = str(request.get("id") or "")[:160]
    if not request_id:
        raise BridgeError("AI Home request has no id")
    state = mark_processing(client, request_id)
    active = next((row for row in request_rows(state) if str(row.get("id") or "") == request_id), None)
    if not active:
        raise BridgeError("AI Home request missing after processing mark")
    try:
        answer = call_hermes(hermes_messages(state, active))
        mark_done(client, request_id, answer)
        payload = {"ok": True, "busy": False, "processed": request_id, "model": HERMES_MODEL}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        LOG.warning("AI Home request failed: %s", error)
        try:
            mark_error(client, request_id, error)
        except Exception:
            LOG.exception("could not publish AI Home error")
        payload = {"ok": False, "busy": False, "processed": request_id, "error": error[:300], "model": HERMES_MODEL}
    write_status(payload)
    return payload


def handle_signal(_signum: int, _frame: Any) -> None:
    global STOP
    STOP = True


def main() -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    LOG.info("starting DVIZH AI Home bridge %s", VERSION)
    while not STOP:
        try:
            sync_once()
        except Exception as exc:
            LOG.warning("AI Home bridge waiting/error: %s", exc)
            try:
                write_status({"ok": False, "busy": False, "error": f"{type(exc).__name__}: {exc}"[:300], "model": HERMES_MODEL})
            except Exception:
                pass
        for _ in range(INTERVAL * 2):
            if STOP:
                break
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
