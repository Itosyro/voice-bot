import asyncio
import time
from collections.abc import Awaitable, Callable

import structlog
from groq import AsyncGroq, RateLimitError

from src.config import settings

log = structlog.get_logger()

OnDelta = Callable[[str], Awaitable[None]]


class ModelUnavailableError(RuntimeError):
    """All candidate models are decommissioned/unknown at the provider."""


def is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception indicates a Groq rate-limit (429) response."""
    if isinstance(exc, RateLimitError):
        return True
    status = getattr(exc, "status_code", None)
    return status == 429


def is_model_unavailable_error(exc: Exception) -> bool:
    """True if the provider says the model itself is gone (decommissioned/unknown).

    Groq возвращает 404 model_not_found или 400 model_decommissioned, когда
    модель отключена (как llama-3.3-70b-versatile в августе 2026). Такие ошибки
    ретраить бессмысленно — надо переключаться на запасную модель.
    """
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    markers = ("model_decommissioned", "model_not_found", "does not exist or you do not have")
    if any(m in text for m in markers):
        return True
    return status == 404 and "model" in text


def _reasoning_extra(model: str, reasoning_effort: str | None) -> dict[str, str]:
    """Params required by reasoning models (gpt-oss family) to emit content.

    Без reasoning_effort + reasoning_format="hidden" gpt-oss возвращает пустой
    content (грабли из CLAUDE.md) — поэтому для gpt-oss ставим их всегда.
    """
    if reasoning_effort is None and "gpt-oss" in model:
        reasoning_effort = "low"
    if not reasoning_effort:
        return {}
    return {"reasoning_effort": reasoning_effort, "reasoning_format": "hidden"}


async def complete(
    system_prompt: str,
    user_message: str,
    api_key: str,
    model: str,
    temperature: float = 0.5,
    max_tokens: int = 4096,
    reasoning_effort: str | None = None,
    on_delta: OnDelta | None = None,
) -> tuple[str, int]:
    """Call Groq LLM via streaming. Returns (response_text, elapsed_ms).

    If on_delta is given, it's called with the accumulated text after each chunk.
    Retries up to 3 times with backoff on transient errors or empty output; on
    rate-limit (429) it rotates through other configured Groq keys to spread load.
    If the provider reports the model as decommissioned/unknown, falls back to
    the next model from settings.llm_model_fallbacks_list instead of retrying.
    """
    models_to_try = [model] + [m for m in settings.llm_model_fallbacks_list if m != model]
    current_key = api_key
    client = AsyncGroq(api_key=current_key)
    started = time.monotonic()
    last_exc: Exception | None = None

    for model_idx, current_model in enumerate(models_to_try):
        extra = _reasoning_extra(current_model, reasoning_effort)

        for attempt in range(3):
            try:
                stream = await client.chat.completions.create(
                    model=current_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=temperature,
                    max_completion_tokens=max_tokens,
                    stream=True,
                    **extra,
                )
                full_text = ""
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    if delta:
                        full_text += delta
                        if on_delta:
                            await on_delta(full_text)

                if full_text:
                    elapsed_ms = int((time.monotonic() - started) * 1000)
                    if model_idx > 0:
                        log.warning("llm_fallback_model_used", model=current_model, wanted=model)
                    return full_text, elapsed_ms

                last_exc = RuntimeError("Groq returned empty response")
            except Exception as e:
                last_exc = e
                if is_model_unavailable_error(e):
                    log.warning("llm_model_unavailable", model=current_model, error=str(e))
                    break  # no point retrying — jump to the next fallback model
                if getattr(e, "status_code", None) in (400, 401, 403, 404, 413):
                    # Постоянные ошибки (битый ключ/запрос) — ретраи только тянут
                    # время до сообщения об ошибке.
                    log.warning("llm_permanent_error", model=current_model, error=str(e))
                    raise
                if is_rate_limit_error(e):
                    alt_keys = [k for k in settings.get_all_groq_keys() if k != current_key]
                    if alt_keys:
                        current_key = alt_keys[attempt % len(alt_keys)]
                        client = AsyncGroq(api_key=current_key)

            if attempt < 2:
                await asyncio.sleep(2 * (attempt + 1))
        else:
            # 3 attempts exhausted on a live model — give up entirely (do not
            # switch models mid-outage: результат станет непредсказуемым).
            break

    if last_exc is not None and is_model_unavailable_error(last_exc):
        raise ModelUnavailableError(
            f"All models unavailable: {', '.join(models_to_try)}"
        ) from last_exc
    raise last_exc  # type: ignore[misc]
