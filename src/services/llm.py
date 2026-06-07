import asyncio
import time

from groq import AsyncGroq


async def complete(
    system_prompt: str,
    user_message: str,
    api_key: str,
    model: str,
    temperature: float = 0.5,
    max_tokens: int = 4096,
) -> tuple[str, int]:
    """Call Groq LLM. Returns (response_text, elapsed_ms). Retries once on error."""
    client = AsyncGroq(api_key=api_key)
    started = time.monotonic()
    last_exc: Exception | None = None

    for attempt in range(2):
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
        except Exception as e:
            last_exc = e
            if attempt == 0:
                await asyncio.sleep(2)

    raise last_exc  # type: ignore[misc]
