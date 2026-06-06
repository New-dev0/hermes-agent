---
name: hermes-agent-dev
description: "Use when modifying Hermes Agent internals or exploring its source code, especially self-learning, prompts, memory, skills, curator, or background review behavior."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes-agent, development, self-learning, prompt-builder, memory, skills, curator]
    related_skills: [hermes-agent, hermes-agent-skill-authoring, systematic-debugging, test-driven-development, requesting-code-review]
---

# Hermes Agent Development and Self-Upgrade Workflow

## Overview

Hermes Agent is self-improving, but changes to that loop are load-bearing: prompt guidance, memory, skills, curator, background review, tool schemas, docs, and tests can all interact. Use this skill as the source-code navigation map and safety checklist for upgrading Hermes itself.

The goal is to make small, verified, reversible improvements while preserving the user's existing local changes and keeping runtime profile state separate from in-repo source changes.

## When to Use

Use this skill when:
- Modifying Hermes Agent source code.
- Exploring the Hermes Agent codebase to find improvement opportunities.
- Changing identity, system prompt behavior, memory behavior, skill behavior, curator, background review, delegation, or self-learning behavior.
- Investigating how Hermes loads skills, stores memory, injects context, or decides what to remember.
- A task asks for "upgrade yourself", "improve Hermes", "self-learning", or "source-code exploration".

Don't use this skill for:
- Ordinary app-code changes outside Hermes Agent.
- Pure user configuration tasks; use `hermes-agent` instead.
- Writing one-off local profile skills; use `hermes-agent-skill-authoring` only if the skill should ship in the repo.

## Core Source Map

| Area | Primary files |
| --- | --- |
| Agent loop | `run_agent.py`, `model_tools.py` |
| System prompt assembly | `agent/prompt_builder.py`, `agent/system_prompt.py` |
| Memory tool | `tools/memory_tool.py`, `agent/memory_manager.py`, `agent/memory_provider.py` |
| Skills read/write | `tools/skills_tool.py`, `tools/skill_manager_tool.py`, `tools/skill_usage.py` |
| Curator | `agent/curator.py`, `agent/curator_backup.py`, `tools/skill_usage.py` |
| Background review | `agent/background_review.py` |
| CLI commands | `cli.py`, `hermes_cli/commands.py`, `hermes_cli/main.py` |
| Tool registration | `tools/registry.py`, `toolsets.py`, `model_tools.py` |
| Gateway | `gateway/run.py`, `gateway/session.py`, `gateway/platforms/` |
| Tests | `tests/agent/`, `tests/tools/`, `tests/run_agent/`, `tests/hermes_cli/` |
| User docs | `website/docs/user-guide/features/skills.md`, `website/docs/user-guide/features/memory.md`, `website/docs/user-guide/features/curator.md` |
| Bundled skills | `skills/<category>/<name>/SKILL.md` |

## Safe Self-Upgrade Workflow

1. Inspect repo state first.
   - Run `git status --short --branch`.
   - Identify pre-existing local modifications.
   - Avoid touching modified files unless the task requires them.
   - Never use reset/restore/checkout to clean up user changes unless the user explicitly authorized those exact files.

2. Explore before editing.
   - Search for relevant symbols with `search_files`.
   - Read the smallest relevant files with line numbers.
   - Prefer small, isolated improvements in unmodified files.
   - If multiple candidates exist, choose the one with the clearest test and least blast radius.

3. Trace the behavior path.
   - Prompt change: constant or builder in `agent/prompt_builder.py` -> injection gate in `agent/system_prompt.py` -> focused tests.
   - Tool change: `tools/<tool>.py` -> registry schema/handler -> `model_tools.py` dispatch if needed -> tests under `tests/tools/`.
   - Memory change: tool/store/provider path -> drift/concurrency/security implications -> tests under `tests/tools/` and `tests/agent/`.
   - Skill change: `tools/skills_tool.py` or `tools/skill_manager_tool.py` -> validator/setup behavior -> tests and bundled skill docs if user-facing.
   - Curator/background review change: prompt/review loop -> skill usage telemetry -> tests and docs.

4. Prefer TDD for behavior changes.
   - Write or tighten a focused regression test first.
   - Run the specific test and confirm it fails for the expected reason.
   - Implement the smallest code change.
   - Re-run the specific test, then the surrounding test file or class.

5. Keep source and profile state separate.
   - In-repo bundled skills live under `skills/` and should be written with file tools.
   - User-local skills live under `~/.hermes/skills/` and are managed with `skill_manage`.
   - Do not edit another profile's skills/plugins/memory unless the user explicitly requested it.
   - New in-repo skills are usually not visible to the current session's skill loader until a fresh session; validate by file contents and tests instead.

6. Update docs or skills when behavior is reusable.
   - User-facing behavior changes need website docs when applicable.
   - Agent-operational workflows belong in a skill.
   - Keep stale references resolvable; if code/docs mention a skill name, ensure it exists or update the reference.

## Prompt and Self-Learning Invariants

- Do not break prompt caching casually. Tool lists, context files, and system prompt content should not change mid-conversation unless the architecture already supports it.
- Keep message role alternation intact; never create two assistant or two user messages in a row in stored conversation sequences.
- Write memories as compact declarative facts, not imperative instructions or task logs.
- Put reusable procedures in skills, not memory.
- If a loaded skill is stale or incomplete, patch the skill immediately after verifying the new workflow.
- Use `get_hermes_home()` for profile-aware runtime paths; never hardcode `~/.hermes` for runtime state.
- Config belongs in `config.yaml`; secrets belong in `.env`.

## Common Pitfalls

1. Editing user-local runtime state when intending to change source.
   - `skill_manage(action='create')` writes to `~/.hermes/skills/`, not the repo. For bundled skills, write under `skills/<category>/<name>/SKILL.md`.

2. Touching dirty files unnecessarily.
   - The user's local modifications may be unrelated. Work around them when possible, and report exactly which files you changed.

3. Updating prompt text without tests.
   - Prompt guidance can silently disappear through gating or refactors. Add focused prompt-builder/system-prompt tests for prompt behavior changes.

4. Fixing a memory/data-loss bug without a regression test.
   - Memory bugs often involve drift, concurrency, or truncation. Reproduce the failure with a focused test before changing production code.

5. Confusing high-level docs with operational agent guidance.
   - User docs explain features; skills encode how the agent should execute repeatable workflows. Update the right artifact.

6. Running broad validation too early.
   - Respect user preference: run targeted tests during intermediate work; run broader validation after implementation is complete.

## Verification Checklist

- [ ] `git status --short --branch` reviewed before and after changes.
- [ ] Pre-existing local modifications preserved.
- [ ] Change is small and scoped to the intended behavior.
- [ ] A focused regression test failed before implementation when changing behavior.
- [ ] Focused tests pass after implementation.
- [ ] Surrounding test class/file passes when practical.
- [ ] Docs/skills updated if the workflow or user-facing behavior changed.
- [ ] Final response lists changed files, tests run, and any pre-existing dirty files left untouched.

## One-Shot Recipe: Small Source Self-Upgrade

```bash
git status --short --branch
# inspect relevant files with read_file/search_files
# write or tighten one focused test
venv/bin/python -m pytest tests/path/test_file.py::TestClass::test_case -q
# implement minimal code
venv/bin/python -m pytest tests/path/test_file.py::TestClass::test_case -q
venv/bin/python -m pytest tests/path/test_file.py -q
git diff --stat
git diff -- path/to/changed_file.py tests/path/test_file.py
```

Use `python3` only if the repo venv is unavailable. In Hermes install checkouts, `venv/bin/python` is usually the correct interpreter.
