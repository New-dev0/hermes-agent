import sys

from gateway.user_mcp_servers import (
    build_user_mcp_servers,
    derive_gbrain_source_id,
    resolve_user_profile_home,
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


def test_resolve_user_profile_home_uses_safe_myspace_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_USER_PROFILE_ROOT", str(tmp_path))

    assert resolve_user_profile_home("myspace-972") == tmp_path / "myspace-972"
    assert resolve_user_profile_home("../../myspace-972") is None
    assert resolve_user_profile_home("user-972") is None


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
    (user_dir / "SOUL.md").write_text(
        "You are Saiki for {{ source_id }} via {{mcp_toolset}}.",
        encoding="utf-8",
    )
    (user_dir / "MEMORY.md").write_text(
        "Shared ritual: midnight check-in. Unknown: {{still_unknown}}",
        encoding="utf-8",
    )

    runtime = build_user_mcp_servers("myspace-972")

    assert "Gateway SOUL.md (myspace-972)" in runtime.prompt_context
    assert "You are Saiki for myspace-972 via mcp-" in runtime.prompt_context
    assert "Gateway MEMORY.md (myspace-972)" in runtime.prompt_context
    assert "Shared ritual: midnight check-in." in runtime.prompt_context
    assert "{{still_unknown}}" in runtime.prompt_context


def test_build_user_prompt_context_loads_configured_gateway_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_GBRAIN_MCP_COMMAND", sys.executable)
    monkeypatch.setenv("HERMES_GATEWAY_USER_CONTEXT_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "HERMES_GATEWAY_USER_CONTEXT_FILES",
        "SOUL.md:Identity,RITUALS.md:Relationship Rituals,../bad.md:Bad",
    )

    user_dir = tmp_path / "myspace-972"
    user_dir.mkdir()
    (user_dir / "SOUL.md").write_text("Identity for {{gbrain_source_id}}.", encoding="utf-8")
    (user_dir / "MEMORY.md").write_text("Should not load.", encoding="utf-8")
    (user_dir / "RITUALS.md").write_text("Daily callback ritual.", encoding="utf-8")

    runtime = build_user_mcp_servers("myspace-972")

    assert "## Identity (myspace-972)" in runtime.prompt_context
    assert "Identity for myspace-972." in runtime.prompt_context
    assert "## Relationship Rituals (myspace-972)" in runtime.prompt_context
    assert "Daily callback ritual." in runtime.prompt_context
    assert "Should not load." not in runtime.prompt_context
    assert "Bad" not in runtime.prompt_context
