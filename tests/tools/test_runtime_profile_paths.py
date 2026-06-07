"""Profile-scoped runtime path tests for skill tooling."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from tools.runtime_paths import runtime_path


def _skill_content(name: str) -> str:
    return f"""---
name: {name}
description: Scoped skill for profile isolation tests.
---

Use the active Hermes profile only.
"""


def _write_skill(skills_root: Path, name: str) -> None:
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_skill_content(name), encoding="utf-8")


def test_skills_tool_lists_active_profile_skills(monkeypatch, tmp_path):
    root_home = tmp_path / "root"
    profile_home = tmp_path / "profiles" / "myspace-42"
    monkeypatch.setenv("HERMES_HOME", str(root_home))

    _write_skill(root_home / "skills", "root-only")
    _write_skill(profile_home / "skills", "profile-only")

    import tools.skills_tool as skills_tool

    token = set_hermes_home_override(profile_home)
    try:
        assert runtime_path(skills_tool.SKILLS_DIR) == profile_home / "skills"
        payload = json.loads(skills_tool.skills_list())
    finally:
        reset_hermes_home_override(token)

    names = {entry["name"] for entry in payload["skills"]}
    assert "profile-only" in names
    assert "root-only" not in names


def test_skill_manager_create_writes_to_active_profile(monkeypatch, tmp_path):
    root_home = tmp_path / "root"
    profile_home = tmp_path / "profiles" / "myspace-42"
    monkeypatch.setenv("HERMES_HOME", str(root_home))

    import tools.skill_manager_tool as skill_manager

    token = set_hermes_home_override(profile_home)
    try:
        assert runtime_path(skill_manager.SKILLS_DIR) == profile_home / "skills"
        result = skill_manager._create_skill(
            "profile-created", _skill_content("profile-created")
        )
    finally:
        reset_hermes_home_override(token)

    assert result["success"] is True
    assert (profile_home / "skills" / "profile-created" / "SKILL.md").exists()
    assert not (root_home / "skills" / "profile-created" / "SKILL.md").exists()


def test_skills_hub_dirs_and_audit_log_follow_active_profile(monkeypatch, tmp_path):
    root_home = tmp_path / "root"
    profile_home = tmp_path / "profiles" / "myspace-42"
    monkeypatch.setenv("HERMES_HOME", str(root_home))

    import tools.skills_hub as skills_hub

    token = set_hermes_home_override(profile_home)
    try:
        skills_hub.ensure_hub_dirs()
        skills_hub.append_audit_log(
            "INSTALL", "profile-skill", "test", "trusted", "allow"
        )
    finally:
        reset_hermes_home_override(token)

    profile_hub = profile_home / "skills" / ".hub"
    assert (profile_hub / "lock.json").exists()
    assert (profile_hub / "audit.log").read_text(encoding="utf-8")
    assert not (root_home / "skills" / ".hub" / "lock.json").exists()
    assert not (root_home / "skills" / ".hub" / "audit.log").exists()


def test_skills_sync_manifest_and_marker_follow_active_profile(monkeypatch, tmp_path):
    root_home = tmp_path / "root"
    profile_home = tmp_path / "profiles" / "myspace-42"
    monkeypatch.setenv("HERMES_HOME", str(root_home))

    import tools.skills_sync as skills_sync

    token = set_hermes_home_override(profile_home)
    try:
        skills_sync._write_manifest({"profile-skill": "hash"})
        result = skills_sync.set_bundled_skills_opt_out(True)
    finally:
        reset_hermes_home_override(token)

    assert result["ok"] is True
    assert (profile_home / "skills" / ".bundled_manifest").exists()
    assert (profile_home / ".no-bundled-skills").exists()
    assert not (root_home / "skills" / ".bundled_manifest").exists()
    assert not (root_home / ".no-bundled-skills").exists()


def test_skill_creation_is_context_local_between_threads(monkeypatch, tmp_path):
    root_home = tmp_path / "root"
    profile_a = tmp_path / "profiles" / "myspace-a"
    profile_b = tmp_path / "profiles" / "myspace-b"
    monkeypatch.setenv("HERMES_HOME", str(root_home))

    import tools.skill_manager_tool as skill_manager

    def create(profile_home: Path, name: str) -> bool:
        token = set_hermes_home_override(profile_home)
        try:
            result = skill_manager._create_skill(name, _skill_content(name))
            return bool(result.get("success"))
        finally:
            reset_hermes_home_override(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda args: create(*args),
                [(profile_a, "thread-a"), (profile_b, "thread-b")],
            )
        )

    assert results == [True, True]
    assert (profile_a / "skills" / "thread-a" / "SKILL.md").exists()
    assert (profile_b / "skills" / "thread-b" / "SKILL.md").exists()
    assert not (profile_a / "skills" / "thread-b" / "SKILL.md").exists()
    assert not (profile_b / "skills" / "thread-a" / "SKILL.md").exists()
    assert not (root_home / "skills" / "thread-a" / "SKILL.md").exists()
    assert not (root_home / "skills" / "thread-b" / "SKILL.md").exists()
