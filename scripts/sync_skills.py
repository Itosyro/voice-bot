"""Clones 8 skill/prompt repositories and loads them into PostgreSQL."""

from __future__ import annotations

import asyncio
import csv as _csv
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete

from src.storage.db import get_session
from src.storage.models import SkillIndex

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "skill_repos"


@dataclass
class RepoConfig:
    name: str
    url: str
    parser: str
    sparse_paths: list[str] = field(default_factory=list)


REPOS = [
    RepoConfig(
        name="anthropics/skills",
        url="https://github.com/anthropics/skills.git",
        parser="skill_md",
    ),
    RepoConfig(
        name="nextlevelbuilder/ui-ux-pro-max-skill",
        url="https://github.com/nextlevelbuilder/ui-ux-pro-max-skill.git",
        parser="uiux_pro_max",
    ),
    RepoConfig(
        name="blader/humanizer",
        url="https://github.com/blader/humanizer.git",
        parser="humanizer_md",
    ),
    RepoConfig(
        name="f/prompts.chat",
        url="https://github.com/f/awesome-chatgpt-prompts.git",
        parser="prompts_csv",
    ),
    RepoConfig(
        name="dair-ai/Prompt-Engineering-Guide",
        url="https://github.com/dair-ai/Prompt-Engineering-Guide.git",
        parser="mdx_files",
        sparse_paths=["pages/"],
    ),
    RepoConfig(
        name="danielrosehill/STT-Basic-Cleanup-System-Prompt",
        url="https://github.com/danielrosehill/STT-Basic-Cleanup-System-Prompt.git",
        parser="stt_md",
    ),
    RepoConfig(
        name="alirezarezvani/claude-skills",
        url="https://github.com/alirezarezvani/claude-skills.git",
        parser="skill_md",
    ),
    RepoConfig(
        name="davila7/claude-code-templates",
        url="https://github.com/davila7/claude-code-templates.git",
        parser="skill_md",
    ),
]


def _clone_or_pull(repo: RepoConfig) -> Path:
    """Clone repo (shallow) or pull if already exists."""
    target = DATA_DIR / repo.name.replace("/", "_")
    if target.exists():
        subprocess.run(
            ["git", "-C", str(target), "pull", "--ff-only"],
            capture_output=True,
            timeout=120,
        )
        return target

    target.mkdir(parents=True, exist_ok=True)
    cmd = ["git", "clone", "--depth=1", repo.url, str(target)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    return target


def _parse_yaml_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm_text = parts[1].strip()
    body = parts[2].strip()
    fm: dict[str, str] = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, body


def _parse_skill_md(repo_path: Path, repo_name: str) -> list[SkillIndex]:
    """Parse repos with SKILL.md files (anthropics/skills, alirezarezvani, davila7)."""
    out: list[SkillIndex] = []
    for skill_md in repo_path.rglob("SKILL.md"):
        content = skill_md.read_text(encoding="utf-8", errors="replace")
        fm, body = _parse_yaml_frontmatter(content)
        name = fm.get("name") or skill_md.parent.name
        description = fm.get("description") or ""
        out.append(
            SkillIndex(
                source_repo=repo_name,
                skill_name=name,
                description=description[:500],
                body=body[:20000],
                file_path=str(skill_md.relative_to(repo_path)),
                tags=fm.get("tags", "").split(",") if fm.get("tags") else None,
            )
        )
    return out


def _parse_humanizer_md(repo_path: Path, repo_name: str) -> list[SkillIndex]:
    """blader/humanizer: one SKILL.md at root."""
    skill_md = repo_path / "SKILL.md"
    if not skill_md.exists():
        # Try .cursorrules or README as fallback
        for fname in ["SKILL.md", ".cursorrules", "README.md"]:
            candidate = repo_path / fname
            if candidate.exists():
                skill_md = candidate
                break
    if not skill_md.exists():
        return []
    content = skill_md.read_text(encoding="utf-8", errors="replace")
    fm, body = _parse_yaml_frontmatter(content)
    return [
        SkillIndex(
            source_repo=repo_name,
            skill_name=fm.get("name", "humanizer"),
            description=fm.get("description", "Remove signs of AI-generated writing"),
            body=body[:20000],
            file_path=skill_md.name,
            tags=["humanize", "anti-ai", "writing"],
        )
    ]


def _parse_prompts_csv(repo_path: Path, repo_name: str) -> list[SkillIndex]:
    """f/prompts.chat: CSV file prompts.csv"""
    csv_path = repo_path / "prompts.csv"
    if not csv_path.exists():
        return []
    out: list[SkillIndex] = []
    with csv_path.open(encoding="utf-8") as f:
        reader = _csv.DictReader(f)
        for row in reader:
            act = (row.get("act") or "").strip()
            prompt = (row.get("prompt") or "").strip()
            if not act or not prompt:
                continue
            out.append(
                SkillIndex(
                    source_repo=repo_name,
                    skill_name=act.lower().replace(" ", "_")[:80],
                    description=f"Act as {act}",
                    body=prompt[:10000],
                    file_path="prompts.csv",
                    tags=["awesome-prompts", "act-as"],
                )
            )
    return out


def _parse_mdx_files(repo_path: Path, repo_name: str) -> list[SkillIndex]:
    """dair-ai/Prompt-Engineering-Guide: pages/**/*.en.mdx"""
    out: list[SkillIndex] = []
    pages_dir = repo_path / "pages"
    if not pages_dir.exists():
        return []
    for mdx in pages_dir.rglob("*.en.mdx"):
        content = mdx.read_text(encoding="utf-8", errors="replace")
        if len(content) > 20_000:
            continue
        name = mdx.stem.replace(".en", "").replace("-", "_")
        first_lines = [
            ln.strip()
            for ln in content.splitlines()[:20]
            if ln.strip() and not ln.startswith("#") and not ln.startswith("import")
        ]
        description = first_lines[0] if first_lines else f"Prompt engineering pattern: {name}"
        out.append(
            SkillIndex(
                source_repo=repo_name,
                skill_name=name,
                description=description[:500],
                body=content,
                file_path=str(mdx.relative_to(repo_path)),
                tags=["prompt-engineering", "dair-ai"],
            )
        )
    return out


def _parse_stt_md(repo_path: Path, repo_name: str) -> list[SkillIndex]:
    """danielrosehill/STT-Basic-Cleanup-System-Prompt: .md files in root."""
    out: list[SkillIndex] = []
    for md in repo_path.glob("*.md"):
        if md.name.lower() == "readme.md":
            continue
        content = md.read_text(encoding="utf-8", errors="replace")
        name = md.stem.replace("-", "_")
        first_para = content.split("\n\n", 1)[0]
        out.append(
            SkillIndex(
                source_repo=repo_name,
                skill_name=f"stt_{name}",
                description=first_para[:300],
                body=content[:10000],
                file_path=md.name,
                tags=["stt", "cleanup", "polish"],
            )
        )
    return out


def _parse_uiux_pro_max(repo_path: Path, repo_name: str) -> list[SkillIndex]:
    """nextlevelbuilder/ui-ux-pro-max-skill: CSV databases."""
    out: list[SkillIndex] = []

    # Look for data directory in several possible locations
    data_dir = None
    for candidate in [
        repo_path / "src" / "ui-ux-pro-max" / "data",
        repo_path / "data",
        repo_path / "src" / "data",
        repo_path,
    ]:
        if candidate.exists() and list(candidate.glob("*.csv")):
            data_dir = candidate
            break

    if data_dir is None:
        # Try to find any CSV files recursively
        csv_files = list(repo_path.rglob("*.csv"))
        if not csv_files:
            return out
        # Use parent of first CSV
        data_dir = csv_files[0].parent

    for csv_path in data_dir.glob("*.csv"):
        category = csv_path.stem
        try:
            with csv_path.open(encoding="utf-8", errors="replace") as f:
                reader = _csv.DictReader(f)
                for i, row in enumerate(reader, 1):
                    norm = {
                        k.strip().lower().replace(" ", "_"): (v or "").strip()
                        for k, v in row.items()
                        if k
                    }
                    primary_name = (
                        norm.get("product_type")
                        or norm.get("style_category")
                        or norm.get("font_pairing")
                        or norm.get("palette_name")
                        or norm.get("guideline")
                        or norm.get("pattern_name")
                        or norm.get("chart_type")
                        or norm.get("name")
                        or f"{category}_{i}"
                    )
                    skill_name = f"uupm_{category}_{primary_name}".lower().replace(" ", "_")[:100]
                    body_parts = [f"{k}: {v}" for k, v in norm.items() if v]
                    body = "\n".join(body_parts)
                    description = " | ".join(body_parts[:3])[:500]

                    out.append(
                        SkillIndex(
                            source_repo=repo_name,
                            skill_name=skill_name,
                            description=description,
                            body=body[:5000],
                            file_path=str(csv_path.relative_to(repo_path)),
                            tags=["ui-ux-pro-max", category],
                        )
                    )
        except Exception:
            continue

    # Also parse stacks subdirectory
    stacks_dir = data_dir / "stacks"
    if stacks_dir.exists():
        for csv_path in stacks_dir.glob("*.csv"):
            framework = csv_path.stem
            try:
                with csv_path.open(encoding="utf-8", errors="replace") as f:
                    reader = _csv.DictReader(f)
                    for i, row in enumerate(reader, 1):
                        norm = {
                            k.strip().lower().replace(" ", "_"): (v or "").strip()
                            for k, v in row.items()
                            if k
                        }
                        guideline_name = norm.get("guideline") or norm.get("name") or f"rule_{i}"
                        skill_name = f"uupm_stack_{framework}_{guideline_name}".lower().replace(
                            " ", "_"
                        )[:100]
                        body_parts = [f"{k}: {v}" for k, v in norm.items() if v]
                        body = "\n".join(body_parts)
                        description = f"{framework} guideline: {guideline_name}"[:500]

                        out.append(
                            SkillIndex(
                                source_repo=repo_name,
                                skill_name=skill_name,
                                description=description,
                                body=body[:5000],
                                file_path=str(csv_path.relative_to(repo_path)),
                                tags=["ui-ux-pro-max", "stack", framework],
                            )
                        )
            except Exception:
                continue

    return out


PARSERS = {
    "skill_md": _parse_skill_md,
    "humanizer_md": _parse_humanizer_md,
    "prompts_csv": _parse_prompts_csv,
    "mdx_files": _parse_mdx_files,
    "stt_md": _parse_stt_md,
    "uiux_pro_max": _parse_uiux_pro_max,
}


async def sync_all() -> None:
    print(f"Cloning {len(REPOS)} repositories...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_skills: list[SkillIndex] = []
    for repo in REPOS:
        print(f"  -> {repo.name}")
        try:
            path = _clone_or_pull(repo)
            parser_fn = PARSERS[repo.parser]
            skills = parser_fn(path, repo.name)
            print(f"    parsed {len(skills)} skills/prompts")
            all_skills.extend(skills)
        except Exception as e:
            print(f"    FAILED: {e}")

    print(f"\nTotal: {len(all_skills)} entries. Writing to Postgres...")
    async with get_session() as session:
        await session.execute(delete(SkillIndex))
        session.add_all(all_skills)
    print("Done")


if __name__ == "__main__":
    asyncio.run(sync_all())
