# Phase 6 — GitHub Integration, Cloud Agent Spawning & Admin Support

> **Goal**: Add GitHub as a new messaging integration, enable spawning cloud agents from any connected messaging channel (Telegram, Slack, Discord, GitHub), enforce proper icon usage everywhere, and add admin panel support for agent/sandbox management.

---

## Constraints (MUST follow)

- **No emojis as icons** — use `react-icons` only (`react-icons/fa`, `react-icons/si`, `react-icons/lu`, `react-icons/fc`)
- **Dark theme**: backgrounds `bg-[#171717]`, `bg-[#111]`, `bg-[#0f0f0f]`; borders `border-[#2a2a2a]`; accent `bg-blue-600`
- **Strict ESLint**: no `setState` in effect bodies, no ref access during render — use derived-state patterns
- **Import icons directly** — e.g. `import { FaGithub } from 'react-icons/fa'`, `import { SiGithub } from 'react-icons/si'`
- **Never break existing features** — all current Telegram/Slack/Discord flows must continue working
- **Python backend**: Python 3.11+, FastAPI, SQLAlchemy async, type hints everywhere

---

## Task 1: GitHub Integration (Backend)

### 1a. Create `integrations/github_connector.py`

Follow the exact same pattern as `integrations/telegram.py`. Create a `GitHubIntegration` class extending `BaseIntegration`.

```python
"""GitHub App webhook integration client."""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubIntegration(BaseIntegration):
    """GitHub App connector with real API calls."""

    name = "github"

    def __init__(self) -> None:
        self.connected = False
        self._token: str | None = None           # Personal access token OR GitHub App installation token
        self._webhook_secret: str | None = None   # For verifying webhook payloads
        self._app_id: str | None = None
        self._username: str | None = None

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate the token by calling /user and store metadata."""
        token = str(config.get("token", "")).strip()
        webhook_secret = str(config.get("webhook_secret", "")).strip()
        app_id = str(config.get("app_id", "")).strip()
        self._token = token or None
        self._webhook_secret = webhook_secret or None
        self._app_id = app_id or None

        if not self._token:
            self.connected = False
            return {"connected": False, "username": None, "error": "Missing token"}

        try:
            data = await self._request("GET", "/user")
        except Exception as exc:
            logger.warning("GitHub auth failed: %s", exc)
            self.connected = False
            return {"connected": False, "username": None, "error": str(exc)}

        if "login" in data:
            self.connected = True
            self._username = data["login"]
            return {"connected": True, "username": self._username}

        self.connected = False
        return {"connected": False, "username": None, "error": data.get("message") or "Auth failed"}

    def verify_webhook_signature(self, payload_body: bytes, signature_header: str) -> bool:
        """Verify GitHub webhook HMAC-SHA256 signature."""
        if not self._webhook_secret or not signature_header:
            return False
        expected = "sha256=" + hmac.new(
            self._webhook_secret.encode(), payload_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header)

    async def disconnect(self) -> None:
        self.connected = False
        self._token = None
        self._webhook_secret = None
        self._app_id = None
        self._username = None

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "github_list_repos", "description": "List repositories for the authenticated user"},
            {"name": "github_get_issues", "description": "Get issues for a repository"},
            {"name": "github_create_issue", "description": "Create a new issue"},
            {"name": "github_get_pull_requests", "description": "List pull requests for a repo"},
            {"name": "github_create_comment", "description": "Comment on an issue or PR"},
            {"name": "github_get_file", "description": "Get file content from a repo"},
            {"name": "github_webhook_event", "description": "Process incoming webhook event"},
        ]

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.connected or not self._token:
            return {"ok": False, "tool": tool_name, "error": "GitHub integration is not connected"}

        if tool_name == "github_list_repos":
            return await self._list_repos(params)
        if tool_name == "github_get_issues":
            return await self._get_issues(params)
        if tool_name == "github_create_issue":
            return await self._create_issue(params)
        if tool_name == "github_get_pull_requests":
            return await self._get_pull_requests(params)
        if tool_name == "github_create_comment":
            return await self._create_comment(params)
        if tool_name == "github_get_file":
            return await self._get_file(params)

        return {"ok": False, "tool": tool_name, "error": "Unsupported tool"}

    # ── Tool implementations ──────────────────────────────────────────

    async def _list_repos(self, params: dict[str, Any]) -> dict[str, Any]:
        per_page = int(params.get("per_page", 30))
        data = await self._request("GET", "/user/repos", params={"per_page": per_page, "sort": "updated"})
        ok = isinstance(data, list)
        return {"ok": ok, "tool": "github_list_repos", "result": data}

    async def _get_issues(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = str(params.get("repo", "")).strip()  # "owner/repo"
        if not repo:
            return {"ok": False, "tool": "github_get_issues", "error": "repo is required (owner/repo)"}
        state = str(params.get("state", "open"))
        data = await self._request("GET", f"/repos/{repo}/issues", params={"state": state, "per_page": 30})
        ok = isinstance(data, list)
        return {"ok": ok, "tool": "github_get_issues", "result": data}

    async def _create_issue(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = str(params.get("repo", "")).strip()
        title = str(params.get("title", "")).strip()
        body = str(params.get("body", "")).strip()
        if not repo or not title:
            return {"ok": False, "tool": "github_create_issue", "error": "repo and title are required"}
        data = await self._request("POST", f"/repos/{repo}/issues", json={"title": title, "body": body})
        ok = bool(data.get("id")) if isinstance(data, dict) else False
        return {"ok": ok, "tool": "github_create_issue", "result": data}

    async def _get_pull_requests(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = str(params.get("repo", "")).strip()
        if not repo:
            return {"ok": False, "tool": "github_get_pull_requests", "error": "repo is required"}
        state = str(params.get("state", "open"))
        data = await self._request("GET", f"/repos/{repo}/pulls", params={"state": state, "per_page": 30})
        ok = isinstance(data, list)
        return {"ok": ok, "tool": "github_get_pull_requests", "result": data}

    async def _create_comment(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = str(params.get("repo", "")).strip()
        issue_number = params.get("issue_number")
        body = str(params.get("body", "")).strip()
        if not repo or issue_number is None or not body:
            return {"ok": False, "tool": "github_create_comment", "error": "repo, issue_number, and body are required"}
        data = await self._request("POST", f"/repos/{repo}/issues/{issue_number}/comments", json={"body": body})
        ok = bool(data.get("id")) if isinstance(data, dict) else False
        return {"ok": ok, "tool": "github_create_comment", "result": data}

    async def _get_file(self, params: dict[str, Any]) -> dict[str, Any]:
        repo = str(params.get("repo", "")).strip()
        path = str(params.get("path", "")).strip()
        ref = str(params.get("ref", "")).strip() or None
        if not repo or not path:
            return {"ok": False, "tool": "github_get_file", "error": "repo and path are required"}
        p: dict[str, Any] = {}
        if ref:
            p["ref"] = ref
        data = await self._request("GET", f"/repos/{repo}/contents/{path}", params=p if p else None)
        ok = isinstance(data, dict) and "content" in data
        return {"ok": ok, "tool": "github_get_file", "result": data}

    # ── HTTP helper ───────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        if not self._token:
            return {"message": "Missing token"}

        url = f"{GITHUB_API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.request(method, url, headers=headers, params=params, json=json)

        try:
            data = response.json()
        except ValueError:
            data = {"message": response.text}

        if response.status_code >= 400:
            error = data.get("message") if isinstance(data, dict) else response.text
            return {"message": error or f"HTTP {response.status_code}", "status": response.status_code}

        return data
```

### 1b. Register GitHub in `integrations/__init__.py`

```python
"""Integration exports."""

from integrations.discord import DiscordIntegration
from integrations.github_connector import GitHubIntegration
from integrations.slack_connector import SlackIntegration
from integrations.telegram import TelegramIntegration

__all__ = ["TelegramIntegration", "SlackIntegration", "DiscordIntegration", "GitHubIntegration"]
```

### 1c. Add GitHub endpoints to `main.py`

Add `GitHubRegistry` class following the exact pattern of `TelegramRegistry`, `SlackRegistry`, `DiscordRegistry`:

```python
from integrations.github_connector import GitHubIntegration
```

Add the registry class:

```python
class GitHubRegistry:
    """In-memory github integration registry."""

    def __init__(self) -> None:
        self._integrations: dict[str, GitHubIntegration] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    def get_github(self, integration_id: str) -> GitHubIntegration | None:
        return self._integrations.get(integration_id)

    def get_config(self, integration_id: str) -> dict[str, Any]:
        return self._configs.get(integration_id, {})

    def upsert(self, integration_id: str, integration: GitHubIntegration, config: dict[str, Any]) -> None:
        self._integrations[integration_id] = integration
        self._configs[integration_id] = config

github_registry = GitHubRegistry()
```

Add these endpoints after the Discord endpoints section:

```python
@app.post("/api/integrations/github/register/{integration_id}")
async def register_github_integration(integration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = {
        "token": str(payload.get("token", "")).strip(),
        "webhook_secret": str(payload.get("webhook_secret", "")).strip(),
        "app_id": str(payload.get("app_id", "")).strip(),
    }
    integration = GitHubIntegration()
    connection = await integration.connect(config)
    github_registry.upsert(integration_id, integration, config)
    return {"connection": connection}

@app.post("/api/integrations/github/{integration_id}/test")
async def test_github_integration(integration_id: str) -> dict[str, Any]:
    integration = github_registry.get_github(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="GitHub integration not found")
    result = await integration.execute_tool("github_list_repos", {"per_page": 5})
    return result

@app.post("/api/integrations/github/{integration_id}/webhook")
async def github_webhook(integration_id: str, request: Request) -> dict[str, Any]:
    """Receive GitHub webhook events (push, PR, issue, etc.)."""
    integration = github_registry.get_github(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="GitHub integration not found")

    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if integration._webhook_secret and not integration.verify_webhook_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    import json as _json
    try:
        payload = _json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = request.headers.get("X-GitHub-Event", "ping")
    return {"ok": True, "event": event_type, "action": payload.get("action"), "received": True}
```

---

## Task 2: GitHub Integration (Frontend)

### 2a. Add GitHub to `frontend/src/lib/mcp.ts`

Add `FaGithub` import and extend the types/maps:

```typescript
import { FaDiscord, FaFolder, FaGithub, FaGlobe, FaLock, FaPlus, FaSlack, FaTelegram, FaTerminal } from 'react-icons/fa'
```

Add `'github'` to the `IntegrationIcon` type:

```typescript
export type IntegrationIcon = 'web-search' | 'filesystem' | 'code-exec' | 'telegram' | 'slack' | 'discord' | 'github' | 'custom'
```

Add to `INTEGRATION_ICON_MAP`:

```typescript
const INTEGRATION_ICON_MAP: Record<IntegrationIcon, IconType> = {
  'web-search': FaGlobe,
  filesystem: FaFolder,
  'code-exec': FaTerminal,
  telegram: FaTelegram,
  slack: FaSlack,
  discord: FaDiscord,
  github: FaGithub,
  custom: FaPlus,
}
```

Add GitHub to `DEFAULT_INTEGRATIONS` array (after Discord):

```typescript
{
  id: 'github',
  name: 'GitHub',
  icon: 'github',
  description: 'GitHub repos, issues, PRs, and webhook events.',
  enabled: false,
  status: 'disabled',
  settings: {
    token: '',
    webhook_secret: '',
    app_id: '',
  },
  tools: ['github_list_repos', 'github_get_issues', 'github_create_issue', 'github_get_pull_requests', 'github_create_comment', 'github_get_file', 'github_webhook_event'],
},
```

Update `normalizeIntegrationConfig` to handle `github`:

```typescript
export function normalizeIntegrationConfig(integration: IntegrationConfig): IntegrationConfig {
  return {
    ...integration,
    icon: normalizeIntegrationIcon(
      integration.icon,
      integration.id === 'telegram' ? 'telegram'
        : integration.id === 'discord' ? 'discord'
        : integration.id === 'slack' ? 'slack'
        : integration.id === 'github' ? 'github'
        : 'custom',
    ),
  }
}
```

### 2b. Add GitHub to `frontend/src/components/icons.tsx`

Add imports:

```typescript
import { FaGithub } from 'react-icons/fa'
import { SiGithub } from 'react-icons/si'
```

Add to `Icons` object:

```typescript
github: ({ className }: IconProps) => <FaGithub className={className ?? 'h-4 w-4'} aria-hidden='true' />,
```

Add to `BRAND_ICON_MAP`:

```typescript
github: { icon: SiGithub, className: 'text-[#f0f0f0]' },
```

### 2c. Add GitHub configure form to `frontend/src/components/settings/IntegrationsTab.tsx`

Add `connectGithub` and `testGithub` functions following the exact pattern of `connectDiscord`/`testDiscord`:

```typescript
const connectGithub = async (integration: IntegrationConfig) => {
  const settings = integration.settings ?? {}
  const payload = {
    token: settings.token ?? '',
    webhook_secret: settings.webhook_secret ?? '',
    app_id: settings.app_id ?? '',
  }
  if (!payload.token) {
    updateIntegration(integration.id, { status: 'error', enabled: false })
    setIntegrationError(integration.id, 'Token is required.')
    return
  }
  setBusyId(integration.id)
  setIntegrationError(integration.id, null)
  try {
    const data = await postJson(`/api/integrations/github/register/${integration.id}`, payload)
    const connected = Boolean(data?.connection?.connected)
    updateIntegration(integration.id, { status: connected ? 'connected' : 'error', enabled: connected })
    if (!connected) setIntegrationError(integration.id, 'Connection failed.')
  } catch (err) {
    updateIntegration(integration.id, { status: 'error' })
    setIntegrationError(integration.id, err instanceof Error ? err.message : 'Connection failed.')
  } finally {
    setBusyId(null)
  }
}

const testGithub = async (integration: IntegrationConfig) => {
  setBusyId(integration.id)
  setIntegrationError(integration.id, null)
  try {
    const data = await postJson(`/api/integrations/github/${integration.id}/test`, {})
    const ok = Boolean(data?.ok)
    updateIntegration(integration.id, { status: ok ? 'connected' : 'error' })
    if (!ok) setIntegrationError(integration.id, 'GitHub test failed.')
  } catch (err) {
    updateIntegration(integration.id, { status: 'error' })
    setIntegrationError(integration.id, err instanceof Error ? err.message : 'GitHub test failed.')
  } finally {
    setBusyId(null)
  }
}
```

Update `toggleIntegration` to handle `'github'`:

```typescript
if (integration.id === 'github') {
  await connectGithub(integration)
  return
}
```

Update `isConfigurable` and `canTest`:

```typescript
const isConfigurable = ['telegram', 'slack', 'discord', 'github'].includes(integration.id)
const canTest = ['telegram', 'slack', 'discord', 'github'].includes(integration.id)
```

Update `handleTest`:

```typescript
if (integration.id === 'github') return testGithub(integration)
```

Add the GitHub config expand panel (after Discord's expand panel):

```tsx
{expandedId === integration.id && integration.id === 'github' && (
  <div className='mt-3 grid gap-2 text-xs'>
    <input
      placeholder='Personal access token or installation token'
      value={integration.settings?.token ?? ''}
      onChange={(event) =>
        updateIntegration(integration.id, {
          settings: { ...(integration.settings ?? {}), token: event.target.value },
        })
      }
      className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
    />
    <input
      placeholder='Webhook secret (optional)'
      value={integration.settings?.webhook_secret ?? ''}
      onChange={(event) =>
        updateIntegration(integration.id, {
          settings: { ...(integration.settings ?? {}), webhook_secret: event.target.value },
        })
      }
      className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
    />
    <input
      placeholder='GitHub App ID (optional)'
      value={integration.settings?.app_id ?? ''}
      onChange={(event) =>
        updateIntegration(integration.id, {
          settings: { ...(integration.settings ?? {}), app_id: event.target.value },
        })
      }
      className='rounded border border-[#2a2a2a] bg-[#0f0f0f] px-3 py-2'
    />
    <div className='flex gap-2'>
      <button
        type='button'
        onClick={() => connectGithub(integration)}
        disabled={isBusy}
        className={`rounded bg-blue-600 px-3 py-1 ${isBusy ? 'opacity-60' : ''}`}
      >
        Save & Connect
      </button>
      <button
        type='button'
        onClick={() => setExpandedId(null)}
        className='rounded border border-[#2a2a2a] px-3 py-1'
      >
        Close
      </button>
    </div>
  </div>
)}
```

---

## Task 3: Cloud Agent Spawning — Database Models

Add these new models to `backend/database.py`. Import `ForeignKey` from sqlalchemy, and `Boolean` from sqlalchemy if not already imported.

```python
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func, inspect, text
```

Add these models after `CreditTopUp`:

```python
class AgentTask(Base):
    """A cloud agent task spawned from any channel (web, telegram, slack, discord, github)."""

    __tablename__ = "agent_tasks"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(255), nullable=False, index=True)
    platform = Column(String(50), nullable=False)          # "web" | "telegram" | "slack" | "discord" | "github"
    platform_chat_id = Column(String(255), nullable=True)  # external chat/channel where request originated
    platform_message_id = Column(String(255), nullable=True)
    instruction = Column(Text, nullable=False)
    status = Column(String(30), default="pending")          # "pending" | "running" | "completed" | "failed" | "cancelled"
    agent_type = Column(String(50), default="navigator")    # "navigator" | "coder" | "researcher" | "custom"
    provider = Column(String(50), nullable=True)            # LLM provider used
    model = Column(String(255), nullable=True)              # LLM model used
    sandbox_id = Column(String(255), nullable=True)         # E2B sandbox ID (future)
    result_summary = Column(Text, nullable=True)            # Short summary of what the agent accomplished
    error_message = Column(Text, nullable=True)
    credits_used = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class AgentAction(Base):
    """Individual action performed by a cloud agent during task execution."""

    __tablename__ = "agent_actions"

    id = Column(String(255), primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String(255), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)               # ordering: 1, 2, 3, ...
    action_type = Column(String(50), nullable=False)         # "navigate" | "click" | "type" | "code_exec" | "file_write" | "git_op" | "llm_call" | "screenshot"
    description = Column(Text, nullable=True)                # human-readable summary of the action
    input_data = Column(Text, nullable=True)                 # JSON: what went into the action
    output_data = Column(Text, nullable=True)                # JSON: what came out
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

---

## Task 4: Cloud Agent Spawning — Backend API

### 4a. Create `backend/agent_spawn.py`

This service manages spawning and tracking cloud agent tasks from any messaging channel.

```python
"""Cloud agent spawning service — creates and tracks agent tasks from any channel."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AgentTask, AgentAction

logger = logging.getLogger(__name__)


async def create_agent_task(
    db: AsyncSession,
    *,
    user_id: str,
    instruction: str,
    platform: str,
    platform_chat_id: str | None = None,
    platform_message_id: str | None = None,
    agent_type: str = "navigator",
    provider: str | None = None,
    model: str | None = None,
) -> AgentTask:
    """Create a new agent task record."""
    task = AgentTask(
        id=str(uuid4()),
        user_id=user_id,
        platform=platform,
        platform_chat_id=platform_chat_id,
        platform_message_id=platform_message_id,
        instruction=instruction,
        status="pending",
        agent_type=agent_type,
        provider=provider,
        model=model,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    logger.info("Agent task created: %s (platform=%s, user=%s)", task.id, platform, user_id)
    return task


async def update_task_status(
    db: AsyncSession,
    task_id: str,
    status: str,
    *,
    result_summary: str | None = None,
    error_message: str | None = None,
    credits_used: int | None = None,
    sandbox_id: str | None = None,
) -> AgentTask | None:
    """Update an agent task's status."""
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        return None

    task.status = status
    now = datetime.now(timezone.utc)

    if status == "running" and not task.started_at:
        task.started_at = now
    if status in ("completed", "failed", "cancelled"):
        task.completed_at = now
    if result_summary is not None:
        task.result_summary = result_summary
    if error_message is not None:
        task.error_message = error_message
    if credits_used is not None:
        task.credits_used = credits_used
    if sandbox_id is not None:
        task.sandbox_id = sandbox_id

    await db.commit()
    await db.refresh(task)
    return task


async def log_agent_action(
    db: AsyncSession,
    *,
    task_id: str,
    sequence: int,
    action_type: str,
    description: str | None = None,
    input_data: str | None = None,
    output_data: str | None = None,
    duration_ms: int | None = None,
) -> AgentAction:
    """Log an individual agent action."""
    action = AgentAction(
        id=str(uuid4()),
        task_id=task_id,
        sequence=sequence,
        action_type=action_type,
        description=description,
        input_data=input_data,
        output_data=output_data,
        duration_ms=duration_ms,
    )
    db.add(action)
    await db.commit()
    return action


async def get_user_tasks(
    db: AsyncSession,
    user_id: str,
    *,
    status: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[AgentTask]:
    """Get tasks for a user, optionally filtered by status/platform."""
    query = select(AgentTask).where(AgentTask.user_id == user_id)
    if status:
        query = query.where(AgentTask.status == status)
    if platform:
        query = query.where(AgentTask.platform == platform)
    query = query.order_by(desc(AgentTask.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_task_actions(db: AsyncSession, task_id: str) -> list[AgentAction]:
    """Get all actions for a task, ordered by sequence."""
    result = await db.execute(
        select(AgentAction).where(AgentAction.task_id == task_id).order_by(AgentAction.sequence)
    )
    return list(result.scalars().all())


async def get_task_by_id(db: AsyncSession, task_id: str) -> AgentTask | None:
    """Get a single task by ID."""
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    return result.scalar_one_or_none()
```

### 4b. Add agent spawn API endpoints to `main.py`

Add these endpoints in the integration endpoints section. They need `_verify_session` for user auth and `get_session` for DB:

```python
from backend.agent_spawn import (
    create_agent_task,
    get_task_actions,
    get_task_by_id,
    get_user_tasks,
    update_task_status,
)
```

Endpoints to add:

```python
# ── Cloud Agent Spawn endpoints ───────────────────────────────────────

@app.post("/api/agents/spawn")
async def spawn_agent_task(
    payload: dict[str, Any],
    user: dict[str, Any] = Depends(_verify_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Spawn a new cloud agent task."""
    instruction = str(payload.get("instruction", "")).strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction is required")

    task = await create_agent_task(
        db,
        user_id=user["uid"],
        instruction=instruction,
        platform=str(payload.get("platform", "web")).strip(),
        platform_chat_id=payload.get("platform_chat_id"),
        platform_message_id=payload.get("platform_message_id"),
        agent_type=str(payload.get("agent_type", "navigator")).strip(),
        provider=payload.get("provider"),
        model=payload.get("model"),
    )
    return {
        "task_id": task.id,
        "status": task.status,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


@app.get("/api/agents/tasks")
async def list_agent_tasks(
    status: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict[str, Any] = Depends(_verify_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List agent tasks for the current user."""
    tasks = await get_user_tasks(db, user["uid"], status=status, platform=platform, limit=limit, offset=offset)
    return {
        "tasks": [
            {
                "id": t.id,
                "instruction": t.instruction[:200],
                "status": t.status,
                "platform": t.platform,
                "agent_type": t.agent_type,
                "provider": t.provider,
                "model": t.model,
                "credits_used": t.credits_used,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ]
    }


@app.get("/api/agents/tasks/{task_id}")
async def get_agent_task(
    task_id: str,
    user: dict[str, Any] = Depends(_verify_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a specific agent task with actions."""
    task = await get_task_by_id(db, task_id)
    if not task or task.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found")

    actions = await get_task_actions(db, task_id)
    return {
        "id": task.id,
        "instruction": task.instruction,
        "status": task.status,
        "platform": task.platform,
        "agent_type": task.agent_type,
        "provider": task.provider,
        "model": task.model,
        "sandbox_id": task.sandbox_id,
        "result_summary": task.result_summary,
        "error_message": task.error_message,
        "credits_used": task.credits_used,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "actions": [
            {
                "id": a.id,
                "sequence": a.sequence,
                "action_type": a.action_type,
                "description": a.description,
                "duration_ms": a.duration_ms,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in actions
        ],
    }


@app.post("/api/agents/tasks/{task_id}/cancel")
async def cancel_agent_task(
    task_id: str,
    user: dict[str, Any] = Depends(_verify_session),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Cancel a running or pending agent task."""
    task = await get_task_by_id(db, task_id)
    if not task or task.user_id != user["uid"]:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel task in '{task.status}' status")

    updated = await update_task_status(db, task_id, "cancelled")
    return {"task_id": task_id, "status": updated.status if updated else "cancelled"}
```

### 4c. Add messaging channel agent spawn helper

Add a helper function in `backend/agent_spawn.py` for spawning agents from messaging webhooks:

```python
async def spawn_from_channel(
    db: AsyncSession,
    *,
    user_id: str,
    instruction: str,
    platform: str,
    chat_id: str | None = None,
    message_id: str | None = None,
) -> AgentTask:
    """Convenience wrapper for spawning an agent from a messaging channel webhook."""
    return await create_agent_task(
        db,
        user_id=user_id,
        instruction=instruction,
        platform=platform,
        platform_chat_id=chat_id,
        platform_message_id=message_id,
        agent_type="coder",
    )
```

---

## Task 5: Icon System Cleanup

### 5a. Remove legacy emoji map from `frontend/src/lib/mcp.ts`

The `LEGACY_INTEGRATION_ICON_MAP` currently maps emojis to icon names. Keep the map for backwards compatibility, but ensure no emojis are ever rendered. The current `normalizeIntegrationIcon` function already handles this correctly — just verify it still works.

### 5b. Remove `MODEL_ICON_URL` from `frontend/src/lib/models.ts`

The line `export const MODEL_ICON_URL = 'https://i.postimg.cc/NMtZmLXT/download_4.png'` should be **deleted**. Search all files that import `MODEL_ICON_URL` and replace usage with the appropriate provider icon from `renderProviderIcon`.

### 5c. Verify all integrations use proper `react-icons`

The icon maps in `mcp.ts`, `icons.tsx`, and `models.ts` must all include GitHub. After this task, the complete icon maps should be:

In `icons.tsx` `BRAND_ICON_MAP`:
```typescript
const BRAND_ICON_MAP: Record<string, { icon: IconType; className: string }> = {
  slack: { icon: SiSlack, className: 'text-[#E01E5A]' },
  discord: { icon: SiDiscord, className: 'text-[#5865F2]' },
  telegram: { icon: SiTelegram, className: 'text-[#24A1DE]' },
  github: { icon: SiGithub, className: 'text-[#f0f0f0]' },
  'web-search': { icon: LuGlobe, className: 'text-blue-200' },
  filesystem: { icon: LuFolder, className: 'text-zinc-200' },
  'code-exec': { icon: LuCode, className: 'text-emerald-200' },
  custom: { icon: LuPlus, className: 'text-blue-200' },
}
```

---

## Task 6: Admin Support for Cloud Agents

> **Prerequisite**: Admin system Phase 2 endpoints at `backend/admin/`. If the admin router does not exist yet, create `backend/admin/__init__.py` and `backend/admin/agents.py`. Mount it at `/api/admin/agents` in `main.py`.

### 6a. Create `backend/admin/agents.py`

Admin endpoints for managing cloud agent tasks across all users:

```python
"""Admin endpoints for cloud agent task management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AgentAction, AgentTask, get_session

router = APIRouter(prefix="/agents", tags=["admin-agents"])


@router.get("/tasks")
async def admin_list_tasks(
    user_id: str | None = None,
    status: str | None = None,
    platform: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List all agent tasks (admin view) with optional filters."""
    query = select(AgentTask)
    if user_id:
        query = query.where(AgentTask.user_id == user_id)
    if status:
        query = query.where(AgentTask.status == status)
    if platform:
        query = query.where(AgentTask.platform == platform)
    query = query.order_by(desc(AgentTask.created_at)).limit(limit).offset(offset)

    count_query = select(func.count()).select_from(AgentTask)
    if user_id:
        count_query = count_query.where(AgentTask.user_id == user_id)
    if status:
        count_query = count_query.where(AgentTask.status == status)
    if platform:
        count_query = count_query.where(AgentTask.platform == platform)

    result = await db.execute(query)
    tasks = list(result.scalars().all())
    total = (await db.execute(count_query)).scalar() or 0

    return {
        "tasks": [
            {
                "id": t.id,
                "user_id": t.user_id,
                "instruction": t.instruction[:200],
                "status": t.status,
                "platform": t.platform,
                "agent_type": t.agent_type,
                "provider": t.provider,
                "model": t.model,
                "sandbox_id": t.sandbox_id,
                "credits_used": t.credits_used,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/tasks/{task_id}")
async def admin_get_task(
    task_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get full task details including all actions."""
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    actions_result = await db.execute(
        select(AgentAction).where(AgentAction.task_id == task_id).order_by(AgentAction.sequence)
    )
    actions = list(actions_result.scalars().all())

    return {
        "id": task.id,
        "user_id": task.user_id,
        "instruction": task.instruction,
        "status": task.status,
        "platform": task.platform,
        "agent_type": task.agent_type,
        "provider": task.provider,
        "model": task.model,
        "sandbox_id": task.sandbox_id,
        "result_summary": task.result_summary,
        "error_message": task.error_message,
        "credits_used": task.credits_used,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "actions": [
            {
                "id": a.id,
                "sequence": a.sequence,
                "action_type": a.action_type,
                "description": a.description,
                "input_data": a.input_data,
                "output_data": a.output_data,
                "duration_ms": a.duration_ms,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in actions
        ],
    }


@router.post("/tasks/{task_id}/cancel")
async def admin_cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Force-cancel any agent task (admin power)."""
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in ("completed", "failed", "cancelled"):
        return {"task_id": task_id, "status": task.status, "message": "Task already terminated"}

    from backend.agent_spawn import update_task_status
    from datetime import datetime, timezone

    updated = await update_task_status(db, task_id, "cancelled")
    return {"task_id": task_id, "status": updated.status if updated else "cancelled"}


@router.get("/stats")
async def admin_agent_stats(
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Dashboard stats for agent tasks."""
    total = (await db.execute(select(func.count()).select_from(AgentTask))).scalar() or 0
    running = (await db.execute(
        select(func.count()).select_from(AgentTask).where(AgentTask.status == "running")
    )).scalar() or 0
    pending = (await db.execute(
        select(func.count()).select_from(AgentTask).where(AgentTask.status == "pending")
    )).scalar() or 0
    completed = (await db.execute(
        select(func.count()).select_from(AgentTask).where(AgentTask.status == "completed")
    )).scalar() or 0
    failed = (await db.execute(
        select(func.count()).select_from(AgentTask).where(AgentTask.status == "failed")
    )).scalar() or 0

    # Credits consumed by all agents
    total_credits = (await db.execute(
        select(func.coalesce(func.sum(AgentTask.credits_used), 0))
    )).scalar() or 0

    # Breakdown by platform
    platform_counts_result = await db.execute(
        select(AgentTask.platform, func.count()).group_by(AgentTask.platform)
    )
    platforms = {row[0]: row[1] for row in platform_counts_result.all()}

    return {
        "total": total,
        "running": running,
        "pending": pending,
        "completed": completed,
        "failed": failed,
        "total_credits_used": total_credits,
        "by_platform": platforms,
    }
```

### 6b. Mount admin agents router

In `main.py`, after existing admin router mounts (or create the admin router structure if not present):

```python
# If backend/admin/router.py exists, add agents subrouter there.
# Otherwise add directly:
from backend.admin.agents import router as admin_agents_router

# Mount under admin prefix (ensure admin auth middleware is applied)
app.include_router(admin_agents_router, prefix="/api/admin")
```

If an admin auth dependency (`require_admin`) already exists from Phase 1/2, apply it to the router:
```python
app.include_router(admin_agents_router, prefix="/api/admin", dependencies=[Depends(require_admin)])
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `FaGithub` is imported and used in `mcp.ts`, `icons.tsx`
- [ ] `SiGithub` is imported and used in `icons.tsx` `BRAND_ICON_MAP`
- [ ] `'github'` is in `IntegrationIcon` type union
- [ ] GitHub appears in `DEFAULT_INTEGRATIONS` array
- [ ] GitHub configure form renders in IntegrationsTab
- [ ] `/api/integrations/github/register/{id}`, `/api/integrations/github/{id}/test`, `/api/integrations/github/{id}/webhook` endpoints exist
- [ ] `AgentTask` and `AgentAction` models exist in `database.py`
- [ ] `/api/agents/spawn`, `/api/agents/tasks`, `/api/agents/tasks/{id}`, `/api/agents/tasks/{id}/cancel` endpoints exist
- [ ] Admin endpoints at `/api/admin/agents/tasks`, `/api/admin/agents/tasks/{id}`, `/api/admin/agents/tasks/{id}/cancel`, `/api/admin/agents/stats` exist
- [ ] No emoji icons anywhere in rendered UI
- [ ] `MODEL_ICON_URL` is removed from `models.ts`
- [ ] All existing Telegram/Slack/Discord tests still pass
- [ ] App starts without import errors
