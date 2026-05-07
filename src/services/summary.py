from dataclasses import dataclass

from src.config import settings
from src.prompts.summary import SUMMARY_PROMPT
from src.services.llm import complete


@dataclass
class SummaryResult:
    text: str
    llm_ms: int
    model: str


async def run_summary(transcript: str) -> SummaryResult:
    system = SUMMARY_PROMPT.format(transcript="{see user message}")
    text, ms = await complete(
        system_prompt=system,
        user_message=transcript,
        api_key=settings.get_groq_key("polish"),
        model=settings.llm_model_default,
        temperature=0.3,
    )
    return SummaryResult(text=text.strip(), llm_ms=ms, model=settings.llm_model_default)
