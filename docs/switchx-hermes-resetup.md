# SwitchX Hermes Full Resetup Guide

This is the minimum operational document for rebuilding the SwitchX Hermes
deployment from scratch.

It intentionally does not contain secret values. Restore secrets from the
password manager, old VM backup, or Azure secret store. Never commit `.env`
files, adapter tokens, provider keys, or user memory dumps.

Current known production snapshot, captured 2026-06-07:

- VM: `gbrain-hermes-vm`
- SSH user: `azureuser`
- Public host: `40.80.84.104`
- Hermes repo path: `/home/azureuser/.hermes/hermes-agent`
- Hermes branch: `switch-ai`
- Last verified runtime code commit before this docs-only guide: `13c09afe0`
- Hermes home: `/home/azureuser/.hermes`
- Gateway service: `hermes-gateway`
- MyHome adapter service: `hermes-myhome-adapter`
- GBrain MCP service: `gbrain-mcp`
- GBrain adapter service: `gbrain-adapter`

## Runtime Shape

```text
SwitchX backend
  -> Hermes MyHome adapter :3142 /myhome/chat
       -> Hermes gateway :8642 /v1/responses
            -> request-scoped Hermes profile myspace-{user_id}
            -> server-derived scoped GBrain MCP source myspace-{user_id}
       -> root SOUL.md + curated skills for shared companion identity

SwitchX backend
  -> GBrain adapter :3141 /myhome/*
       -> gbrain CLI / MCP storage
       -> source myspace-{user_id}
```

Isolation model:

- Shared Hermes code: `/home/azureuser/.hermes/hermes-agent`
- Shared Hermes root identity/config: `/home/azureuser/.hermes`
- Per-user Hermes mutable state: `/home/azureuser/.hermes/profiles/myspace-{user_id}`
- Per-user GBrain source: `myspace-{user_id}`
- Root `SOUL.md` is the single shared persona source.
- Do not seed `SOUL.md` into `profiles/myspace-*`.
- Do not put private user facts into shared Hermes memory or shared skills.
- Private relationship memory belongs in GBrain under the user source.

## What Must Be Backed Up

Before rebuilding, back up these paths from the old VM if available:

```bash
/home/azureuser/.hermes/.env
/home/azureuser/.hermes/config.yaml
/home/azureuser/.hermes/SOUL.md
/home/azureuser/.hermes/skills/
/home/azureuser/.hermes/memories/
/home/azureuser/.hermes/profiles/
/home/azureuser/.hermes/state.db*
/home/azureuser/.hermes/response_store.db*
/home/azureuser/.gbrain/
/home/azureuser/gbrain/
/data/hermes-adapter/server.py
/data/hermes-adapter/token
/data/gbrain-adapter/server.py
/data/gbrain-adapter/token
/etc/systemd/system/hermes-gateway.service
/etc/systemd/system/hermes-myhome-adapter.service
/etc/systemd/system/gbrain-mcp.service
/etc/systemd/system/gbrain-adapter.service
```

Most important secrets/config to restore:

- `API_SERVER_KEY` for Hermes gateway API auth.
- Model provider credentials in `/home/azureuser/.hermes/.env`.
- `/data/hermes-adapter/token`, used by `HERMES_MYHOME_TOKEN` in backend.
- `/data/gbrain-adapter/token`, used by `GBRAIN_MYHOME_ADAPTER_TOKEN`.
- Any platform bot tokens if messaging platforms are enabled.

Do not set `HERMES_ENABLE_SHELL_COMMAND_TOOLS=1` for MyHome companion traffic.
Command execution tools are disabled by default for safety.

## VM Prerequisites

Install the baseline runtime:

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates build-essential python3 python3-venv python3-pip
```

Hermes itself requires Python `>=3.11,<3.14`. If the distro default Python is
older, install a supported Python version and use that for Hermes. The simple
adapters currently run with `/usr/bin/python3`.

Install Bun for `gbrain`:

```bash
curl -fsSL https://bun.sh/install | bash
export PATH="$HOME/.bun/bin:$HOME/.local/bin:$PATH"
```

Install or restore the `gbrain` CLI so this exists:

```bash
/home/azureuser/.bun/bin/gbrain --help
```

## Clone Hermes

```bash
mkdir -p /home/azureuser/.hermes
cd /home/azureuser/.hermes
git clone https://github.com/New-dev0/hermes-agent hermes-agent
cd /home/azureuser/.hermes/hermes-agent
git checkout switch-ai
```

Install Hermes according to the chosen Python runtime. One acceptable local
development install shape is:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -e ".[messaging,mcp]"
mkdir -p /home/azureuser/.local/bin
ln -sf /home/azureuser/.hermes/hermes-agent/hermes /home/azureuser/.local/bin/hermes
```

Verify:

```bash
/home/azureuser/.local/bin/hermes --help
```

## Restore Hermes Root

Restore these files from backup if available:

```bash
/home/azureuser/.hermes/.env
/home/azureuser/.hermes/config.yaml
/home/azureuser/.hermes/SOUL.md
/home/azureuser/.hermes/skills/
/home/azureuser/.hermes/memories/
```

If no backup exists, seed the shared SwitchX companion profile from the backend
repo artifact `deploy/hermes-switch-ai/`:

```bash
cp SOUL.md /home/azureuser/.hermes/SOUL.md
mkdir -p /home/azureuser/.hermes/skills /home/azureuser/.hermes/memories
cp -R skills/* /home/azureuser/.hermes/skills/
cp memories/MEMORY.md /home/azureuser/.hermes/memories/MEMORY.md
cp memories/USER.md /home/azureuser/.hermes/memories/USER.md
```

Merge the SwitchX config snippet into `/home/azureuser/.hermes/config.yaml`:

```yaml
memory:
  memory_enabled: false
  user_profile_enabled: false
  nudge_interval: 10

skills:
  creation_nudge_interval: 10
  external_dirs: []

platform_toolsets:
  api_server: []
```

Keep API-server tools narrow. The gateway dynamically adds scoped GBrain MCP
tools for valid `myspace-*` request scopes.

## Gateway Service

Create `/etc/systemd/system/hermes-gateway.service`:

```ini
[Unit]
Description=Hermes Gateway API Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=/home/azureuser/.hermes/hermes-agent
Environment=HOME=/home/azureuser
Environment=HERMES_HOME=/home/azureuser/.hermes
Environment=PATH=/home/azureuser/.local/bin:/home/azureuser/.bun/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/home/azureuser/.local/bin/hermes gateway run --accept-hooks
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-gateway
```

Health check:

```bash
curl -sS http://127.0.0.1:8642/health
```

Expected:

```json
{"status":"ok","platform":"hermes-agent"}
```

## GBrain MCP Service

Create `/etc/systemd/system/gbrain-mcp.service`:

```ini
[Unit]
Description=GBrain HTTP MCP Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=/home/azureuser
Environment=PATH=/home/azureuser/.bun/bin:/home/azureuser/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/home/azureuser/.bun/bin/gbrain serve --http --port 3131 --bind 0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gbrain-mcp
```

## GBrain Adapter

The backend uses this adapter for `/myhome/message`, `/myhome/page/get`,
`/myhome/page/upsert`, `/myhome/context`, and `/myhome/search`.

Restore or create:

```bash
sudo mkdir -p /data/gbrain-adapter
sudo chown -R azureuser:azureuser /data/gbrain-adapter
```

Required files:

```text
/data/gbrain-adapter/server.py
/data/gbrain-adapter/token
```

Create `/etc/systemd/system/gbrain-adapter.service`:

```ini
[Unit]
Description=SwitchX GBrain Adapter
After=network-online.target gbrain-mcp.service docker.service
Wants=network-online.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=/data/gbrain-adapter
Environment=GBRAIN_ADAPTER_PORT=3141
Environment=GBRAIN_ADAPTER_TOKEN_FILE=/data/gbrain-adapter/token
ExecStart=/usr/bin/python3 /data/gbrain-adapter/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and verify:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now gbrain-adapter
curl -sS http://127.0.0.1:3141/health
```

Expected:

```json
{"status":"ok"}
```

## Hermes MyHome Adapter

The backend calls this adapter for chat generation.

Restore or create:

```bash
sudo mkdir -p /data/hermes-adapter
sudo chown -R azureuser:azureuser /data/hermes-adapter
```

Required files:

```text
/data/hermes-adapter/server.py
/data/hermes-adapter/token
```

Create `/etc/systemd/system/hermes-myhome-adapter.service`:

```ini
[Unit]
Description=SwitchX Hermes MyHome Adapter
After=network-online.target gbrain-mcp.service
Wants=network-online.target

[Service]
Type=simple
User=azureuser
WorkingDirectory=/data/hermes-adapter
Environment=HERMES_ADAPTER_PORT=3142
Environment=HERMES_ADAPTER_TOKEN_FILE=/data/hermes-adapter/token
Environment=HERMES_ADAPTER_TIMEOUT_SECONDS=600
Environment=HOME=/home/azureuser
Environment=HERMES_HOME=/home/azureuser/.hermes
ExecStart=/usr/bin/python3 /data/hermes-adapter/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and verify:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-myhome-adapter
curl -sS http://127.0.0.1:3142/health
```

Expected:

```json
{"status":"ok"}
```

## Backend Environment

The SwitchX backend must point to the adapters:

```bash
HERMES_MYHOME_ENABLED=true
HERMES_MYHOME_URL=http://<vm-private-or-public-host>:3142
HERMES_MYHOME_TOKEN=<contents of /data/hermes-adapter/token>
HERMES_MYHOME_TIMEOUT_SECONDS=120

GBRAIN_MYHOME_MEMORY_ENABLED=true
GBRAIN_MYHOME_ADAPTER_URL=http://<vm-private-or-public-host>:3141
GBRAIN_MYHOME_ADAPTER_TOKEN=<contents of /data/gbrain-adapter/token>
GBRAIN_MYHOME_ADAPTER_TIMEOUT_SECONDS=60

# Optional fallback/direct MCP path used by backend memory code:
GBRAIN_MCP_URL=http://<vm-private-or-public-host>:3131
GBRAIN_MCP_TOKEN=<if configured>
GBRAIN_MCP_TIMEOUT_SECONDS=5
```

Prefer private networking or firewall allowlists. Do not expose adapter ports to
the public internet without an ingress/auth layer.

## Per-User Isolation Verification

Gateway session key must be a stable `myspace-*` source:

```text
X-Hermes-Session-Key: myspace-{user_id}
```

Expected behavior:

- Hermes profile path resolves to `/home/azureuser/.hermes/profiles/myspace-{user_id}`.
- Dynamic GBrain MCP gets `GBRAIN_SOURCE=myspace-{user_id}`.
- GBrain pages are read/written only under that source.
- Root `SOUL.md` remains shared.

Profile path check:

```bash
cd /home/azureuser/.hermes/hermes-agent
python3 - <<'PY'
from pathlib import Path
from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from tools.runtime_paths import runtime_path
import tools.skills_tool as skills_tool

profile = Path("/home/azureuser/.hermes/profiles/myspace-resetup-check")
token = set_hermes_home_override(profile)
try:
    print(runtime_path(skills_tool.SKILLS_DIR))
finally:
    reset_hermes_home_override(token)
PY
```

Expected:

```text
/home/azureuser/.hermes/profiles/myspace-resetup-check/skills
```

Dynamic GBrain source derivation check:

```bash
cd /home/azureuser/.hermes/hermes-agent
python3 - <<'PY'
from gateway.user_mcp_servers import build_user_mcp_servers

runtime = build_user_mcp_servers("myspace-resetup-check")
print(runtime.source_id)
print(runtime.toolsets)
for server in runtime.mcp_servers.values():
    print(server["env"]["GBRAIN_SOURCE"])
PY
```

Expected:

```text
myspace-resetup-check
['mcp-gbrain_<hash>']
myspace-resetup-check
```

The hash suffix is stable but does not need to be hardcoded.

## Command Tool Safety Verification

Command execution tools must stay hidden and blocked for MyHome traffic:

```bash
cd /home/azureuser/.hermes/hermes-agent
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

Expected:

```json
{
  "exposed": [],
  "direct": {
    "terminal": {"status": "blocked"},
    "process": {"status": "blocked"},
    "execute_code": {"status": "blocked"}
  }
}
```

## Full Service Verification

```bash
systemctl is-active hermes-gateway hermes-myhome-adapter gbrain-mcp gbrain-adapter
curl -sS http://127.0.0.1:8642/health
curl -sS http://127.0.0.1:3142/health
curl -sS http://127.0.0.1:3141/health
journalctl -u hermes-gateway -u hermes-myhome-adapter -u gbrain-mcp -u gbrain-adapter -n 120 --no-pager
```

Expected service status:

```text
active
active
active
active
```

## Deployment Update Flow

Local:

```powershell
cd D:\SwitchX-Desktop\hermes-agent
git status --short
pytest -o addopts= tests/hermes_cli/test_shell_command_policy.py -q
git push origin switch-ai
```

Azure:

```bash
cd /home/azureuser/.hermes/hermes-agent
git pull --ff-only origin switch-ai
sudo systemctl restart hermes-gateway hermes-myhome-adapter
systemctl is-active hermes-gateway hermes-myhome-adapter
```

Restart GBrain services only when GBrain or adapter code/config changes:

```bash
sudo systemctl restart gbrain-mcp gbrain-adapter
```

## Resetup Checklist

- VM user `azureuser` exists and can SSH.
- `/home/azureuser/.local/bin` and `/home/azureuser/.bun/bin` are on service PATH.
- `gbrain` CLI runs.
- Hermes repo is cloned from `New-dev0/hermes-agent`.
- Branch is `switch-ai`.
- `/home/azureuser/.hermes/.env` restored with provider credentials and `API_SERVER_KEY`.
- `/home/azureuser/.hermes/config.yaml` restored or merged with SwitchX snippet.
- `/home/azureuser/.hermes/SOUL.md` restored from backup or seed.
- Curated `skills/` restored.
- Per-user `profiles/` restored if preserving existing user state.
- GBrain storage restored from `/home/azureuser/.gbrain`.
- `/data/hermes-adapter/server.py` and token restored.
- `/data/gbrain-adapter/server.py` and token restored.
- Four systemd services installed and active.
- Gateway health, adapter health, profile scoping, GBrain scoping, and command-tool block all verified.
