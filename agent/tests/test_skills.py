import pytest

from agent.skills import SkillError, load_skills, skill_index


def test_shipped_skills_load_with_descriptions():
    skills = load_skills()
    assert {"triage-changes", "write-backend-tests"} <= set(skills)
    assert all(s.description and s.body for s in skills.values())
    assert "`triage-changes`" in skill_index(skills)


def make(tmp_path, dirname, text):
    path = tmp_path / dirname / "SKILL.md"
    path.parent.mkdir()
    path.write_text(text)


def test_name_must_match_directory(tmp_path):
    make(tmp_path, "real", "---\nname: other\ndescription: d\n---\nbody\n")
    with pytest.raises(SkillError, match="must match"):
        load_skills(tmp_path)


def test_frontmatter_is_required(tmp_path):
    make(tmp_path, "bare", "just a body\n")
    with pytest.raises(SkillError, match="missing frontmatter"):
        load_skills(tmp_path)
