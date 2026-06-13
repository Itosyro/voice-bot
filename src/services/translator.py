from dataclasses import dataclass

from src.config import settings
from src.prompts.translator import LANG_NAMES, TRANSLATE_PROMPT
from src.services.llm import OnDelta, complete


@dataclass
class TranslatorResult:
    text: str
    llm_ms: int
    model: str
    target_lang: str


async def run_translator(
    transcript: str,
    target_lang: str = "en",
    on_delta: OnDelta | None = None,
) -> TranslatorResult:
    lang_name = LANG_NAMES.get(target_lang, target_lang)

    system = TRANSLATE_PROMPT.format(
        target_lang_name=lang_name,
        target_lang_code=target_lang,
    )

    text, ms = await complete(
        system_prompt=system,
        user_message=f"<user_input>{transcript}</user_input>",
        api_key=settings.get_groq_key("translator"),
        model=settings.llm_model_default,
        temperature=0.3,
        on_delta=on_delta,
    )
    return TranslatorResult(
        text=text.strip(),
        llm_ms=ms,
        model=settings.llm_model_default,
        target_lang=target_lang,
    )
