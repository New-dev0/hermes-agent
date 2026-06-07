import json


def test_command_execution_tools_hidden_by_default(monkeypatch):
    monkeypatch.delenv("HERMES_ENABLE_SHELL_COMMAND_TOOLS", raising=False)

    import model_tools

    model_tools._clear_tool_defs_cache()
    tool_defs = model_tools.get_tool_definitions(
        enabled_toolsets=["terminal", "code_execution"],
        quiet_mode=True,
        skip_tool_search_assembly=True,
    )
    names = {tool["function"]["name"] for tool in tool_defs}

    assert "terminal" not in names
    assert "process" not in names
    assert "execute_code" not in names


def test_command_execution_tools_block_direct_dispatch(monkeypatch):
    monkeypatch.delenv("HERMES_ENABLE_SHELL_COMMAND_TOOLS", raising=False)

    import model_tools

    for name, args in {
        "terminal": {"command": "echo should-not-run"},
        "process": {"action": "list"},
        "execute_code": {"code": "print('should-not-run')"},
    }.items():
        result = json.loads(model_tools.handle_function_call(name, args))
        assert result["status"] == "blocked"
        assert result["tool"] == name
        assert "disabled" in result["error"].lower()
