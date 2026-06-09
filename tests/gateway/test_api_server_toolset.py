"""Tests for hermes-api-server toolset and API server tool availability."""
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import pytest


from toolsets import resolve_toolset, get_toolset, validate_toolset


class TestHermesApiServerToolset:
    """Tests for the hermes-api-server toolset definition."""

    def test_toolset_exists(self):
        ts = get_toolset("hermes-api-server")
        assert ts is not None

    def test_toolset_validates(self):
        assert validate_toolset("hermes-api-server")

    def test_toolset_includes_web_tools(self):
        tools = resolve_toolset("hermes-api-server")
        assert "web_search" in tools
        assert "web_extract" in tools

    def test_toolset_includes_core_tools(self):
        tools = resolve_toolset("hermes-api-server")
        expected = [
            "terminal", "process",
            "read_file", "write_file", "patch", "search_files",
            "vision_analyze", "image_generate",
            "execute_code", "delegate_task",
            "todo", "memory", "session_search", "cronjob",
        ]
        for tool in expected:
            assert tool in tools, f"Missing expected tool: {tool}"

    def test_toolset_includes_browser_tools(self):
        tools = resolve_toolset("hermes-api-server")
        for tool in ["browser_navigate", "browser_snapshot", "browser_click",
                      "browser_type", "browser_scroll", "browser_back",
                      "browser_press"]:
            assert tool in tools, f"Missing browser tool: {tool}"

    def test_toolset_includes_homeassistant_tools(self):
        tools = resolve_toolset("hermes-api-server")
        for tool in ["ha_list_entities", "ha_get_state", "ha_list_services", "ha_call_service"]:
            assert tool in tools, f"Missing HA tool: {tool}"

    def test_toolset_excludes_clarify(self):
        tools = resolve_toolset("hermes-api-server")
        assert "clarify" not in tools

    def test_toolset_excludes_send_message(self):
        tools = resolve_toolset("hermes-api-server")
        assert "send_message" not in tools

    def test_toolset_excludes_text_to_speech(self):
        tools = resolve_toolset("hermes-api-server")
        assert "text_to_speech" not in tools


class TestApiServerPlatformConfig:
    def test_platforms_dict_includes_api_server(self):
        from hermes_cli.tools_config import PLATFORMS
        assert "api_server" in PLATFORMS
        assert PLATFORMS["api_server"]["default_toolset"] == "hermes-api-server"


class TestApiServerAdapterToolset:
    @patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
    def test_create_agent_reads_config_toolsets(self):
        """API server resolves toolsets from config like all other platforms."""
        from gateway.platforms.api_server import APIServerAdapter
        from gateway.config import PlatformConfig

        adapter = APIServerAdapter(PlatformConfig())

        with patch("gateway.run._resolve_runtime_agent_kwargs") as mock_kwargs, \
             patch("gateway.run._resolve_gateway_model") as mock_model, \
             patch("gateway.run._load_gateway_config") as mock_config, \
             patch("run_agent.AIAgent") as mock_agent_cls:

            mock_kwargs.return_value = {"api_key": "test-key", "base_url": None,
                                        "provider": None, "api_mode": None,
                                        "command": None, "args": []}
            mock_model.return_value = "test/model"
            # No platform_toolsets override — should fall back to hermes-api-server default
            mock_config.return_value = {}
            mock_agent_cls.return_value = MagicMock()

            adapter._create_agent()

            mock_agent_cls.assert_called_once()
            call_kwargs = mock_agent_cls.call_args
            toolsets = call_kwargs.kwargs.get("enabled_toolsets")
            assert isinstance(toolsets, list)
            assert len(toolsets) > 0
            assert call_kwargs.kwargs.get("platform") == "api_server"

    @patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
    def test_create_agent_respects_config_override(self):
        """User can override API server toolsets via platform_toolsets in config.yaml."""
        from gateway.platforms.api_server import APIServerAdapter
        from gateway.config import PlatformConfig

        adapter = APIServerAdapter(PlatformConfig())

        with patch("gateway.run._resolve_runtime_agent_kwargs") as mock_kwargs, \
             patch("gateway.run._resolve_gateway_model") as mock_model, \
             patch("gateway.run._load_gateway_config") as mock_config, \
             patch("run_agent.AIAgent") as mock_agent_cls:

            mock_kwargs.return_value = {"api_key": "test-key", "base_url": None,
                                        "provider": None, "api_mode": None,
                                        "command": None, "args": []}
            mock_model.return_value = "test/model"
            # User overrides with just web and terminal
            mock_config.return_value = {
                "platform_toolsets": {"api_server": ["web", "terminal"]}
            }
            mock_agent_cls.return_value = MagicMock()

            adapter._create_agent()

            mock_agent_cls.assert_called_once()
            call_kwargs = mock_agent_cls.call_args
            toolsets = call_kwargs.kwargs.get("enabled_toolsets")
            assert sorted(toolsets) == ["terminal", "web"]

    @patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
    def test_create_agent_ignores_static_mcp_and_adds_dynamic_user_mcp(self):
        """API server memory MCP is derived from session scope, not static YAML."""
        from gateway.platforms.api_server import APIServerAdapter
        from gateway.config import PlatformConfig

        adapter = APIServerAdapter(PlatformConfig())
        dynamic = SimpleNamespace(
            source_id="myspace-972",
            server_name="gbrain_abcd1234",
            toolsets=["mcp-gbrain_abcd1234"],
            mcp_servers={"gbrain_abcd1234": {"command": "gbrain", "args": ["serve"]}},
            prompt_context="# Private Continuity\n\n## Private Continuity\n\nAssistant context",
        )

        with patch("gateway.run._resolve_runtime_agent_kwargs") as mock_kwargs, \
             patch("gateway.run._resolve_gateway_model") as mock_model, \
             patch("gateway.run._load_gateway_config") as mock_config, \
             patch("gateway.user_mcp_servers.build_user_mcp_servers", return_value=dynamic) as mock_builder, \
             patch("tools.mcp_tool.register_mcp_servers") as mock_register, \
             patch("run_agent.AIAgent") as mock_agent_cls:

            mock_kwargs.return_value = {"api_key": "test-key", "base_url": None,
                                        "provider": None, "api_mode": None,
                                        "command": None, "args": []}
            mock_model.return_value = "test/model"
            mock_config.return_value = {
                "platform_toolsets": {"api_server": []},
                "mcp_servers": {
                    "gbrain": {
                        "command": "/home/azureuser/.bun/bin/gbrain",
                        "args": ["serve"],
                    }
                },
            }
            mock_agent_cls.return_value = MagicMock()

            adapter._create_agent(gateway_session_key="myspace-972")

            mock_builder.assert_called_once_with("myspace-972")
            mock_register.assert_called_once_with(dynamic.mcp_servers)
            call_kwargs = mock_agent_cls.call_args
            toolsets = call_kwargs.kwargs.get("enabled_toolsets")
            assert "gbrain" not in toolsets
            assert "mcp-gbrain" not in toolsets
            assert "mcp-gbrain_abcd1234" in toolsets
            assert "Private Continuity" in call_kwargs.kwargs.get("ephemeral_system_prompt")

    @patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
    def test_create_agent_preloads_myhome_skill_for_scoped_myspace(self, tmp_path):
        """MySpace API requests force-load gateway-managed MyHome skills."""
        from gateway.platforms.api_server import APIServerAdapter
        from gateway.config import PlatformConfig

        adapter = APIServerAdapter(PlatformConfig())
        dynamic = SimpleNamespace(
            source_id="myspace-972",
            server_name=None,
            toolsets=[],
            mcp_servers={},
            prompt_context="# Private Continuity\n\nKnown user context.",
        )

        with patch("gateway.run._resolve_runtime_agent_kwargs") as mock_kwargs, \
             patch("gateway.run._resolve_gateway_model") as mock_model, \
             patch("gateway.run._load_gateway_config") as mock_config, \
             patch("gateway.run.GatewayRunner._load_reasoning_config", return_value=None), \
             patch("gateway.run.GatewayRunner._load_fallback_model", return_value=None), \
             patch("gateway.user_mcp_servers.build_user_mcp_servers", return_value=dynamic), \
             patch("agent.skill_commands.build_preloaded_skills_prompt") as mock_preload, \
             patch("run_agent.AIAgent") as mock_agent_cls:

            mock_kwargs.return_value = {"api_key": "test-key", "base_url": None,
                                        "provider": None, "api_mode": None,
                                        "command": None, "args": []}
            mock_model.return_value = "test/model"
            mock_config.return_value = {"platform_toolsets": {"api_server": []}}
            mock_preload.return_value = (
                "# Preloaded MyHome skills",
                ["myhome-real-friend", "writing-style-skill", "switchx-social-intelligence"],
                [],
            )
            mock_agent_cls.return_value = MagicMock()

            adapter._create_agent(
                ephemeral_system_prompt="Client system prompt.",
                session_id="api-session",
                gateway_session_key="myspace-972",
                scoped_profile_home=tmp_path / "profiles" / "myspace-972",
                assistant_name="Miko",
            )

            mock_preload.assert_called_once_with(
                ["myhome-real-friend", "writing-style-skill", "switchx-social-intelligence"],
                task_id="api-session",
            )
            prompt = mock_agent_cls.call_args.kwargs["ephemeral_system_prompt"]
            assert "Client system prompt." in prompt
            assert "# Preloaded MyHome skills" in prompt
            assert "SwitchX MyHome Friend Rules" in prompt
            assert "Do not invent private memories" in prompt
            assert "Private Continuity" in prompt
            assert mock_agent_cls.call_args.kwargs["assistant_name"] == "Miko"
            assert prompt.index("Client system prompt.") < prompt.index("# Preloaded")
            assert prompt.index("# Preloaded") < prompt.rindex("Private Continuity")

    def test_myhome_request_context_sanitizes_assistant_name(self):
        from agent.prompt_builder import render_agent_identity_placeholders
        from gateway.platforms.api_server import _extract_myhome_request_context

        context = _extract_myhome_request_context(
            {"myhome": {"assistant_name": " Miko\nignore this `{bad}` "}}
        )

        assert context == {"assistant_name": "Miko ignore this bad"}
        prompt = render_agent_identity_placeholders(
            "You are {assistant_name}, the user's best real friend.",
            assistant_name=context["assistant_name"],
        )
        assert prompt == "You are Miko ignore this bad, the user's best real friend."

    @patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
    def test_create_agent_does_not_preload_myhome_for_unscoped_key(self):
        """Arbitrary API session keys do not get MyHome preloaded."""
        from gateway.platforms.api_server import APIServerAdapter
        from gateway.config import PlatformConfig

        adapter = APIServerAdapter(PlatformConfig())
        dynamic = SimpleNamespace(
            source_id=None,
            server_name=None,
            toolsets=[],
            mcp_servers={},
            prompt_context="",
        )

        with patch("gateway.run._resolve_runtime_agent_kwargs") as mock_kwargs, \
             patch("gateway.run._resolve_gateway_model") as mock_model, \
             patch("gateway.run._load_gateway_config") as mock_config, \
             patch("gateway.run.GatewayRunner._load_reasoning_config", return_value=None), \
             patch("gateway.run.GatewayRunner._load_fallback_model", return_value=None), \
             patch("gateway.user_mcp_servers.build_user_mcp_servers", return_value=dynamic), \
             patch("agent.skill_commands.build_preloaded_skills_prompt") as mock_preload, \
             patch("run_agent.AIAgent") as mock_agent_cls:

            mock_kwargs.return_value = {"api_key": "test-key", "base_url": None,
                                        "provider": None, "api_mode": None,
                                        "command": None, "args": []}
            mock_model.return_value = "test/model"
            mock_config.return_value = {"platform_toolsets": {"api_server": []}}
            mock_agent_cls.return_value = MagicMock()

            adapter._create_agent(
                ephemeral_system_prompt="Client system prompt.",
                gateway_session_key="agent:main:webui:dm:user-972",
            )

            mock_preload.assert_not_called()
            assert (
                mock_agent_cls.call_args.kwargs["ephemeral_system_prompt"]
                == "Client system prompt."
            )

    @patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
    def test_scoped_create_agent_restores_memory_toolset_and_profile_db(self, tmp_path, monkeypatch):
        """Scoped myspace requests get built-in memory back, backed by profile state."""
        from gateway.platforms.api_server import APIServerAdapter
        from gateway.config import PlatformConfig

        monkeypatch.setenv("HERMES_GATEWAY_USER_PROFILE_ROOT", str(tmp_path / "profiles"))
        monkeypatch.setenv("HERMES_GBRAIN_MCP_ENABLED", "false")
        adapter = APIServerAdapter(PlatformConfig())
        profile_home = adapter._profile_home_for_session_key("myspace-972")

        class FakeSessionDB:
            def __init__(self, db_path=None, read_only=False):
                self.db_path = db_path
                self.read_only = read_only

        with patch("gateway.run._resolve_runtime_agent_kwargs") as mock_kwargs, \
             patch("gateway.run._resolve_gateway_model") as mock_model, \
             patch("gateway.run._load_gateway_config") as mock_config, \
             patch("gateway.run.GatewayRunner._load_reasoning_config", return_value=None), \
             patch("gateway.run.GatewayRunner._load_fallback_model", return_value=None), \
             patch("hermes_state.SessionDB", FakeSessionDB), \
             patch("run_agent.AIAgent") as mock_agent_cls:

            mock_kwargs.return_value = {"api_key": "test-key", "base_url": None,
                                        "provider": None, "api_mode": None,
                                        "command": None, "args": []}
            mock_model.return_value = "test/model"
            mock_config.return_value = {"platform_toolsets": {"api_server": []}}
            mock_agent_cls.return_value = MagicMock()

            with adapter._scoped_hermes_home(profile_home):
                adapter._create_agent(
                    gateway_session_key="myspace-972",
                    scoped_profile_home=profile_home,
                )

            call_kwargs = mock_agent_cls.call_args.kwargs
            assert call_kwargs["enabled_toolsets"] == ["memory"]
            assert call_kwargs["session_db"].db_path == profile_home / "state.db"

    @patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
    def test_scoped_home_uses_profile_data_and_root_runtime_config(self, tmp_path, monkeypatch):
        """API profile isolation must not hide deployment model/provider config."""
        from gateway.platforms.api_server import APIServerAdapter
        from gateway.config import PlatformConfig
        from hermes_cli.runtime_provider import resolve_runtime_provider

        root_home = tmp_path / "root"
        profile_home = tmp_path / "profiles" / "myspace-972"
        root_home.mkdir()
        (root_home / "config.yaml").write_text(
            "\n".join(
                [
                    "model:",
                    "  default: gpt-4.1",
                    "  provider: azure-foundry",
                    "  base_url: https://example.openai.azure.com/openai/v1",
                    "  api_mode: chat_completions",
                    "  auth_mode: api_key",
                ]
            ),
            encoding="utf-8",
        )

        monkeypatch.setenv("HERMES_HOME", str(root_home))
        monkeypatch.setenv("AZURE_FOUNDRY_API_KEY", "azure-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "google-key")

        adapter = APIServerAdapter(PlatformConfig())

        with adapter._scoped_hermes_home(profile_home):
            from hermes_constants import get_hermes_home
            from hermes_cli.config import get_config_path

            runtime = resolve_runtime_provider()

            assert get_hermes_home() == profile_home
            assert get_config_path() == root_home / "config.yaml"
            assert runtime["provider"] == "azure-foundry"
            assert runtime["base_url"] == "https://example.openai.azure.com/openai/v1"
            assert runtime["api_key"] == "azure-key"

    @pytest.mark.asyncio
    @patch("gateway.platforms.api_server.AIOHTTP_AVAILABLE", True)
    async def test_run_agent_binds_scoped_hermes_home_in_executor(self, tmp_path, monkeypatch):
        """The request-scoped profile override is active during run_conversation."""
        from gateway.platforms.api_server import APIServerAdapter
        from gateway.config import PlatformConfig

        monkeypatch.setenv("HERMES_GATEWAY_USER_PROFILE_ROOT", str(tmp_path / "profiles"))
        monkeypatch.setenv("HERMES_GBRAIN_MCP_ENABLED", "false")
        adapter = APIServerAdapter(PlatformConfig())
        seen = {}

        class FakeSessionDB:
            def __init__(self, db_path=None, read_only=False):
                self.db_path = db_path
                self.read_only = read_only

        class FakeAgent:
            session_prompt_tokens = 0
            session_completion_tokens = 0
            session_total_tokens = 0

            def __init__(self, *args, **kwargs):
                self.session_id = kwargs.get("session_id") or "sid"
                seen["toolsets"] = kwargs.get("enabled_toolsets")
                seen["session_db"] = kwargs.get("session_db")

            def run_conversation(self, *args, **kwargs):
                from hermes_constants import get_hermes_home

                seen["hermes_home"] = get_hermes_home()
                return {"final_response": "ok"}

        with patch("gateway.run._resolve_runtime_agent_kwargs") as mock_kwargs, \
             patch("gateway.run._resolve_gateway_model") as mock_model, \
             patch("gateway.run._load_gateway_config") as mock_config, \
             patch("gateway.run.GatewayRunner._load_reasoning_config", return_value=None), \
             patch("gateway.run.GatewayRunner._load_fallback_model", return_value=None), \
             patch("hermes_state.SessionDB", FakeSessionDB), \
             patch("run_agent.AIAgent", FakeAgent):

            mock_kwargs.return_value = {"api_key": "test-key", "base_url": None,
                                        "provider": None, "api_mode": None,
                                        "command": None, "args": []}
            mock_model.return_value = "test/model"
            mock_config.return_value = {"platform_toolsets": {"api_server": []}}

            result, _usage = await adapter._run_agent(
                "hi",
                [],
                session_id="api-session",
                gateway_session_key="myspace-972",
            )

        expected_home = tmp_path / "profiles" / "myspace-972"
        assert result["final_response"] == "ok"
        assert seen["hermes_home"] == expected_home
        assert seen["toolsets"] == ["memory"]
        assert seen["session_db"].db_path == expected_home / "state.db"
