import sys

from gateway.user_mcp_servers import (
    build_user_mcp_servers,
    derive_gbrain_source_id,
    ensure_gbrain_source,
    get_user_preload_skills,
    resolve_user_profile_home,
    _run_gbrain_call,
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


def test_user_preload_skills_default_to_myhome_for_myspace(monkeypatch):
    monkeypatch.delenv("HERMES_GATEWAY_USER_PRELOAD_SKILLS", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_USER_PRELOAD_SKILLS_ENABLED", raising=False)

    assert get_user_preload_skills("myspace-972") == (
        "myhome-real-friend",
        "writing-style-skill",
        "switchx-social-intelligence",
    )
    assert get_user_preload_skills("agent:main:webui:dm:user-972") == ()


def test_user_preload_skills_can_be_configured_and_disabled(monkeypatch):
    monkeypatch.setenv(
        "HERMES_GATEWAY_USER_PRELOAD_SKILLS",
        "myhome-companion, signal-detector myhome-companion",
    )

    assert get_user_preload_skills("myspace-972") == (
        "myhome-companion",
        "signal-detector",
    )

    monkeypatch.setenv("HERMES_GATEWAY_USER_PRELOAD_SKILLS_ENABLED", "false")
    assert get_user_preload_skills("myspace-972") == ()


def test_build_user_mcp_servers_scopes_gbrain_env(monkeypatch):
    monkeypatch.setenv("HERMES_GBRAIN_MCP_COMMAND", sys.executable)
    monkeypatch.setattr("gateway.user_mcp_servers.ensure_gbrain_source", lambda source_id: True)
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
    monkeypatch.setattr("gateway.user_mcp_servers.ensure_gbrain_source", lambda source_id: True)

    user_dir = tmp_path / "myspace-972"
    user_dir.mkdir()
    (user_dir / "SOUL.md").write_text(
        "You are Nova for {{ source_id }} via {{mcp_toolset}}.",
        encoding="utf-8",
    )
    (user_dir / "MEMORY.md").write_text(
        "Shared ritual: midnight check-in. Unknown: {{still_unknown}}",
        encoding="utf-8",
    )

    runtime = build_user_mcp_servers("myspace-972")

    assert "Gateway SOUL.md" not in runtime.prompt_context
    assert "You are Nova for myspace-972 via mcp-" not in runtime.prompt_context
    assert "## Private Continuity" in runtime.prompt_context
    assert "Shared ritual: midnight check-in." in runtime.prompt_context
    assert "{{still_unknown}}" in runtime.prompt_context


def test_build_user_prompt_context_loads_configured_gateway_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_GBRAIN_MCP_COMMAND", sys.executable)
    monkeypatch.setenv("HERMES_GATEWAY_USER_CONTEXT_ROOT", str(tmp_path))
    monkeypatch.setattr("gateway.user_mcp_servers.ensure_gbrain_source", lambda source_id: True)
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

    assert "## Identity" in runtime.prompt_context
    assert "Identity for myspace-972." in runtime.prompt_context
    assert "## Relationship Rituals" in runtime.prompt_context
    assert "Daily callback ritual." in runtime.prompt_context
    assert "Should not load." not in runtime.prompt_context
    assert "Bad" not in runtime.prompt_context


def test_ensure_gbrain_source_registers_missing_source(monkeypatch):
    calls = []

    def fake_run(source_id, args, **kwargs):
        calls.append((source_id, args, kwargs))

        class Result:
            stdout = ""

        if args == ["sources", "list", "--json"]:
            Result.stdout = '{"sources": [{"id": "default"}]}'
        return Result()

    monkeypatch.setattr("gateway.user_mcp_servers._run_gbrain_cli", fake_run)

    assert ensure_gbrain_source("myspace-newsource")

    assert calls[0][1] == ["sources", "list", "--json"]
    assert calls[1][1] == [
        "sources",
        "add",
        "myspace-newsource",
        "--name",
        "MySpace newsource",
        "--no-federated",
    ]


def test_run_gbrain_call_uses_source_aware_tool_invocation(monkeypatch):
    calls = []

    def fake_run(source_id, args, **kwargs):
        calls.append((source_id, args, kwargs))

        class Result:
            stdout = '{"content": [{"type": "text", "text": "{\\"ok\\":true}"}]}'

        return Result()

    monkeypatch.setattr("gateway.user_mcp_servers.ensure_gbrain_source", lambda source_id: True)
    monkeypatch.setattr("gateway.user_mcp_servers._run_gbrain_cli", fake_run)

    assert _run_gbrain_call("myspace-972", "get_page", {"slug": "profile/assistant-profile"}) == '{"ok":true}'
    assert calls[0][0] == "myspace-972"
    assert calls[0][1] == [
        "call",
        "--source",
        "myspace-972",
        "get_page",
        '{"slug": "profile/assistant-profile"}',
    ]
