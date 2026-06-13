from dataclasses import dataclass

from src.config import settings
from src.prompts.humanizer import HUMANIZER_PROMPTS
from src.services.llm import OnDelta, complete


@dataclass
class HumanizerResult:
    text: str
    llm_ms: int
    model: str


TEMPERATURE_MAP = {
    "humanize_lite": 0.4,
    "humanize_strong": 0.7,
}


async def run_humanizer(
    text: str, sub_style: str = "humanize_lite", on_delta: OnDelta | None = None
) -> HumanizerResult:
    if sub_style not in HUMANIZER_PROMPTS:
        sub_style = "humanize_lite"

    system = HUMANIZER_PROMPTS[sub_style]
    result, ms = await complete(
        system_prompt=system,
        user_message=f"<user_input>{text}</user_input>",
        api_key=settings.get_groq_key("humanizer"),
        model=settings.llm_model_default,
        temperature=TEMPERATURE_MAP.get(sub_style, 0.5),
        on_delta=on_delta,
    )
    return HumanizerResult(text=result.strip(), llm_ms=ms, model=settings.llm_model_default)
