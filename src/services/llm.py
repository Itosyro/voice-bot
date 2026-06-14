import asyncio
import time
from collections.abc import Awaitable, Callable

from groq import AsyncGroq, RateLimitError

from src.config import settings

OnDelta = Callable[[str], Awaitable[None]]


def is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception indicates a Groq rate-limit (429) response."""
    if isinstance(exc, RateLimitError):
        return True
    status = getattr(exc, "status_code", None)
    return status == 429


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
    """
    current_key = api_key
    client = AsyncGroq(api_key=current_key)
    started = time.monotonic()
    last_exc: Exception | None = None

    extra: dict[str, str] = {}
    if reasoning_effort:
        extra["reasoning_effort"] = reasoning_effort
        extra["reasoning_format"] = "hidden"

    for attempt in range(3):
        try:
            stream = await client.chat.completions.create(
                model=model,
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
                return full_text, elapsed_ms

            last_exc = RuntimeError("Groq returned empty response")
        except Exception as e:
            last_exc = e
            if is_rate_limit_error(e):
                alt_keys = [k for k in settings.get_all_groq_keys() if k != current_key]
                if alt_keys:
                    current_key = alt_keys[attempt % len(alt_keys)]
                    client = AsyncGroq(api_key=current_key)

        if attempt < 2:
            await asyncio.sleep(2 * (attempt + 1))

    raise last_exc  # type: ignore[misc]
