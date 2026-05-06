from src.prompts.humanizer import HUMANIZER_PROMPTS
from src.prompts.polish import POLISH_PROMPTS
from src.prompts.prompt_eng import PROMPT_ENG_PROMPTS
from src.prompts.translator import TRANSLATE_PROMPT


def test_polish_prompts_have_transcript_placeholder():
    for name, tmpl in POLISH_PROMPTS.items():
        assert "{transcript}" in tmpl, f"{name} missing {{transcript}}"


def test_prompt_eng_prompts_have_placeholders():
    for name, tmpl in PROMPT_ENG_PROMPTS.items():
        assert "{transcript}" in tmpl, f"{name} missing {{transcript}}"
        assert "{skills_context}" in tmpl, f"{name} missing {{skills_context}}"


def test_humanizer_prompts_have_text_placeholder():
    for name, tmpl in HUMANIZER_PROMPTS.items():
        assert "{text}" in tmpl, f"{name} missing {{text}}"


def test_translator_prompt_has_placeholders():
    assert "{target_lang_name}" in TRANSLATE_PROMPT
    assert "{target_lang_code}" in TRANSLATE_PROMPT
    assert "{transcript}" in TRANSLATE_PROMPT


def test_polish_renders():
    rendered = POLISH_PROMPTS["polish_default"].format(transcript="test text")
    assert "test text" in rendered


def test_prompt_eng_renders():
    rendered = PROMPT_ENG_PROMPTS["prompt_general"].format(
        transcript="build a saas", skills_context="<no skills>"
    )
    assert "build a saas" in rendered
    assert "<no skills>" in rendered


def test_humanizer_renders():
    rendered = HUMANIZER_PROMPTS["humanize_lite"].format(text="ai generated text")
    assert "ai generated text" in rendered


def test_translator_renders():
    rendered = TRANSLATE_PROMPT.format(
        target_lang_name="English", target_lang_code="en", transcript="hello world"
    )
    assert "English" in rendered
    assert "hello world" in rendered
