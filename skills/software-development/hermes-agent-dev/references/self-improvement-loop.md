# Hermes Self-Improvement Loop Reference

## Purpose

This reference captures invariants for modifying Hermes Agent's self-learning loop. It is linked from `agent/background_review.py` and the `hermes-agent-dev` skill so future source-code upgrades have a concrete checklist.

## Memory vs Skill Decisions

Save to memory when the fact is durable, compact, and likely to reduce future user steering:
- user preferences
- stable environment facts
- project conventions
- recurring corrections

Save to a skill when the knowledge is procedural:
- command sequences
- debugging paths
- verification recipes
- pitfalls and recovery steps
- reusable workflows that took multiple tool calls to discover

Do not save:
- task progress
- PR/issue numbers
- commit SHAs
- raw logs
- stale artifact IDs
- broad negative claims that will become false

## Background Review Invariants

- Background review should suggest memories or skill changes only when evidence is strong.
- Bundled and hub skills are source artifacts; do not silently rewrite them as if they were disposable notes.
- User-local agent-created skills can be curated, but destructive lifecycle actions need backups and conservative thresholds.
- Prefer additive patches over rewrites when improving a skill after a task.
- Skill updates should improve future execution, not record that a one-off task happened.

## Prompt Cache Invariants

- Keep system prompt construction stable within a session.
- Add named guidance constants rather than scattering prompt strings through runtime code.
- Inject guidance conditionally from a single clear gate when possible.
- Add tests that prove both inclusion and exclusion behavior for gated guidance.

## Review Checklist for Self-Learning Changes

- [ ] Does the change preserve the distinction between memory facts and procedural skills?
- [ ] Does it avoid turning task logs into durable memory?
- [ ] Does it protect user/local/profile state from accidental source edits?
- [ ] Does it preserve prompt cache and role alternation assumptions?
- [ ] Does it include regression coverage for the behavior being changed?
- [ ] Does it update user docs or skills if future agents need the workflow?
