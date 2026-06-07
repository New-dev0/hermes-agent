# Command Execution Tools Disabled

This deployment disables Hermes command-execution tools by default.

Disabled tools:

- `terminal`
- `process`
- `execute_code`

## Reason

The MyHome assistant is user-facing companion software, not an operations agent. In the live Gen Z benchmark, the Arjun technical-debugging case showed a risky behavior: the agent matched the user's "dont yap, next command" style, but invented a service name in a shell command.

That failure mode is dangerous because a confident wrong command can look authoritative. Until command generation has stricter grounding and verification, Hermes must not expose shell/process/code execution tools to the model.

`execute_code` is disabled with `terminal` because it can spawn subprocesses or run Python code that bypasses terminal command approval.

## Enforcement

The policy is centralized in:

- `tools/shell_command_policy.py`

Schema exposure is blocked in:

- `model_tools.py`

Direct handler execution is blocked in:

- `tools/terminal_tool.py`
- `tools/process_registry.py`
- `tools/code_execution_tool.py`

This means command tools are hidden from the model and also return a blocked response if reached by direct dispatch.

## Re-enable

Only re-enable intentionally by setting:

```bash
HERMES_ENABLE_SHELL_COMMAND_TOOLS=1
```

Do not enable this for MyHome companion traffic until command mode has a separate verified tool policy.

## Verification

Focused regression test:

```bash
pytest -o addopts= tests/hermes_cli/test_shell_command_policy.py -q
```

Expected result:

```text
2 passed
```

Runtime verification:

```bash
python3 - <<'PY'
import json
import model_tools

model_tools._clear_tool_defs_cache()
tool_defs = model_tools.get_tool_definitions(
    enabled_toolsets=["terminal", "code_execution"],
    quiet_mode=True,
    skip_tool_search_assembly=True,
)
names = [tool["function"]["name"] for tool in tool_defs]
direct = {}
for name, args in {
    "terminal": {"command": "echo nope"},
    "process": {"action": "list"},
    "execute_code": {"code": "print(1)"},
}.items():
    direct[name] = json.loads(model_tools.handle_function_call(name, args))
print(json.dumps({"exposed": names, "direct": direct}, indent=2))
PY
```

Expected shape:

```json
{
  "exposed": [],
  "direct": {
    "terminal": {
      "status": "blocked",
      "error": "Shell command execution is disabled for this Hermes deployment.",
      "tool": "terminal"
    },
    "process": {
      "status": "blocked",
      "error": "Shell command execution is disabled for this Hermes deployment.",
      "tool": "process"
    },
    "execute_code": {
      "status": "blocked",
      "error": "Shell command execution is disabled for this Hermes deployment.",
      "tool": "execute_code"
    }
  }
}
```

Azure deployment verified on commit `49bc0f593` with:

```bash
systemctl is-active hermes-gateway hermes-myhome-adapter
```

Expected:

```text
active
active
```
