import asyncio
import time
from functools import lru_cache

import structlog
from groq import AsyncGroq

log = structlog.get_logger()

_MAX_RETRIES = 2
_RETRY_DELAY = 1.5


@lru_cache(maxsize=8)
def _get_client(api_key: str) -> AsyncGroq:
    return AsyncGroq(api_key=api_key)


async def complete(
    system_prompt: str,
    user_message: str,
    api_key: str,
    model: str,
    temperature: float = 0.5,
    max_tokens: int = 4096,
) -> tuple[str, int]:
    """Call Groq LLM with retry. Returns (response_text, elapsed_ms)."""
    client = _get_client(api_key)
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
            if attempt < _MAX_RETRIES:
                log.warning("groq_retry", attempt=attempt + 1, error=str(exc))
                await asyncio.sleep(_RETRY_DELAY * (attempt + 1))

    raise last_exc  # type: ignore[misc]
