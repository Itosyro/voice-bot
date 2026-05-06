from unittest.mock import AsyncMock, patch

import pytest

from src.services.skills_db import SkillsDB
from src.storage.models import SkillIndex


@pytest.fixture
def mock_groq():
    with patch("src.services.llm.AsyncGroq") as mock:
        client = AsyncMock()
        mock.return_value = client

        choice = AsyncMock()
        choice.message.content = "Mocked response text"

        response = AsyncMock()
        response.choices = [choice]

        client.chat.completions.create = AsyncMock(return_value=response)
        yield client


@pytest.fixture
def skills_db():
    skills = [
        SkillIndex(
            id=1,
            source_repo="test/repo",
            skill_name="test-skill",
            description="A test skill",
            body="Test body content",
            file_path="test.md",
            tags=None,
        )
    ]
    return SkillsDB(skills)


async def test_run_polish(mock_groq):
    from src.services.polish import run_polish

    result = await run_polish("test transcript", sub_style="polish_default")
    assert result.text == "Mocked response text"
    assert result.llm_ms >= 0


async def test_run_prompt_eng(mock_groq, skills_db):
    from src.services.prompt_eng import run_prompt_eng

    result = await run_prompt_eng(
        "build a landing page", sub_style="prompt_general", skills_db=skills_db
    )
    assert result.text == "Mocked response text"
    assert result.llm_ms >= 0


async def test_run_humanizer(mock_groq):
    from src.services.humanizer import run_humanizer

    result = await run_humanizer("AI generated text to humanize")
    assert result.text == "Mocked response text"


async def test_run_translator(mock_groq):
    from src.services.translator import run_translator

    result = await run_translator("Hello world", target_lang="ru")
    assert result.text == "Mocked response text"
    assert result.target_lang == "ru"
