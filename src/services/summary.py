from dataclasses import dataclass

from src.config import settings
from src.prompts.summary import SUMMARY_PROMPT
from src.services.llm import OnDelta, complete


@dataclass
class SummaryResult:
    text: str
    llm_ms: int
    model: str


async def run_summary(transcript: str, on_delta: OnDelta | None = None) -> SummaryResult:
    text, ms = await complete(
        system_prompt=SUMMARY_PROMPT,
        user_message=f"<user_input>{transcript}</user_input>",
        api_key=settings.get_groq_key("summary"),
        model=settings.llm_model_default,
        temperature=0.3,
        on_delta=on_delta,
    )
    return SummaryResult(text=text.strip(), llm_ms=ms, model=settings.llm_model_default)
