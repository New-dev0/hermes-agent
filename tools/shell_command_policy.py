"""Central policy for disabling Hermes command-execution tools.

This deployment currently does not allow the agent to run shell/process
commands. Keep the policy in one small module so schema exposure, direct tool
dispatch, and sandbox bypasses all make the same decision.
"""

from __future__ import annotations

import json
import os


COMMAND_EXECUTION_TOOL_NAMES = frozenset({"terminal", "process", "execute_code"})

DISABLED_MESSAGE = "Shell command execution is disabled for this Hermes deployment."


def command_execution_enabled() -> bool:
    """Return True only when command execution is explicitly re-enabled."""
    return os.getenv("HERMES_ENABLE_SHELL_COMMAND_TOOLS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def command_execution_disabled() -> bool:
    return not command_execution_enabled()


def command_execution_disabled_result(tool_name: str | None = None) -> str:
    payload = {
        "status": "blocked",
        "error": DISABLED_MESSAGE,
    }
    if tool_name:
        payload["tool"] = tool_name
    return json.dumps(payload, ensure_ascii=False)
