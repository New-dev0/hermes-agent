import sys

from gateway.user_mcp_servers import (
    build_user_mcp_servers,
    derive_gbrain_source_id,
)


def test_derive_gbrain_source_id_accepts_myspace_key():
    assert derive_gbrain_source_id("myspace-972") == "myspace-972"


def test_derive_gbrain_source_id_accepts_wrapped_myspace_key():
    assert (
        derive_gbrain_source_id("agent:main:webui:dm:myspace-88023")
        == "myspace-88023"
    )


def test_derive_gbrain_source_id_rejects_arbitrary_keys():
    assert derive_gbrain_source_id("agent:main:webui:dm:user-42") is None
    assert derive_gbrain_source_id("../../myspace-42") is None


def test_build_user_mcp_servers_scopes_gbrain_env(monkeypatch):
    monkeypatch.setenv("HERMES_GBRAIN_MCP_COMMAND", sys.executable)
    runtime = build_user_mcp_servers("myspace-972")

    assert runtime.source_id == "myspace-972"
    assert runtime.server_name is not None
    assert runtime.server_name.startswith("gbrain_")
    assert runtime.toolsets == [f"mcp-{runtime.server_name}"]

    server = runtime.mcp_servers[runtime.server_name]
    assert server["command"] == sys.executable
    assert server["args"] == ["serve"]
    assert server["env"]["MCP_STDIO"] == "1"
    assert server["env"]["GBRAIN_SOURCE"] == "myspace-972"
    assert "put_page" in server["tools"]["include"]
    assert "recall" in server["tools"]["include"]
    assert server["tools"]["resources"] is False
    assert server["tools"]["prompts"] is False


def test_build_user_prompt_context_loads_gateway_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_GBRAIN_MCP_COMMAND", sys.executable)
    monkeypatch.setenv("HERMES_GATEWAY_USER_CONTEXT_ROOT", str(tmp_path))

    user_dir = tmp_path / "myspace-972"
    user_dir.mkdir()
    (user_dir / "SOUL.md").write_text("You are Saiki.", encoding="utf-8")
    (user_dir / "MEMORY.md").write_text("Shared ritual: midnight check-in.", encoding="utf-8")

    runtime = build_user_mcp_servers("myspace-972")

    assert "Gateway SOUL.md (myspace-972)" in runtime.prompt_context
    assert "You are Saiki." in runtime.prompt_context
    assert "Gateway MEMORY.md (myspace-972)" in runtime.prompt_context
    assert "Shared ritual: midnight check-in." in runtime.prompt_context
