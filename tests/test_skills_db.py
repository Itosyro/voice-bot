from src.services.skills_db import SkillsDB
from src.storage.models import SkillIndex


def _make_skill(name: str, description: str, body: str, repo: str = "test/repo") -> SkillIndex:
    return SkillIndex(
        id=0,
        source_repo=repo,
        skill_name=name,
        description=description,
        body=body,
        file_path="test.md",
        tags=None,
    )


def test_search_returns_results():
    skills = [
        _make_skill("frontend-design", "Design UI components", "Build beautiful UIs"),
        _make_skill("backend-api", "Build REST APIs", "Develop scalable backends"),
        _make_skill("humanizer", "Remove AI markers", "Make text sound human"),
    ]
    db = SkillsDB(skills)
    results = db.search("design UI components")
    assert len(results) > 0
    assert any("design" in s.skill_name for s in results)


def test_search_empty_db():
    db = SkillsDB([])
    results = db.search("anything")
    assert results == []


def test_format_for_prompt():
    skills = [
        _make_skill("my-skill", "A great skill", "Detailed body content here"),
    ]
    formatted = SkillsDB.format_for_prompt(skills)
    assert "my-skill" in formatted
    assert "A great skill" in formatted


def test_format_empty():
    assert SkillsDB.format_for_prompt([]) == ""


def test_priority_bonus():
    skills = [
        _make_skill("humanizer", "Remove AI markers", "Make text sound human"),
        _make_skill("something-else", "random skill", "random body content here"),
    ]
    db = SkillsDB(skills)
    results = db.search("some text", sub_style="humanize_lite")
    assert len(results) > 0
    assert results[0].skill_name == "humanizer"
