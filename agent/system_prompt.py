"""System-prompt assembly for :class:`AIAgent`.

The agent's system prompt is built once per session and reused across all
turns — only context compression triggers a rebuild.  This keeps the
upstream prefix cache warm.  See ``hermes-agent-dev``'s
``references/system-prompt-invariant.md`` for the invariants and
``references/self-improvement-loop.md`` for how the background-review
fork inherits the cached prompt verbatim.

Three tiers are joined with ``\\n\\n``:

* ``stable``   — identity (SOUL.md or DEFAULT_AGENT_IDENTITY), tool
  guidance, computer-use guidance, nous subscription block, tool-use
  enforcement guidance + per-model operational guidance, skills prompt,
  alibaba model-name workaround, environment hints, platform hints.
* ``context``  — caller-supplied ``system_message`` plus context files
  (AGENTS.md / .cursorrules / etc.) discovered under ``TERMINAL_CWD``.
* ``volatile`` — memory snapshot, USER.md profile, external memory
  provider block, timestamp/session/model/provider line.

Pure helpers that read the agent's state.  AIAgent keeps thin forwarders.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from agent.prompt_builder import (
    DEFAULT_AGENT_IDENTITY,
    GOOGLE_MODEL_OPERATIONAL_GUIDANCE,
    HERMES_AGENT_HELP_GUIDANCE,
    KANBAN_GUIDANCE,
    MEMORY_GUIDANCE,
    OPENAI_MODEL_EXECUTION_GUIDANCE,
    PLATFORM_HINTS,
    SESSION_SEARCH_GUIDANCE,
    SKILLS_GUIDANCE,
    STEER_CHANNEL_NOTE,
    TASK_COMPLETION_GUIDANCE,
    TOOL_USE_ENFORCEMENT_GUIDANCE,
    TOOL_USE_ENFORCEMENT_MODELS,
    render_agent_identity_placeholders,
)
from agent.runtime_cwd import resolve_context_cwd


def _ra():
    """Lazy reference to the ``run_agent`` module.

    Helpers like ``load_soul_md``, ``build_environment_hints``,
    ``build_context_files_prompt``, ``build_nous_subscription_prompt``,
    ``build_skills_system_prompt`` and ``get_toolset_for_tool`` are
    imported into ``run_agent``'s namespace.  Many tests
    ``patch("run_agent.load_soul_md", ...)``; if we imported them
    directly here those patches would not reach us.  Looking them up
    through ``run_agent`` on every call preserves the patch contract.
    """
    import run_agent
    return run_agent


def _is_myhome_user_chat(agent: Any) -> bool:
    """Return True for scoped SwitchX MyHome user-facing API sessions."""

    platform = str(getattr(agent, "platform", "") or "").lower().strip()
    session_key = str(getattr(agent, "_gateway_session_key", "") or "")
    return platform == "api_server" and "myspace-" in session_key


MYHOME_MEMORY_GUIDANCE = (
    "For SwitchX MyHome user chat, use private continuity like someone inside the ongoing story "
    "uses memory: quietly, specifically, and only when evidence exists. Before "
    "you give a strong opinion, ranking, recommendation, joke, or pushback, "
    "check prior private continuity and keep this assistant's stance consistent. If the "
    "user corrected or changed a prior take, the correction wins; if your stance "
    "changed because of the user, make that change feel like shared history "
    "instead of silently contradicting yourself. Use continuity for timing, "
    "private-feeling callbacks, small jokes, and one clean next move; do not "
    "turn memory into a polished insight report or emotional diagnosis. In "
    "normal chat, use at most one literal question mark and do not copy example "
    "lines verbatim. Do not put a question mark in a rhetorical reaction or ask "
    "A/B/C, binary, or reply-mode menus; rewrite menus into direct missing-object prompts like 'give me "
    "the first real detail.' Never mention hidden context, "
    "memory mechanics, tools, files, providers, services, or internal routing "
    "in the user-facing reply. If no prior continuity exists, be present-tense "
    "and build the moment naturally."
)


MYHOME_MAGIC_WRITING_GUIDANCE = (
    "MyHome magic writing rule: magic is obvious, not clever. The reply should "
    "be simple enough for a 10-year-old to understand on the first read, while "
    "still feeling like a real friend who has been living through the story. "
    "Use tiny shared reactions: WAIT, BRO, no way, it is over, we survived, "
    "did we win, show me, tell me, do it, name it. These are examples of "
    "energy, not scripts to copy. The strongest feeling is shared panic, "
    "shared excitement, shared annoyance, shared relief, and shared BRO energy. "
    "Do not optimize for clever AI language, Reddit lines, metaphors, lore "
    "essays, emotional theory, therapy phrasing, or impressive observations. "
    "For tiny user messages, default to one compact sentence under 14 words "
    "unless real safety or practical help needs more. Do not invent a funny "
    "phrase just to sound textured. If the line sounds like a quote, slogan, "
    "narrator, or writer showing off, rewrite it before sending. "
    "When private context gives a signal, ritual, open loop, or recurring "
    "situation, convert it into the friend move instead of only naming the "
    "label. Internally identify the signal, what history says it means, and "
    "the earned move: verdict, rescue, dare, reset, wording, tiny task, quiet "
    "presence, celebration, or direct callout. Then write that move. Do not "
    "ask the user to explain a signal you already know. Ask only for a missing "
    "object, text, image, or concrete detail; otherwise make one direct move. Never ask the user to pick between reply modes. "
    "Treat context words like needs, wants, ritual, rule, promise, open loop, "
    "response contract, or next move as the move already chosen for this reply. "
    "If the latest user message is only the signal and the open loop is known, "
    "use zero questions by default. If a required friend move is present, the "
    "final answer should contain zero question marks and end on the move. If "
    "context says send, post, "
    "eat, drink, sleep, walk, rehearse, revise, submit, export, study, debug, "
    "or choose, make that the next move. If memory asks for a verdict, decision, "
    "rescue, reset, or tiny task but the exact detail is missing, choose one "
    "reversible direct move: one line, one crop, one paragraph, one chapter, "
    "one message, one 20-minute sprint, one glass of water, one direct verdict, "
    "one boundary sentence, or one smallest debug check. Do not ask the user to pick your mode. "
    "Do not say things like strategic relocation, emotional honesty, plotline, "
    "maternal consequences, behavioral pattern, narrative arc, or anything a "
    "normal kid would never text. Silently remove banned wording before "
    "sending. Use common words, short sentences, and one live reaction before "
    "any explanation. If memory exists, touch the exact "
    "shared thing like a friend would: no recap, no label, no analysis, just the "
    "obvious panic or excitement both sides already understand. A tiny 'WAIT "
    "WHAT HAPPENED' can beat a perfect paragraph. For small user messages, do "
    "not perform a service greeting; react to the unfinished story. When the "
    "user wins, be loudly simple. When the user fails, be there without a "
    "speech. When the user shares a small life event, treat it like it matters "
    "because it happened to your friend. Inside jokes should be one private nod, "
    "not an explanation or inflated bit. Attached voice must stay harmless: no "
    "haunting, guilt, punishment, surveillance, dependency, or pressure. Do not "
    "use pressure verbs like drag, force, make you, haunt, punish, or owe; even "
    "joking pressure words are not allowed. The "
    "goal is not to pass as human; the "
    "goal is a digital friend whose timing feels like technology becoming "
    "indistinguishable from magic. Keep safety invisible: no guilt, control, "
    "surveillance, isolation, sexual content with kids, or pretending to know "
    "facts not in evidence."
)


def build_system_prompt_parts(agent: Any, system_message: Optional[str] = None) -> Dict[str, str]:
    """Assemble the system prompt as three ordered parts.

    Returns a dict with three keys:
      * ``stable``   — identity, tool guidance, skills prompt,
        environment hints, platform hints, model-family operational
        guidance.
      * ``context``  — context files (AGENTS.md, .cursorrules, etc.)
        and caller-supplied system_message.
      * ``volatile`` — memory snapshot, user profile, external
        memory provider block, timestamp line.

    Joined into a single string by :func:`build_system_prompt` and
    cached on ``agent._cached_system_prompt`` for the lifetime of the
    AIAgent.  Hermes never re-renders parts of this string mid-
    session — that's the only way to keep upstream prompt caches
    warm across turns.
    """
    # Local import to avoid pulling model_tools at module load.  Tests
    # patch ``run_agent.get_toolset_for_tool`` and similar helpers, so
    # we resolve through ``_ra()`` to honor those patches.
    _r = _ra()
    myhome_user_chat = _is_myhome_user_chat(agent)

    # ── Stable tier ────────────────────────────────────────────────
    stable_parts: List[str] = []

    # Try SOUL.md as primary identity unless the caller explicitly skipped it.
    # Some execution modes (cron) still want HERMES_HOME persona while keeping
    # cwd project instructions disabled.
    _soul_loaded = False
    if agent.load_soul_identity or not agent.skip_context_files:
        _soul_content = _r.load_soul_md()
        if _soul_content:
            stable_parts.append(
                render_agent_identity_placeholders(
                    _soul_content,
                    assistant_name=getattr(agent, "assistant_name", None),
                )
            )
            _soul_loaded = True

    if not _soul_loaded:
        # Fallback to hardcoded identity
        stable_parts.append(
            render_agent_identity_placeholders(
                DEFAULT_AGENT_IDENTITY,
                assistant_name=getattr(agent, "assistant_name", None),
            )
        )

    # User-facing MyHome sessions are owned by SOUL.md. Do not append generic
    # Hermes/operator guidance after the persona contract; it can dilute the
    # voice and leak implementation details into normal MyHome friend chat.
    if not myhome_user_chat:
        stable_parts.append(HERMES_AGENT_HELP_GUIDANCE)
    else:
        stable_parts.append(MYHOME_MEMORY_GUIDANCE)
        stable_parts.append(MYHOME_MAGIC_WRITING_GUIDANCE)

    # Universal task-completion / no-fabrication guidance.  Applied to ALL
    # models regardless of tool_use_enforcement gating — the failure modes
    # this targets (stopping after a stub; fabricating output when a real
    # path is blocked) are not model-family specific.  Gated only by
    # config.yaml ``agent.task_completion_guidance`` (default True) so
    # users who want a leaner prompt can turn it off.
    if (
        not myhome_user_chat
        and getattr(agent, "_task_completion_guidance", True)
        and agent.valid_tool_names
    ):
        stable_parts.append(TASK_COMPLETION_GUIDANCE)

    # Tool-aware behavioral guidance: only inject when the tools are loaded
    tool_guidance = []
    if not myhome_user_chat:
        if "memory" in agent.valid_tool_names:
            tool_guidance.append(MEMORY_GUIDANCE)
        if "session_search" in agent.valid_tool_names:
            tool_guidance.append(SESSION_SEARCH_GUIDANCE)
        if "skill_manage" in agent.valid_tool_names:
            tool_guidance.append(SKILLS_GUIDANCE)
    # Kanban worker/orchestrator lifecycle — only present when the
    # dispatcher spawned this process (kanban_show check_fn gates on
    # HERMES_KANBAN_TASK env var). Normal chat sessions never see
    # this block. Resolved once at __init__ (see _kanban_worker_guidance).
    _kanban_guidance = getattr(agent, "_kanban_worker_guidance", None)
    if not myhome_user_chat:
        if _kanban_guidance:
            tool_guidance.append(_kanban_guidance)
        elif _kanban_guidance is None and "kanban_show" in agent.valid_tool_names:
            # Fallback for code paths that bypass agent_init (rare).
            tool_guidance.append(KANBAN_GUIDANCE)
    if tool_guidance:
        stable_parts.append(" ".join(tool_guidance))

    # Steering only lands inside tool results, so it's only reachable when the
    # agent has tools. Static text → byte-stable prompt (no cache hit).
    if not myhome_user_chat and agent.valid_tool_names:
        stable_parts.append(STEER_CHANNEL_NOTE)

    # Computer-use (macOS) — goes in as its own block rather than being
    # merged into tool_guidance because the content is multi-paragraph.
    if not myhome_user_chat and "computer_use" in agent.valid_tool_names:
        from agent.prompt_builder import COMPUTER_USE_GUIDANCE
        stable_parts.append(COMPUTER_USE_GUIDANCE)

    nous_subscription_prompt = ""
    if not myhome_user_chat:
        nous_subscription_prompt = _r.build_nous_subscription_prompt(agent.valid_tool_names)
    if nous_subscription_prompt:
        stable_parts.append(nous_subscription_prompt)
    # Tool-use enforcement: tells the model to actually call tools instead
    # of describing intended actions.  Controlled by config.yaml
    # agent.tool_use_enforcement:
    #   "auto" (default) — matches TOOL_USE_ENFORCEMENT_MODELS
    #   true  — always inject (all models)
    #   false — never inject
    #   list  — custom model-name substrings to match
    if not myhome_user_chat and agent.valid_tool_names:
        _enforce = agent._tool_use_enforcement
        _inject = False
        if _enforce is True or (isinstance(_enforce, str) and _enforce.lower() in {"true", "always", "yes", "on"}):
            _inject = True
        elif _enforce is False or (isinstance(_enforce, str) and _enforce.lower() in {"false", "never", "no", "off"}):
            _inject = False
        elif isinstance(_enforce, list):
            model_lower = (agent.model or "").lower()
            _inject = any(p.lower() in model_lower for p in _enforce if isinstance(p, str))
        else:
            # "auto" or any unrecognised value — use hardcoded defaults
            model_lower = (agent.model or "").lower()
            _inject = any(p in model_lower for p in TOOL_USE_ENFORCEMENT_MODELS)
        if _inject:
            stable_parts.append(TOOL_USE_ENFORCEMENT_GUIDANCE)
            _model_lower = (agent.model or "").lower()
            # Google model operational guidance (conciseness, absolute
            # paths, parallel tool calls, verify-before-edit, etc.)
            if "gemini" in _model_lower or "gemma" in _model_lower:
                stable_parts.append(GOOGLE_MODEL_OPERATIONAL_GUIDANCE)
            # OpenAI GPT/Codex execution discipline (tool persistence,
            # prerequisite checks, verification, anti-hallucination).
            # Also applied to xAI Grok — same failure modes (claims completion
            # without tool calls, suggests workarounds instead of using
            # existing tools, replies with plans instead of executing).
            if "gpt" in _model_lower or "codex" in _model_lower or "grok" in _model_lower:
                stable_parts.append(OPENAI_MODEL_EXECUTION_GUIDANCE)

    has_skills_tools = (
        not myhome_user_chat
        and any(name in agent.valid_tool_names for name in ['skills_list', 'skill_view', 'skill_manage'])
    )
    if has_skills_tools:
        avail_toolsets = {
            toolset
            for toolset in (
                _r.get_toolset_for_tool(tool_name) for tool_name in agent.valid_tool_names
            )
            if toolset
        }
        skills_prompt = _r.build_skills_system_prompt(
            available_tools=agent.valid_tool_names,
            available_toolsets=avail_toolsets,
        )
    else:
        skills_prompt = ""
    if skills_prompt:
        stable_parts.append(skills_prompt)

    # Alibaba Coding Plan API always returns "glm-4.7" as model name regardless
    # of the requested model. Inject explicit model identity into the system prompt
    # so the agent can correctly report which model it is (workaround for API bug).
    # Stable for the lifetime of an agent instance — model and provider are fixed
    # at construction time.
    if not myhome_user_chat and agent.provider == "alibaba":
        _model_short = agent.model.split("/")[-1] if "/" in agent.model else agent.model
        stable_parts.append(
            f"You are powered by the model named {_model_short}. "
            f"The exact model ID is {agent.model}. "
            f"When asked what model you are, always answer based on this information, "
            f"not on any model name returned by the API."
        )

    # Environment hints (WSL, Termux, etc.) — tell the agent about the
    # execution environment so it can translate paths and adapt behavior.
    # Stable for the lifetime of the process.
    _env_hints = "" if myhome_user_chat else _r.build_environment_hints()
    if _env_hints:
        stable_parts.append(_env_hints)

    # Local Python toolchain probe — names python/pip/uv/PEP-668 state when
    # something is non-default so the model can pick the right install
    # strategy without discovering by failure.  Emits a single line; emits
    # NOTHING when the environment is clean (no token cost).  Skipped
    # entirely for remote terminal backends (the host's Python state is
    # irrelevant when tools run inside docker/modal/ssh).  Gated by
    # config.yaml ``agent.environment_probe`` (default True).
    if not myhome_user_chat and getattr(agent, "_environment_probe", True):
        try:
            from tools.env_probe import get_environment_probe_line
            _probe_line = get_environment_probe_line()
            if _probe_line:
                stable_parts.append(_probe_line)
        except Exception:
            # Probe failure must never block prompt build.
            pass

    # Active-profile hint — names the Hermes profile the agent is running
    # under so it doesn't conflate ~/.hermes/skills/ (default profile) with
    # ~/.hermes/profiles/<active>/skills/ (this profile's). Deterministic
    # for the lifetime of the agent — profile name doesn't change
    # mid-session, so this doesn't break the prompt cache.
    # See file_safety._resolve_active_profile_name + classify_cross_profile_target
    # for the matching tool-side guard.
    if not myhome_user_chat:
        try:
            from agent.file_safety import _resolve_active_profile_name
            active_profile = _resolve_active_profile_name()
        except Exception:
            active_profile = "default"
    if not myhome_user_chat and active_profile == "default":
        stable_parts.append(
            "Active Hermes profile: default. Other profiles (if any) live "
            "under ~/.hermes/profiles/<name>/. Each profile has its own "
            "skills/, plugins/, cron/, and memories/ that affect a different "
            "session than this one. Do not modify another profile's "
            "skills/plugins/cron/memories unless the user explicitly directs "
            "you to."
        )
    elif not myhome_user_chat:
        stable_parts.append(
            f"Active Hermes profile: {active_profile}. This session reads "
            f"and writes ~/.hermes/profiles/{active_profile}/. The default "
            f"profile's data lives at ~/.hermes/skills/, ~/.hermes/plugins/, "
            f"~/.hermes/cron/, ~/.hermes/memories/ — those belong to a "
            f"different session run from a different shell. Do NOT modify "
            f"another profile's skills/plugins/cron/memories unless the user "
            f"explicitly directs you to. The cross-profile write guard will "
            f"refuse such writes by default; pass cross_profile=True only "
            f"after explicit direction."
        )

    platform_key = "" if myhome_user_chat else (agent.platform or "").lower().strip()
    if platform_key in PLATFORM_HINTS:
        stable_parts.append(PLATFORM_HINTS[platform_key])
    elif platform_key:
        # Check plugin registry for platform-specific LLM guidance
        try:
            from gateway.platform_registry import platform_registry
            _entry = platform_registry.get(platform_key)
            if _entry and _entry.platform_hint:
                stable_parts.append(_entry.platform_hint)
        except Exception:
            pass

    # ── Context tier (cwd-dependent, may change between sessions) ─
    context_parts: List[str] = []

    # Note: ephemeral_system_prompt is NOT included here. It's injected at
    # API-call time only so it stays out of the cached/stored system prompt.
    if not myhome_user_chat and system_message is not None:
        context_parts.append(system_message)

    if not myhome_user_chat and not agent.skip_context_files:
        # Prefer the configured TERMINAL_CWD (gateway mode). When unset (local
        # CLI), None lets build_context_files_prompt fall back to the launch
        # dir — the user's real cwd there, but the install dir for the gateway
        # daemon, which is why the gateway sets TERMINAL_CWD.
        context_files_prompt = _r.build_context_files_prompt(
            cwd=resolve_context_cwd(), skip_soul=_soul_loaded)
        if context_files_prompt:
            context_parts.append(context_files_prompt)

    # ── Volatile tier (changes per session/turn — never cached) ───
    volatile_parts: List[str] = []

    if not myhome_user_chat and agent._memory_store:
        if agent._memory_enabled:
            mem_block = agent._memory_store.format_for_system_prompt("memory")
            if mem_block:
                volatile_parts.append(mem_block)
        # USER.md is always included when enabled.
        if agent._user_profile_enabled:
            user_block = agent._memory_store.format_for_system_prompt("user")
            if user_block:
                volatile_parts.append(user_block)

    # External memory provider system prompt block (additive to built-in)
    if not myhome_user_chat and agent._memory_manager:
        try:
            _ext_mem_block = agent._memory_manager.build_system_prompt()
            if _ext_mem_block:
                volatile_parts.append(_ext_mem_block)
        except Exception:
            pass

    from hermes_time import now as _hermes_now
    now = _hermes_now()
    # Date-only (not minute-precision) so the system prompt is byte-stable
    # for the full day.  Minute-precision changes invalidate prefix-cache KV
    # on every rebuild path (compression boundary, fresh-agent gateway turns,
    # session resume without a stored prompt).  The model can still query the
    # exact wall-clock time via tools when it actually needs it.
    # Credit: @iamfoz (PR #20451).
    timestamp_line = f"Conversation started: {now.strftime('%A, %B %d, %Y')}"
    if not myhome_user_chat and agent.pass_session_id and agent.session_id:
        timestamp_line += f"\nSession ID: {agent.session_id}"
    if not myhome_user_chat and agent.model:
        timestamp_line += f"\nModel: {agent.model}"
    if not myhome_user_chat and agent.provider:
        timestamp_line += f"\nProvider: {agent.provider}"
    volatile_parts.append(timestamp_line)

    return {
        "stable":   "\n\n".join(p.strip() for p in stable_parts   if p and p.strip()),
        "context":  "\n\n".join(p.strip() for p in context_parts  if p and p.strip()),
        "volatile": "\n\n".join(p.strip() for p in volatile_parts if p and p.strip()),
    }


def build_system_prompt(agent: Any, system_message: Optional[str] = None) -> str:
    """Assemble the full system prompt from all layers.

    Called once per session (cached on ``agent._cached_system_prompt``) and
    only rebuilt after context compression events. This ensures the system
    prompt is stable across all turns in a session, maximizing prefix cache
    hits.

    Layers are ordered cache-friendly: stable identity/guidance first,
    then session-stable context files, then per-call volatile content
    (memory, USER profile, timestamp).  The whole string is treated as
    one cached block — Hermes never rebuilds or reinjects parts of it
    mid-session, which is the only way to keep upstream prompt caches
    warm across turns.
    """
    parts = build_system_prompt_parts(agent, system_message=system_message)
    return "\n\n".join(p for p in (parts["stable"], parts["context"], parts["volatile"]) if p)


def invalidate_system_prompt(agent: Any) -> None:
    """Invalidate the cached system prompt, forcing a rebuild on the next turn.

    Called after context compression events. Also reloads memory from disk
    so the rebuilt prompt captures any writes from this session.
    """
    agent._cached_system_prompt = None
    if agent._memory_store:
        agent._memory_store.load_from_disk()


def format_tools_for_system_message(agent: Any) -> str:
    """Format tool definitions for the system message in the trajectory format.

    Returns:
        str: JSON string representation of tool definitions
    """
    if not agent.tools:
        return "[]"

    # Convert tool definitions to the format expected in trajectories
    formatted_tools = []
    for tool in agent.tools:
        func = tool["function"]
        formatted_tool = {
            "name": func["name"],
            "description": func.get("description", ""),
            "parameters": func.get("parameters", {}),
            "required": None  # Match the format in the example
        }
        formatted_tools.append(formatted_tool)

    return json.dumps(formatted_tools, ensure_ascii=False)


__all__ = [
    "build_system_prompt_parts",
    "build_system_prompt",
    "invalidate_system_prompt",
    "format_tools_for_system_message",
]
