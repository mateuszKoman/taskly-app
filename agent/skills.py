"""Skill discovery: SKILL.md files with `name` and `description` frontmatter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SKILLS_DIR = Path(__file__).parent / "skills"


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str


class SkillError(ValueError):
    pass


def parse(text: str, source: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillError(f"{source}: missing frontmatter")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        raise SkillError(f"{source}: unterminated frontmatter") from None
    meta = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip().strip('"')
    return meta, "\n".join(lines[end + 1 :]).strip()


def load_skills(directory: Path = SKILLS_DIR) -> dict[str, Skill]:
    skills = {}
    for path in sorted(directory.glob("*/SKILL.md")):
        meta, body = parse(path.read_text(), str(path))
        name, description = meta.get("name", ""), meta.get("description", "")
        if name != path.parent.name:
            raise SkillError(f"{path}: name {name!r} must match its directory")
        if not description or not body:
            raise SkillError(f"{path}: description and body are required")
        skills[name] = Skill(name, description, body)
    return skills


def skill_index(skills: dict[str, Skill]) -> str:
    return "\n".join(f"- `{s.name}`: {s.description}" for s in skills.values())
