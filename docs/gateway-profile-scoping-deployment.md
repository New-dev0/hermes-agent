# Gateway Profile Scoping Deployment

This document records how the SwitchX Hermes gateway is deployed on the Azure
VM and how to verify that per-user profile scoping works after deployment.

## Azure Target

- VM user: `azureuser`
- VM host: `40.80.84.104`
- Repository path: `/home/azureuser/.hermes/hermes-agent`
- Active branch: `switch-ai`
- Systemd service: `hermes-gateway`
- Service working directory: `/home/azureuser/.hermes/hermes-agent`
- Service `HERMES_HOME`: `/home/azureuser/.hermes`
- Local API listener: `127.0.0.1:8642`

The service starts with root Hermes home so shared config, provider credentials,
and gateway process state remain under `/home/azureuser/.hermes`. Individual API
requests can still bind a per-user Hermes profile through
`X-Hermes-Session-Key`.

## Deployment

From the local repo:

```powershell
git status --short
uv run --extra dev pytest tests\gateway\test_user_mcp_servers.py tests\gateway\test_api_server_toolset.py tests\run_agent\test_background_review.py tests\run_agent\test_background_review_toolset_restriction.py tests\tools\test_runtime_profile_paths.py -q --override-ini addopts=
git push origin switch-ai
```

On the VM:

```bash
cd /home/azureuser/.hermes/hermes-agent
git fetch origin switch-ai
git pull --no-rebase --no-edit origin switch-ai
sudo systemctl restart hermes-gateway
sudo systemctl is-active hermes-gateway
```

## Request Flow

1. The API client sends `X-Hermes-Session-Key`.
2. The gateway only accepts durable profile scopes that resolve to `myspace-*`.
3. A valid key maps to `/home/azureuser/.hermes/profiles/<myspace-id>`.
4. The API request temporarily sets a context-local Hermes home override.
5. During that request, runtime path lookups resolve profile-local files:

```text
/home/azureuser/.hermes/profiles/myspace-972/state.db
/home/azureuser/.hermes/profiles/myspace-972/memories/MEMORY.md
/home/azureuser/.hermes/profiles/myspace-972/memories/USER.md
/home/azureuser/.hermes/profiles/myspace-972/skills/
/home/azureuser/.hermes/profiles/myspace-972/SOUL.md
/home/azureuser/.hermes/profiles/myspace-972/.skills_prompt_snapshot.json
```

The override is a `ContextVar`, not `os.environ`, so concurrent API requests can
use different profile homes without overwriting one another.

## Verification

Health check:

```bash
curl -sS http://127.0.0.1:8642/health
```

Expected:

```json
{"status":"ok","platform":"hermes-agent"}
```

Service and commit check:

```bash
cd /home/azureuser/.hermes/hermes-agent
git branch --show-current
git rev-parse --short HEAD
sudo systemctl is-active hermes-gateway
```

Runtime profile path check without making an LLM call:

```bash
cd /home/azureuser/.hermes/hermes-agent
python3 - <<'PY'
from pathlib import Path
from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from tools.runtime_paths import runtime_path
import tools.skills_tool as skills_tool

profile = Path("/home/azureuser/.hermes/profiles/myspace-deploy-check")
token = set_hermes_home_override(profile)
try:
    print(runtime_path(skills_tool.SKILLS_DIR))
finally:
    reset_hermes_home_override(token)
PY
```

Expected output:

```text
/home/azureuser/.hermes/profiles/myspace-deploy-check/skills
```

Optional live API verification:

```bash
set -a
. /home/azureuser/.hermes/.env
set +a

curl -sS http://127.0.0.1:8642/v1/chat/completions \
  -H "Authorization: Bearer $API_SERVER_KEY" \
  -H "Content-Type: application/json" \
  -H "X-Hermes-Session-Key: myspace-deploy-check" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"Reply with only: deploy-check-ok"}],"stream":false}'
```

Then inspect:

```bash
ls -la /home/azureuser/.hermes/profiles/myspace-deploy-check
journalctl -u hermes-gateway -n 120 --no-pager
```

Look for a log line like:

```text
API Server scoped Hermes profile enabled: home=/home/azureuser/.hermes/profiles/myspace-deploy-check
```
