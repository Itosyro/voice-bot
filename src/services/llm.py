import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog
from groq import AsyncGroq, RateLimitError

from src.config import settings

log = structlog.get_logger()

OnDelta = Callable[[str], Awaitable[None]]


@dataclass
class LLMResult:
    """Ответ модели + правда о том, КТО его дал.

    Раньше сервисы писали в историю settings.llm_model_default, даже если
    ответ реально пришёл от фолбэк-модели или внешнего провайдера.
    """

    text: str
    elapsed_ms: int
    model: str
    provider: str  # "groq" | "cerebras" | "openrouter"


class ModelUnavailableError(RuntimeError):
    """All candidate models are decommissioned/unknown at the provider."""


class RequestTooLargeError(RuntimeError):
    """Запрос не влезает в лимиты бесплатного тарифа (и нет провайдера с
    длинным контекстом). Ретраи бессмысленны — юзеру нужен честный совет."""


def sanitize_user_input(text: str) -> str:
    """Убираем поддельные закрывающие теги: пользовательский текст не должен
    уметь «выпрыгнуть» из <user_input>-обёртки (обход защиты из PR#6)."""
    return text.replace("</user_input>", "")


def is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception indicates a rate-limit (429) response."""
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


def estimate_tokens(text: str) -> int:
    """Грубая оценка токенов: для кириллицы реально ~2 символа/токен, считаем
    консервативно, чтобы длинный транскрипт не проскочил мимо роутинга."""
    return len(text) // 2 + 1


def _reasoning_extra(model: str, reasoning_effort: str | None) -> dict[str, str]:
    """Params required by reasoning models (gpt-oss family) to emit content.

    Без reasoning_effort + reasoning_format="hidden" gpt-oss на Groq возвращает
    пустой content (грабли из CLAUDE.md) — поэтому для gpt-oss ставим их всегда.
    Только для Groq: сторонние провайдеры этих параметров не ждут.
    """
    if reasoning_effort is None and "gpt-oss" in model:
        reasoning_effort = "low"
    if not reasoning_effort:
        return {}
    return {"reasoning_effort": reasoning_effort, "reasoning_format": "hidden"}


async def _stream_chat(
    client,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
    extra: dict,
    on_delta: OnDelta | None,
) -> str:
    """Stream one chat completion; Groq и OpenAI-совместимые клиенты дают
    одинаковую форму чанков (choices[0].delta.content)."""
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
    finish_reason = None
    async for chunk in stream:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if choice.finish_reason:
            finish_reason = choice.finish_reason
        delta = choice.delta.content or ""
        if delta:
            full_text += delta
            if on_delta:
                await on_delta(full_text)
    if full_text and finish_reason == "length":
        # Молчаливый обрыв на полуслове хуже честной пометки.
        log.warning("llm_response_truncated", model=model)
        full_text += "\n\n[…ответ обрезан по лимиту длины — попробуй разбить запрос]"
    return full_text


@dataclass
class _FallbackProvider:
    name: str
    base_url: str
    api_key: str
    model: str


def _fallback_providers(long_context: bool) -> list[_FallbackProvider]:
    """Настроенные внешние OpenAI-совместимые провайдеры, по порядку попыток.

    long_context=True — только провайдеры с большим контекстом (OpenRouter):
    Cerebras free урезан до ~8K и длинный транскрипт не примет.
    """
    providers: list[_FallbackProvider] = []
    if settings.cerebras_api_key and not long_context:
        providers.append(
            _FallbackProvider(
                name="cerebras",
                base_url="https://api.cerebras.ai/v1",
                api_key=settings.cerebras_api_key,
                model=settings.cerebras_model,
            )
        )
    if settings.openrouter_api_key:
        providers.append(
            _FallbackProvider(
                name="openrouter",
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.openrouter_api_key,
                model=settings.openrouter_model,
            )
        )
    return providers


async def _try_fallback_providers(
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
    on_delta: OnDelta | None,
    long_context: bool,
) -> tuple[str, str, str] | None:
    """Прогоняем внешних провайдеров. Возвращает (text, provider, model) или None."""
    for provider in _fallback_providers(long_context):
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(base_url=provider.base_url, api_key=provider.api_key)
            text = await _stream_chat(
                client,
                provider.model,
                system_prompt,
                user_message,
                temperature,
                max_tokens,
                {},
                on_delta,
            )
            if text:
                log.warning("llm_external_provider_used", provider=provider.name)
                return text, provider.name, provider.model
        except Exception as exc:
            log.warning("llm_external_provider_failed", provider=provider.name, error=str(exc))
    return None


async def complete(
    system_prompt: str,
    user_message: str,
    api_key: str,
    model: str,
    temperature: float = 0.5,
    max_tokens: int = 4096,
    reasoning_effort: str | None = None,
    on_delta: OnDelta | None = None,
) -> LLMResult:
    """Call the LLM via streaming. Returns LLMResult (текст + кто ответил).

    Порядок: Groq (осн. модель → фолбэк-модели, ретраи, ротация ключей на 429)
    → внешние провайдеры (Cerebras/OpenRouter), если настроены ключи.
    Запрос, не влезающий в TPM Groq free, сразу роутится в OpenRouter
    (контекст 131K) — иначе Groq гарантированно вернёт 413.
    """
    started = time.monotonic()

    # Длинный вход (часовое голосовое ≈ 12-18K токенов) в Groq free не влезает.
    request_tokens = estimate_tokens(system_prompt + user_message) + max_tokens
    if request_tokens > settings.groq_max_request_tokens:
        external = await _try_fallback_providers(
            system_prompt, user_message, temperature, max_tokens, on_delta, long_context=True
        )
        if external:
            text, provider_name, provider_model = external
            return LLMResult(
                text=text,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                model=provider_model,
                provider=provider_name,
            )
        log.warning(
            "llm_long_request_no_provider",
            request_tokens=request_tokens,
            hint="set OPENROUTER_API_KEY to handle long transcripts",
        )
        # Провайдера с длинным контекстом нет — пробуем Groq: вдруг тариф платный.
        long_request_without_provider = True
    else:
        long_request_without_provider = False

    models_to_try = [model] + [m for m in settings.llm_model_fallbacks_list if m != model]
    current_key = api_key
    client = AsyncGroq(api_key=current_key)
    last_exc: Exception | None = None
    permanent_error = False

    for model_idx, current_model in enumerate(models_to_try):
        extra = _reasoning_extra(current_model, reasoning_effort)

        for attempt in range(3):
            try:
                full_text = await _stream_chat(
                    client,
                    current_model,
                    system_prompt,
                    user_message,
                    temperature,
                    max_tokens,
                    extra,
                    on_delta,
                )
                if full_text:
                    elapsed_ms = int((time.monotonic() - started) * 1000)
                    if model_idx > 0:
                        log.warning("llm_fallback_model_used", model=current_model, wanted=model)
                    return LLMResult(
                        text=full_text,
                        elapsed_ms=elapsed_ms,
                        model=current_model,
                        provider="groq",
                    )

                last_exc = RuntimeError("Groq returned empty response")
            except Exception as e:
                last_exc = e
                if is_model_unavailable_error(e):
                    log.warning("llm_model_unavailable", model=current_model, error=str(e))
                    break  # no point retrying — jump to the next fallback model
                if getattr(e, "status_code", None) in (400, 401, 403, 404, 413):
                    # Постоянные ошибки (битый ключ/запрос) — ретраи только тянут
                    # время. Даём шанс внешним провайдерам ниже.
                    log.warning("llm_permanent_error", model=current_model, error=str(e))
                    permanent_error = True
                    break
                if is_rate_limit_error(e):
                    alt_keys = [k for k in settings.get_all_groq_keys() if k != current_key]
                    if alt_keys:
                        current_key = alt_keys[attempt % len(alt_keys)]
                        client = AsyncGroq(api_key=current_key)

            if attempt < 2:
                await asyncio.sleep(2 * (attempt + 1))
        else:
            # 3 attempts exhausted on a live model — stop the Groq chain (do not
            # switch models mid-outage: результат станет непредсказуемым).
            break

        if permanent_error:
            break  # битый ключ/запрос — Groq-цепочку не продолжаем

    # Groq не справился — внешние провайдеры (если настроены).
    external = await _try_fallback_providers(
        system_prompt, user_message, temperature, max_tokens, on_delta, long_context=False
    )
    if external:
        text, provider_name, provider_model = external
        return LLMResult(
            text=text,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            model=provider_model,
            provider=provider_name,
        )

    if last_exc is not None and is_model_unavailable_error(last_exc):
        raise ModelUnavailableError(
            f"All models unavailable: {', '.join(models_to_try)}"
        ) from last_exc
    if last_exc is not None and getattr(last_exc, "status_code", None) == 413:
        # 413 = запрос не влез в тариф. Оценка токенов приблизительна, поэтому
        # ловим и те запросы, которые проскочили мимо предварительной проверки.
        raise RequestTooLargeError(str(last_exc)) from last_exc
    if (
        last_exc is not None
        and long_request_without_provider
        and getattr(last_exc, "status_code", None) in (400, 429)
    ):
        # 413/429 на заведомо длинном запросе — это не «сервер недоступен»,
        # а лимит тарифа: совет «попробуй через минуту» здесь враньё.
        raise RequestTooLargeError(str(last_exc)) from last_exc
    raise last_exc  # type: ignore[misc]
