from dataclasses import dataclass

from src.config import settings
from src.prompts.humanizer import HUMANIZER_PROMPTS
from src.services.llm import complete


@dataclass
class HumanizerResult:
    text: str
    llm_ms: int
    model: str


TEMPERATURE_MAP = {
    "humanize_lite": 0.4,
    "humanize_strong": 0.7,
}


async def run_humanizer(text: str, sub_style: str = "humanize_lite") -> HumanizerResult:
    if sub_style not in HUMANIZER_PROMPTS:
        sub_style = "humanize_lite"

    system = HUMANIZER_PROMPTS[sub_style].format(text="{see user message}")
    result, ms = await complete(
        system_prompt=system,
        user_message=text,
        api_key=settings.get_groq_key("humanizer"),
        model=settings.llm_model_default,
        temperature=TEMPERATURE_MAP.get(sub_style, 0.5),
    )
    return HumanizerResult(text=result.strip(), llm_ms=ms, model=settings.llm_model_default)
