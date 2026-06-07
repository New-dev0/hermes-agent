"""Gateway-derived per-user MCP and prompt context.

This module is intentionally server-side only. API clients may supply a stable
``X-Hermes-Session-Key``, but they do not get to provide arbitrary MCP server
definitions. The gateway derives the allowed GBrain source and MCP server from
that trusted scope.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

DEFAULT_GBRAIN_TOOLS = (
    "search",
    "query",
    "recall",
    "extract_facts",
    "put_page",
    "get_page",
    "list_pages",
)

_SOURCE_RE = re.compile(r"^myspace-[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


@dataclass(frozen=True)
class UserMcpRuntime:
    """Runtime additions for one gateway-scoped user."""

    source_id: Optional[str] = None
    server_name: Optional[str] = None
    toolsets: List[str] = field(default_factory=list)
    mcp_servers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    prompt_context: str = ""


def _enabled(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in _FALSE_VALUES


def derive_gbrain_source_id(gateway_session_key: Optional[str]) -> Optional[str]:
    """Return a safe GBrain source id from ``X-Hermes-Session-Key``.

    For SwitchX MySpace memory isolation we only accept explicit
    ``myspace-*`` scopes. This keeps arbitrary request strings from silently
    becoming durable memory namespaces.
    """

    key = (gateway_session_key or "").strip()
    if not key:
        return None
    if _SOURCE_RE.match(key):
        return key

    # Be tolerant of wrapper formats like ``agent:main:web:dm:myspace-972``.
    # Do not split on path separators; path-like strings should not be able to
    # smuggle a valid source segment.
    for part in re.split(r"[:\s|]+", key):
        if _SOURCE_RE.match(part):
            return part
    return None


def _stable_server_name(source_id: str) -> str:
    digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:12]
    return f"gbrain_{digest}"


def _resolve_gbrain_command() -> Optional[str]:
    configured = (
        os.getenv("HERMES_GBRAIN_MCP_COMMAND")
        or os.getenv("GBRAIN_MCP_COMMAND")
        or "/home/azureuser/.bun/bin/gbrain"
    ).strip()
    if not configured:
        return None

    expanded = os.path.expanduser(configured)
    if os.path.isabs(expanded):
        if os.path.isfile(expanded):
            return expanded
        logger.warning("Dynamic GBrain MCP skipped: command not found at %s", expanded)
        return None

    resolved = shutil.which(expanded)
    if resolved:
        return resolved

    logger.warning("Dynamic GBrain MCP skipped: command %r not found on PATH", configured)
    return None


def _prompt_root() -> Path:
    configured = os.getenv("HERMES_GATEWAY_USER_CONTEXT_ROOT", "").strip()
    if configured:
        return Path(os.path.expanduser(configured))
    return get_hermes_home() / "gateway" / "myspaces"


def _safe_child_path(root: Path, source_id: str, filename: str) -> Optional[Path]:
    try:
        root_resolved = root.resolve()
        candidate = (root_resolved / source_id / filename).resolve()
        candidate.relative_to(root_resolved)
        return candidate
    except Exception:
        logger.warning(
            "Gateway user context path rejected: root=%s source=%s file=%s",
            root,
            source_id,
            filename,
        )
        return None


def _load_prompt_file(path: Path, label: str) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        logger.warning("Could not read gateway user context %s: %s", path, exc)
        return ""
    if not content:
        return ""

    try:
        from agent.prompt_builder import _scan_context_content, _truncate_content

        content = _scan_context_content(content, label)
        content = _truncate_content(content, label)
    except Exception:
        # Prompt scanning is best-effort here; do not fail the request because
        # a private helper moved.
        pass
    return content


def build_user_prompt_context(source_id: Optional[str]) -> str:
    """Load optional gateway-scoped SOUL.md / MEMORY.md overlays."""

    if not source_id or not _enabled("HERMES_GATEWAY_USER_CONTEXT_ENABLED", True):
        return ""

    root = _prompt_root()
    sections: List[str] = []
    for filename, title in (
        ("SOUL.md", "Gateway SOUL.md"),
        ("MEMORY.md", "Gateway MEMORY.md"),
    ):
        path = _safe_child_path(root, source_id, filename)
        if path is None:
            continue
        content = _load_prompt_file(path, f"{source_id}/{filename}")
        if content:
            sections.append(f"## {title} ({source_id})\n\n{content}")

    if not sections:
        return ""
    return (
        "# Gateway User Context\n\n"
        "The following server-managed context applies only to this scoped user "
        "session. It is not supplied by the client request body.\n\n"
        + "\n\n".join(sections)
    )


def build_user_mcp_servers(gateway_session_key: Optional[str]) -> UserMcpRuntime:
    """Build scoped GBrain MCP config for one gateway request."""

    source_id = derive_gbrain_source_id(gateway_session_key)
    prompt_context = build_user_prompt_context(source_id)

    if not source_id or not _enabled("HERMES_GBRAIN_MCP_ENABLED", True):
        return UserMcpRuntime(source_id=source_id, prompt_context=prompt_context)

    command = _resolve_gbrain_command()
    if not command:
        return UserMcpRuntime(source_id=source_id, prompt_context=prompt_context)

    server_name = _stable_server_name(source_id)
    toolset = f"mcp-{server_name}"
    server_config: Dict[str, Any] = {
        "command": command,
        "args": ["serve"],
        "connect_timeout": int(os.getenv("HERMES_GBRAIN_MCP_CONNECT_TIMEOUT", "15")),
        "timeout": int(os.getenv("HERMES_GBRAIN_MCP_TOOL_TIMEOUT", "120")),
        "env": {
            "MCP_STDIO": "1",
            "GBRAIN_SOURCE": source_id,
        },
        "tools": {
            "include": list(DEFAULT_GBRAIN_TOOLS),
            "resources": False,
            "prompts": False,
        },
    }

    logger.info(
        "Dynamic GBrain MCP prepared: source=%s server=%s toolset=%s",
        source_id,
        server_name,
        toolset,
    )
    return UserMcpRuntime(
        source_id=source_id,
        server_name=server_name,
        toolsets=[toolset],
        mcp_servers={server_name: server_config},
        prompt_context=prompt_context,
    )
