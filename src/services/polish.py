from dataclasses import dataclass

from src.config import settings
from src.prompts.polish import POLISH_PROMPTS
from src.services.llm import OnDelta, complete


@dataclass
class PolishResult:
    text: str
    llm_ms: int
    model: str


TEMPERATURE_MAP = {
    "polish_default": 0.2,
    "polish_creative": 0.7,
    "polish_formal": 0.3,
    "polish_embellish": 0.6,
}


async def run_polish(
    transcript: str, sub_style: str = "polish_default", on_delta: OnDelta | None = None
) -> PolishResult:
    if sub_style not in POLISH_PROMPTS:
        sub_style = "polish_default"

    system = POLISH_PROMPTS[sub_style]
    text, ms = await complete(
        system_prompt=system,
        user_message=f"<user_input>{transcript}</user_input>",
        api_key=settings.get_groq_key("polish"),
        model=settings.llm_model_default,
        temperature=TEMPERATURE_MAP.get(sub_style, 0.3),
        on_delta=on_delta,
    )
    return PolishResult(text=text.strip(), llm_ms=ms, model=settings.llm_model_default)
