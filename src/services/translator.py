from dataclasses import dataclass

from src.config import settings
from src.prompts.translator import LANG_NAMES, TRANSLATE_PROMPT
from src.services.llm import complete


@dataclass
class TranslatorResult:
    text: str
    llm_ms: int
    model: str
    target_lang: str


async def run_translator(
    transcript: str,
    target_lang: str = "en",
) -> TranslatorResult:
    lang_name = LANG_NAMES.get(target_lang, target_lang)

    system = TRANSLATE_PROMPT.format(
        target_lang_name=lang_name,
        target_lang_code=target_lang,
        transcript=transcript,
    )

    text, ms = await complete(
        system_prompt=system,
        user_message=transcript,
        api_key=settings.get_groq_key("translator"),
        model=settings.llm_model_default,
        temperature=0.3,
    )
    return TranslatorResult(
        text=text.strip(),
        llm_ms=ms,
        model=settings.llm_model_default,
        target_lang=target_lang,
    )
