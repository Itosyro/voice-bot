from src.prompts.humanizer import HUMANIZER_PROMPTS
from src.prompts.polish import POLISH_PROMPTS
from src.prompts.prompt_eng import PROMPT_ENG_PROMPTS
from src.prompts.summary import SUMMARY_PROMPT
from src.prompts.translator import TRANSLATE_PROMPT


def test_prompt_eng_prompts_have_placeholders():
    for name, tmpl in PROMPT_ENG_PROMPTS.items():
        assert "{skills_context}" in tmpl, f"{name} missing {{skills_context}}"


def test_translator_prompt_has_placeholders():
    assert "{target_lang_name}" in TRANSLATE_PROMPT
    assert "{target_lang_code}" in TRANSLATE_PROMPT


def test_polish_renders():
    rendered = POLISH_PROMPTS["polish_default"]
    assert "ТВОЯ ЗАДАЧА:" in rendered


def test_polish_raw_renders():
    rendered = POLISH_PROMPTS["polish_raw"]
    assert "НЕ редактируй содержание" in rendered


def test_summary_prompt_renders():
    assert "•" in SUMMARY_PROMPT
    assert "Задачи:" in SUMMARY_PROMPT


def test_prompt_eng_renders():
    rendered = PROMPT_ENG_PROMPTS["prompt_general"].format(skills_context="<no skills>")
    assert "<no skills>" in rendered


def test_humanizer_renders():
    rendered = HUMANIZER_PROMPTS["humanize_lite"]
    assert "УБИРАЙ ЭТИ ШАБЛОНЫ:" in rendered


def test_translator_renders():
    rendered = TRANSLATE_PROMPT.format(target_lang_name="English", target_lang_code="en")
    assert "English" in rendered
    assert "en" in rendered
