"""Sub-agent runtime — spawns ephemeral child agents from within a parent session.

Each sub-agent:
  - Runs in a separate asyncio.Task inside the same server process
  - Has its own cancel_event and steering_context
  - Streams events back through the parent WebSocket, tagged with sub_session_id
  - Uses only browser + web-search + memory tools (no bot/telegram/discord/slack-bot)
  - Is ephemeral — cancelled and removed when the parent WS disconnects
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Awaitable, Literal
from uuid import uuid4

logger = logging.getLogger(__name__)

# ── Sub-agent tool allowlist ──────────────────────────────────────────────────
# Sub-agents get: browser control, web search, memory, wait, ask_user_input
# Sub-agents do NOT get: cron, memory_patch, cron_delete (write-heavy destructive ops),
#   telegram, discord, slack-bot, github-bot — those require explicit parent trust.
SUBAGENT_ALLOWED_TOOLS = frozenset({
    "screenshot",
    "go_to_url",
    "click",
    "type_text",
    "scroll",
    "go_back",
    "wait",
    "ask_user_input",
    "memory_search",
    "memory_write",
    "memory_read",
    "web_search",
    "done",
    "error",
})

# System prompt for sub-agents — no bot tools, focused on task completion
SUBAGENT_SYSTEM_PROMPT = """\
You are an Aegis sub-agent. You have been spawned by the main Aegis agent to complete \
a focused sub-task. Work independently and efficiently.

You have access to: browser control (screenshot, navigate, click, type, scroll), \
web search, and memory tools.

You do NOT have access to: messaging bots (Telegram, Slack, Discord), cron scheduling, \
or cross-agent communication tools.

{\"tool\": \"screenshot\"}
  → Takes a screenshot of the current browser state.

{\"tool\": \"go_to_url\", \"url\": \"https://...\"}
  → Navigates the browser to a URL.

{\"tool\": \"click\", \"x\": 500, \"y\": 300, \"description\": \"button label\"}
  → Clicks at pixel coordinates. Viewport is 1280x720.

{\"tool\": \"type_text\", \"text\": \"hello\", \"x\": 400, \"y\": 200}
  → Types text, optionally clicking to focus first.

{\"tool\": \"scroll\", \"direction\": \"down\", \"amount\": 300}
  → Scrolls the page.

{\"tool\": \"go_back\"}
  → Navigates browser history back.

{\"tool\": \"wait\", \"seconds\": 1.5}
  → Waits for the page to load.

{\"tool\": \"ask_user_input\", \"question\": \"...\", \"options\": [...]}
  → Asks the user a clarifying question.

{\"tool\": \"memory_search\", \"query\": \"...\"}
  → Searches the user's memory store.

{\"tool\": \"memory_write\", \"content\": \"...\", \"category\": \"general\"}
  → Stores a new memory.

{\"tool\": \"done\", \"summary\": \"Task completed: ...\"}
  → Signals task completion. Always call this when finished.

{\"tool\": \"error\", \"message\": \"Cannot proceed because ...\"}
  → Signals an unrecoverable error.

RULES:
1. Always start with a screenshot to see the current browser state.
2. Return exactly ONE JSON tool call per message.
3. Be efficient — complete the task in as few steps as possible.
4. When done, always call the done tool with a clear summary.
"""


class SubAgentRuntime:
    """State container for a single running sub-agent."""

    def __init__(
        self,
        sub_id: str,
        instruction: str,
        model: str,
        parent_user_uid: str | None,
    ) -> None:
        self.sub_id = sub_id
        self.instruction = instruction
        self.model = model
        self.parent_user_uid = parent_user_uid
        self.cancel_event = asyncio.Event()
        self.steering_context: list[str] = []
        self.task: asyncio.Task[None] | None = None
        self.status: Literal["spawning", "running", "completed", "failed", "cancelled"] = "spawning"
        self.steps: list[str] = []       # summary of completed steps for UI


class SubAgentManager:
    """Manages the lifecycle of all sub-agents for a single parent WebSocket session."""

    def __init__(self) -> None:
        self._agents: dict[str, SubAgentRuntime] = {}

    def list_agents(self) -> list[dict[str, Any]]:
        return [
            {
                "sub_id": a.sub_id,
                "instruction": a.instruction,
                "model": a.model,
                "status": a.status,
                "step_count": len(a.steps),
            }
            for a in self._agents.values()
        ]

    def get(self, sub_id: str) -> SubAgentRuntime | None:
        return self._agents.get(sub_id)

    async def spawn(
        self,
        *,
        instruction: str,
        model: str,
        parent_user_uid: str | None,
        orchestrator: Any,  # AgentOrchestrator
        parent_settings: dict[str, Any],
        send_to_parent: Callable[[dict[str, Any]], Awaitable[None]],
        on_user_input: Callable[[str, list[str]], Awaitable[str]] | None,
    ) -> str:
        """Create and start a sub-agent. Returns sub_session_id."""
        sub_id = str(uuid4())
        runtime = SubAgentRuntime(
            sub_id=sub_id,
            instruction=instruction,
            model=model,
            parent_user_uid=parent_user_uid,
        )
        self._agents[sub_id] = runtime

        # Notify parent WS that sub-agent spawned
        await send_to_parent({
            "type": "subagent_spawned",
            "data": {
                "sub_id": sub_id,
                "instruction": instruction,
                "model": model,
            },
        })

        # Build sub-agent settings — inherit provider/key config, override model + system prompt
        sub_settings = {
            **parent_settings,
            "model": model,
            "system_instruction": SUBAGENT_SYSTEM_PROMPT,
        }

        async def _run() -> None:
            runtime.status = "running"
            try:
                await orchestrator.execute_task(
                    session_id=f"sub_{sub_id}",
                    instruction=instruction,
                    on_step=_make_step_handler(sub_id, runtime, send_to_parent),
                    on_frame=None,          # sub-agents don't stream frames
                    cancel_event=runtime.cancel_event,
                    steering_context=runtime.steering_context,
                    settings=sub_settings,
                    on_workflow_step=None,
                    user_uid=parent_user_uid,
                    on_user_input=on_user_input,
                    on_reasoning_delta=None,
                    is_subagent=True,       # enforces SUBAGENT_ALLOWED_TOOLS in executor
                )
                runtime.status = "completed"
            except asyncio.CancelledError:
                runtime.status = "cancelled"
                logger.info("Sub-agent %s cancelled", sub_id)
                raise
            except Exception as exc:  # noqa: BLE001
                runtime.status = "failed"
                logger.exception("Sub-agent %s failed: %s", sub_id, exc)
                await send_to_parent({
                    "type": "subagent_error",
                    "data": {"sub_id": sub_id, "message": str(exc)},
                })
            finally:
                await send_to_parent({
                    "type": "subagent_completed",
                    "data": {
                        "sub_id": sub_id,
                        "status": runtime.status,
                        "step_count": len(runtime.steps),
                    },
                })

        runtime.task = asyncio.create_task(_run())
        return sub_id

    async def send_message(self, sub_id: str, message: str) -> bool:
        """Inject a steering message into a running sub-agent. Returns False if not found."""
        agent = self._agents.get(sub_id)
        if not agent or agent.status not in ("spawning", "running"):
            return False
        agent.steering_context.append(message)
        return True

    async def cancel(self, sub_id: str) -> bool:
        """Cancel a specific sub-agent. Returns False if not found."""
        agent = self._agents.get(sub_id)
        if not agent:
            return False
        agent.cancel_event.set()
        if agent.task and not agent.task.done():
            agent.task.cancel()
            try:
                await agent.task
            except (asyncio.CancelledError, Exception):
                pass
        return True

    async def cancel_all(self) -> None:
        """Cancel all running sub-agents — called on parent WS disconnect."""
        for sub_id in list(self._agents.keys()):
            await self.cancel(sub_id)
        self._agents.clear()


def _make_step_handler(
    sub_id: str,
    runtime: SubAgentRuntime,
    send_to_parent: Callable[[dict[str, Any]], Awaitable[None]],
) -> Callable[[dict[str, Any]], Awaitable[None]]:
    """Build a step callback that forwards steps to the parent WS tagged with sub_id."""

    async def _on_step(step: dict[str, Any]) -> None:
        content = str(step.get("content", ""))
        runtime.steps.append(content)
        await send_to_parent({
            "type": "subagent_step",
            "data": {
                "sub_id": sub_id,
                "step": step,
                "step_index": len(runtime.steps) - 1,
            },
        })

    return _on_step
