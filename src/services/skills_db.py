from __future__ import annotations

from typing import ClassVar

from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.models import SkillIndex


class SkillsDB:
    """In-memory cache of skills from Postgres + BM25 search."""

    def __init__(self, skills: list[SkillIndex]) -> None:
        self.skills = skills
        self._tokens = [
            self._tokenize(
                s.skill_name + " " + s.description + " " + (s.body[:500] if s.body else "")
            )
            for s in skills
        ]
        self.bm25 = BM25Okapi(self._tokens) if self._tokens else None

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return text.lower().split()

    @classmethod
    async def load_from_db(cls, session: AsyncSession) -> SkillsDB:
        result = await session.execute(select(SkillIndex))
        skills = list(result.scalars().all())
        return cls(skills)

    PRIORITY_BY_STYLE: ClassVar[dict[str, set[str]]] = {
        "designer": {
            "frontend-design",
            "theme-factory",
            "canvas-design",
            "web-artifacts-builder",
            "senior-product-designer",
            "senior-ux-designer",
            "senior-design-engineer",
            "design-taste-frontend",
            "design-taste-frontend-v1",
            "gpt-taste",
            "high-end-visual-design",
            "minimalist-ui",
            "industrial-brutalist-ui",
            "stitch-design-taste",
            "brandkit",
            "redesign-existing-projects",
            "impeccable",
        },
        "coder": {
            "web-artifacts-builder",
            "claude-api",
            "mcp-builder",
            "webapp-testing",
            "senior-prompt-engineer",
            "senior-frontend-engineer",
            "senior-backend-engineer",
            "senior-fullstack-engineer",
            "code-architect",
            "impeccable",
            "image-to-code",
        },
        "coder_strict": {
            "web-artifacts-builder",
            "claude-api",
            "mcp-builder",
            "webapp-testing",
            "senior-prompt-engineer",
            "senior-fullstack-engineer",
            "code-architect",
            "senior-platform-engineer",
            "senior-security-engineer",
            "senior-devops-engineer",
            "impeccable",
        },
        "humanize_lite": {"humanizer"},
        "humanize_strong": {"humanizer"},
        "polish_default": {"stt_basic_cleanup", "stt_complete_system_prompt"},
        "polish_creative": {"stt_basic_cleanup"},
    }

    UUPM_PREFIXES_BY_STYLE: ClassVar[dict[str, tuple[str, ...]]] = {
        "designer": (
            "uupm_products_",
            "uupm_styles_",
            "uupm_colors_",
            "uupm_typography_",
            "uupm_landing_",
            "uupm_ux-guidelines_",
        ),
        "coder": ("uupm_products_", "uupm_stack_"),
        "coder_strict": ("uupm_products_", "uupm_stack_"),
    }

    def search(
        self,
        query: str,
        sub_style: str | None = None,
        top_k: int = 3,
    ) -> list[SkillIndex]:
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(self._tokenize(query))
        priority = self.PRIORITY_BY_STYLE.get(sub_style or "", set())
        uupm_prefixes = self.UUPM_PREFIXES_BY_STYLE.get(sub_style or "", ())

        def _bonus(skill: SkillIndex) -> float:
            b = 0.0
            if skill.skill_name in priority:
                b += 1.5
            if uupm_prefixes and skill.skill_name.startswith(uupm_prefixes):
                b += 0.8
            if skill.source_repo == "anthropics/skills":
                b += 0.3
            if skill.source_repo == "nextlevelbuilder/ui-ux-pro-max-skill" and uupm_prefixes:
                b += 0.5
            return b

        ranked = sorted(
            zip(scores, self.skills, strict=False),
            key=lambda x: x[0] + _bonus(x[1]),
            reverse=True,
        )
        return [s for _score, s in ranked[:top_k] if _score > 0.0 or s.skill_name in priority]

    @staticmethod
    def format_for_prompt(skills: list[SkillIndex], max_total_chars: int = 6000) -> str:
        if not skills:
            return ""
        per_skill = max_total_chars // len(skills)
        parts = ["# Контекст экспертизы (из проверенных skill-репозиториев)\n"]
        for s in skills:
            body = s.body[:per_skill]
            parts.append(
                f"## {s.skill_name} (источник: {s.source_repo})\n{s.description}\n\n{body}\n"
            )
        return "\n".join(parts)
