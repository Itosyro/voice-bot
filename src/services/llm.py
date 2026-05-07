import asyncio
import time
from functools import lru_cache

import structlog
from groq import AsyncGroq

from src.config import settings

log = structlog.get_logger()

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0
_FALLBACK_MODEL = "llama-3.3-70b-versatile"


@lru_cache(maxsize=8)
def get_client(api_key: str) -> AsyncGroq:
    return AsyncGroq(api_key=api_key)


def is_rate_limit_error(exc: Exception) -> bool:
    """Check if exception is a rate limit error."""
    exc_str = str(exc).lower()
    return "rate" in exc_str or "limit" in exc_str


async def complete(
    system_prompt: str,
    user_message: str,
    api_key: str,
    model: str,
    temperature: float = 0.5,
    max_tokens: int = 4096,
) -> tuple[str, int]:
    """Call Groq LLM with retry + key rotation on rate limit + fallback model."""
    current_key = api_key
    client = get_client(current_key)
    started = time.monotonic()
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return resp.choices[0].message.content or "", elapsed_ms
        except Exception as exc:
            last_exc = exc
            rate_limited = is_rate_limit_error(exc)
            log.warning(
                "groq_retry",
                attempt=attempt + 1,
                model=model,
                error=str(exc),
                rate_limited=rate_limited,
            )
            if attempt < _MAX_RETRIES:
                if rate_limited:
                    alt_keys = [k for k in settings.get_all_groq_keys() if k != current_key]
                    if alt_keys:
                        current_key = alt_keys[attempt % len(alt_keys)]
                        client = get_client(current_key)
                        log.info("groq_key_rotation", attempt=attempt + 1)
                await asyncio.sleep(_RETRY_DELAY * (attempt + 1))

    if model != _FALLBACK_MODEL:
        log.warning("groq_fallback", original_model=model, fallback=_FALLBACK_MODEL)
        try:
            resp = await client.chat.completions.create(
                model=_FALLBACK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=min(max_tokens, 4096),
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return resp.choices[0].message.content or "", elapsed_ms
        except Exception as fallback_exc:
            log.error("groq_fallback_failed", error=str(fallback_exc))

    raise last_exc  # type: ignore[misc]
