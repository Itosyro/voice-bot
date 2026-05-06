from dataclasses import dataclass, field

from src.config import settings
from src.prompts.prompt_eng import PROMPT_ENG_PROMPTS
from src.services.llm import complete
from src.services.skills_db import SkillsDB


@dataclass
class PromptResult:
    text: str
    llm_ms: int
    model: str
    used_skills: list[str] = field(default_factory=list)


async def run_prompt_eng(
    transcript: str,
    sub_style: str,
    skills_db: SkillsDB,
) -> PromptResult:
    if sub_style not in PROMPT_ENG_PROMPTS:
        sub_style = "prompt_general"

    style_short = sub_style.replace("prompt_", "")
    relevant = skills_db.search(transcript, sub_style=style_short, top_k=2)
    skills_context = SkillsDB.format_for_prompt(relevant)

    system = PROMPT_ENG_PROMPTS[sub_style].format(
        transcript=transcript,
        skills_context=skills_context,
    )

    model = (
        settings.llm_model_strict
        if sub_style == "prompt_coder_strict"
        else settings.llm_model_default
    )

    temperature = 0.3 if sub_style == "prompt_coder_strict" else 0.4

    text, ms = await complete(
        system_prompt=system,
        user_message=transcript,
        api_key=settings.get_groq_key("prompt"),
        model=model,
        temperature=temperature,
        max_tokens=8000,
    )
    return PromptResult(
        text=text.strip(),
        llm_ms=ms,
        model=model,
        used_skills=[s.skill_name for s in relevant],
    )
