"""Universal LLM navigator — provider-agnostic vision + tool-calling loop.

Replaces the Gemini ADK-only orchestrator for non-Gemini providers.
Works with any BaseProvider that supports vision (OpenAI, Anthropic, xAI,
OpenRouter, or Gemini via the providers adapter layer).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.providers.base import BaseProvider, ChatMessage

logger = logging.getLogger(__name__)

# ── System prompt for the navigator ──────────────────────────────────

SYSTEM_PROMPT = """\
You are Aegis, an AI agent that controls a real web browser to complete tasks.

You have access to these tools — call them by returning JSON in your response:

{"tool": "screenshot"}
  → Takes a screenshot and returns a base64-encoded PNG.  Use this to see the
    current state of the browser before deciding what to do next.

{"tool": "go_to_url", "url": "https://..."}
  → Navigates to the given URL.

{"tool": "click", "x": 500, "y": 300, "description": "submit button"}
  → Clicks at pixel coordinates (x, y). Use screenshot coordinates directly.
    Viewport is 1280×720.

{"tool": "type_text", "text": "hello world", "x": 400, "y": 200}
  → Types text, optionally clicking at (x, y) first to focus an input.

{"tool": "scroll", "direction": "down", "amount": 300}
  → Scrolls the page (direction: "up" or "down", amount in pixels).

{"tool": "go_back"}
  → Navigates browser history back one step.

{"tool": "wait", "seconds": 1.5}
  → Waits for the page to load or an animation to complete.

{"tool": "ask_user_input", "question": "What color scheme do you prefer?", "options": ["Blue", "Green", "Let me tell you"]}
  → Pauses the task and asks the user a question. Provide 2-4 short options.
    Always include an option like "Let me tell you" for free-form input.
    Returns the user's choice as a string.

{"tool": "memory_search", "query": "user's preferred writing style"}
  → Semantic search through stored memories. Returns up to 5 relevant entries.

{"tool": "memory_write", "content": "User prefers concise bullet-point summaries", "category": "preferences"}
  → Store a new memory. category: "preferences" | "facts" | "tasks" | "general"

{"tool": "memory_read", "memory_id": "uuid"}
  → Read a specific memory entry by ID.

{"tool": "memory_patch", "memory_id": "uuid", "content": "Updated content here"}
  → Update an existing memory entry.

{"tool": "cron_write", "name": "Daily report", "prompt": "Generate and send daily summary", "cron_expr": "0 9 * * *", "timezone": "UTC"}
  → Create a new scheduled automation. cron_expr is standard 5-field cron format.

{"tool": "cron_patch", "task_id": "uuid", "name": "Updated name", "cron_expr": "0 10 * * *"}
  → Update an existing scheduled task. Only include fields to change.

{"tool": "cron_delete", "task_id": "uuid"}
  → Delete a scheduled task permanently.

{"tool": "done", "summary": "Task completed: ..."}
  → Signals that the task is complete. Always call this when finished.

{"tool": "error", "message": "Cannot proceed because ..."}
  → Signals an unrecoverable error.

RULES:
1. Always start by taking a screenshot to see the current state.
2. Return exactly ONE JSON tool call per message — nothing else.
3. Use pixel coordinates from the screenshot (1280×720 viewport).
4. After each action, take a screenshot to verify the result before proceeding.
5. Be concise and efficient — complete tasks in as few steps as possible.
"""

# ── Tool executor ────────────────────────────────────────────────────

class UniversalToolExecutor:
    """Executes tool calls issued by the LLM and returns text results."""

    def __init__(
        self,
        executor: Any,
        user_uid: str | None = None,
        on_user_input: Callable[[str, list[str]], Awaitable[str]] | None = None,
    ) -> None:
        """executor: ActionExecutor instance from executor.py"""
        self._exe = executor
        self._last_screenshot: bytes | None = None
        self._user_uid = user_uid
        self._on_user_input = on_user_input

    async def run(self, tool_call: dict[str, Any]) -> tuple[str, bytes | None]:
        """Execute a tool and return (text_result, optional_screenshot_bytes)."""
        tool = tool_call.get("tool", "")
        screenshot: bytes | None = None

        try:
            if tool == "screenshot":
                screenshot = await self._exe.screenshot()
                self._last_screenshot = screenshot
                return "Screenshot captured.", screenshot

            elif tool == "go_to_url":
                url = str(tool_call.get("url", "")).strip()
                if not url:
                    return "Error: url is required.", None
                result = await self._exe.goto(url)
                return f"Navigated to {result['url']} — title: {result.get('title', '')}", None

            elif tool == "click":
                x = int(tool_call.get("x", 0))
                y = int(tool_call.get("y", 0))
                desc = str(tool_call.get("description", ""))
                result = await self._exe.click(x, y)
                suffix = f" ({desc})" if desc else ""
                return f"Clicked ({x}, {y}){suffix} — now at {result.get('url', '')}", None

            elif tool == "type_text":
                text = str(tool_call.get("text", ""))
                x = tool_call.get("x")
                y = tool_call.get("y")
                await self._exe.type_text(text, int(x) if x is not None else None, int(y) if y is not None else None)
                return f"Typed {len(text)} characters.", None

            elif tool == "scroll":
                direction = str(tool_call.get("direction", "down"))
                amount = int(tool_call.get("amount", 300))
                await self._exe.scroll(direction, amount)
                return f"Scrolled {direction} {amount}px.", None

            elif tool == "go_back":
                result = await self._exe.go_back()
                return f"Went back to {result.get('url', '')}", None

            elif tool == "wait":
                seconds = float(tool_call.get("seconds", 1.5))
                await asyncio.sleep(min(seconds, 10.0))
                return f"Waited {seconds:.1f}s.", None

            elif tool == "ask_user_input":
                question = str(tool_call.get("question", ""))
                options: list[str] = list(tool_call.get("options", []))
                if self._on_user_input:
                    answer = await self._on_user_input(question, options)
                    return f"User answered: {answer}", None
                return "No user input handler available — continuing without user input.", None

            elif tool == "memory_search":
                query = str(tool_call.get("query", ""))
                if not self._user_uid:
                    return "Memory tools require an authenticated user.", None
                try:
                    from backend.database import _session_factory
                    from backend.memory.service import MemoryService
                    if _session_factory is None:
                        return "Database not ready.", None
                    async with _session_factory() as session:
                        results = await MemoryService.recall(session, self._user_uid, query, limit=5)
                    if not results:
                        return "No relevant memories found.", None
                    lines = [f"[{r['id']}] ({r['category']}) {r['content']}" for r in results]
                    return "Found memories:\n" + "\n".join(lines), None
                except Exception as exc:  # noqa: BLE001
                    return f"memory_search error: {exc}", None

            elif tool == "memory_write":
                content = str(tool_call.get("content", ""))
                category = str(tool_call.get("category", "general"))
                if not self._user_uid:
                    return "Memory tools require an authenticated user.", None
                try:
                    from backend.database import _session_factory
                    from backend.memory.service import MemoryService
                    if _session_factory is None:
                        return "Database not ready.", None
                    async with _session_factory() as session:
                        entry = await MemoryService.store(session, self._user_uid, content, category=category)
                    return f"Memory stored with id={entry['id']}.", None
                except Exception as exc:  # noqa: BLE001
                    return f"memory_write error: {exc}", None

            elif tool == "memory_read":
                memory_id = str(tool_call.get("memory_id", ""))
                if not self._user_uid:
                    return "Memory tools require an authenticated user.", None
                try:
                    from backend.database import _session_factory
                    from backend.memory.service import MemoryService
                    if _session_factory is None:
                        return "Database not ready.", None
                    async with _session_factory() as session:
                        entry = await MemoryService.get_memory(session, memory_id, self._user_uid)
                    if not entry:
                        return f"Memory {memory_id} not found.", None
                    return f"Memory [{entry['id']}] ({entry['category']}): {entry['content']}", None
                except Exception as exc:  # noqa: BLE001
                    return f"memory_read error: {exc}", None

            elif tool == "memory_patch":
                memory_id = str(tool_call.get("memory_id", ""))
                content = tool_call.get("content")
                category = tool_call.get("category")
                if not self._user_uid:
                    return "Memory tools require an authenticated user.", None
                try:
                    from backend.database import _session_factory
                    from backend.memory.service import MemoryService
                    if _session_factory is None:
                        return "Database not ready.", None
                    async with _session_factory() as session:
                        updated = await MemoryService.update_memory(
                            session,
                            memory_id,
                            self._user_uid,
                            content=content,
                            category=category,
                        )
                    if not updated:
                        return f"Memory {memory_id} not found or not updated.", None
                    return f"Memory {memory_id} updated.", None
                except Exception as exc:  # noqa: BLE001
                    return f"memory_patch error: {exc}", None

            elif tool == "cron_write":
                name = str(tool_call.get("name", "Scheduled task"))
                prompt = str(tool_call.get("prompt", ""))
                cron_expr = str(tool_call.get("cron_expr", ""))
                timezone = str(tool_call.get("timezone", "UTC"))
                if not self._user_uid:
                    return "Cron tools require an authenticated user.", None
                try:
                    from backend.database import _session_factory, ScheduledTask
                    from backend.automation import _compute_next_run, _validate_cron
                    from uuid import uuid4 as _uuid4
                    if _session_factory is None:
                        return "Database not ready.", None
                    cron_expr = _validate_cron(cron_expr)
                    next_run = _compute_next_run(cron_expr, timezone)
                    async with _session_factory() as session:
                        task = ScheduledTask(
                            user_id=self._user_uid,
                            name=name,
                            prompt=prompt,
                            cron_expr=cron_expr,
                            timezone=timezone,
                            enabled=True,
                            next_run_at=next_run,
                            last_status="pending",
                            run_count=0,
                        )
                        session.add(task)
                        await session.commit()
                        await session.refresh(task)
                        task_id = task.id
                    return f"Cron task created with id={task_id}.", None
                except Exception as exc:  # noqa: BLE001
                    return f"cron_write error: {exc}", None

            elif tool == "cron_patch":
                task_id = str(tool_call.get("task_id", ""))
                if not self._user_uid:
                    return "Cron tools require an authenticated user.", None
                try:
                    from backend.database import _session_factory, ScheduledTask
                    from backend.automation import _compute_next_run, _validate_cron
                    if _session_factory is None:
                        return "Database not ready.", None
                    async with _session_factory() as session:
                        task = await session.get(ScheduledTask, task_id)
                        if not task or task.user_id != self._user_uid:
                            return f"Cron task {task_id} not found.", None
                        if "name" in tool_call:
                            task.name = str(tool_call["name"])
                        if "prompt" in tool_call:
                            task.prompt = str(tool_call["prompt"])
                        if "enabled" in tool_call:
                            task.enabled = bool(tool_call["enabled"])
                        if "timezone" in tool_call:
                            task.timezone = str(tool_call["timezone"])
                        if "cron_expr" in tool_call:
                            task.cron_expr = _validate_cron(str(tool_call["cron_expr"]))
                        task.next_run_at = _compute_next_run(task.cron_expr, task.timezone)
                        await session.commit()
                    return f"Cron task {task_id} updated.", None
                except Exception as exc:  # noqa: BLE001
                    return f"cron_patch error: {exc}", None

            elif tool == "cron_delete":
                task_id = str(tool_call.get("task_id", ""))
                if not self._user_uid:
                    return "Cron tools require an authenticated user.", None
                try:
                    from backend.database import _session_factory, ScheduledTask
                    if _session_factory is None:
                        return "Database not ready.", None
                    async with _session_factory() as session:
                        task = await session.get(ScheduledTask, task_id)
                        if not task or task.user_id != self._user_uid:
                            return f"Cron task {task_id} not found.", None
                        await session.delete(task)
                        await session.commit()
                    return f"Cron task {task_id} deleted.", None
                except Exception as exc:  # noqa: BLE001
                    return f"cron_delete error: {exc}", None

            elif tool in ("done", "error"):
                # Terminal tools — caller handles them
                return "", None

            else:
                return f"Unknown tool: {tool}", None

        except Exception as exc:  # noqa: BLE001
            logger.warning("Tool %s failed: %s", tool, exc)
            return f"Tool error ({tool}): {exc}", None


# ── Tool call parser ─────────────────────────────────────────────────

def _parse_tool_call(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from model output."""
    text = text.strip()
    # Try fenced code block first
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    # Try bare JSON object
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


# ── Main navigation loop ─────────────────────────────────────────────

MAX_STEPS = 40  # safety cap


async def run_universal_navigation(
    *,
    provider: BaseProvider,
    model: str,
    executor: Any,  # ActionExecutor
    instruction: str,
    on_step: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    on_frame: Callable[[str], Awaitable[None]] | None = None,
    cancel_event: asyncio.Event | None = None,
    steering_context: list[str] | None = None,
    on_workflow_step: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    on_user_input: Callable[[str, list[str]], Awaitable[str]] | None = None,
    user_uid: str | None = None,
) -> dict[str, Any]:
    """Run a vision+tool-calling navigation loop with any BaseProvider.

    Returns a result dict compatible with the Gemini ADK path.
    """
    tool_executor = UniversalToolExecutor(executor, user_uid=user_uid, on_user_input=on_user_input)
    messages: list[ChatMessage] = []
    steps: list[dict[str, Any]] = []
    parent_step_id: str | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    async def emit_step(content: str, step_type: str = "step") -> None:
        step_data = {"type": step_type, "content": content, "steering": []}
        steps.append(step_data)
        if on_step:
            await on_step(step_data)
        step_id = str(uuid4())
        if on_workflow_step:
            await on_workflow_step({
                "step_id": step_id,
                "parent_step_id": parent_step_id,
                "action": step_type,
                "description": content[:200],
                "status": "completed",
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "duration_ms": 300,
                "screenshot": None,
            })
        return step_id  # type: ignore[return-value]

    await emit_step(f"Starting task: {instruction}")

    # Initial user message
    messages.append(ChatMessage(role="system", content=SYSTEM_PROMPT))
    messages.append(ChatMessage(role="user", content=f"Task: {instruction}\n\nStart by taking a screenshot to see the current state of the browser."))

    for step_num in range(MAX_STEPS):
        # Check cancellation
        if cancel_event and cancel_event.is_set():
            return {"status": "interrupted", "instruction": instruction, "steps": steps}

        # Inject any steering notes
        if steering_context:
            notes = steering_context.copy()
            steering_context.clear()
            steer_text = "User steering note: " + "; ".join(notes)
            messages.append(ChatMessage(role="user", content=steer_text))
            await emit_step(steer_text, step_type="steer")

        # Call the LLM
        try:
            response = await provider.chat(
                messages,
                model=model,
                temperature=0.2,
                max_tokens=1024,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM call failed at step %d", step_num)
            return {"status": "failed", "instruction": instruction, "steps": steps, "error": str(exc), "input_tokens": total_input_tokens, "output_tokens": total_output_tokens}

        # Accumulate token usage
        if response.usage:
            total_input_tokens += response.usage.get("prompt_tokens", 0)
            total_output_tokens += response.usage.get("completion_tokens", 0)

        reply = response.content.strip()
        messages.append(ChatMessage(role="assistant", content=reply))

        # Parse tool call
        tool_call = _parse_tool_call(reply)
        if not tool_call:
            await emit_step(f"Model response (no tool call): {reply[:200]}")
            # If no tool call, nudge the model
            messages.append(ChatMessage(role="user", content="Please return a JSON tool call to continue."))
            continue

        tool_name = tool_call.get("tool", "unknown")

        # Handle terminal tools
        if tool_name == "done":
            summary = str(tool_call.get("summary", "Task completed."))
            await emit_step(summary, step_type="result")
            return {"status": "completed", "instruction": instruction, "steps": steps, "summary": summary, "input_tokens": total_input_tokens, "output_tokens": total_output_tokens}

        if tool_name == "error":
            error_msg = str(tool_call.get("message", "Unknown error."))
            await emit_step(f"Error: {error_msg}", step_type="error")
            return {"status": "failed", "instruction": instruction, "steps": steps, "error": error_msg, "input_tokens": total_input_tokens, "output_tokens": total_output_tokens}

        # Emit step info — user_input_request gets a special enriched step
        if tool_name == "ask_user_input":
            question = str(tool_call.get("question", ""))
            options: list[str] = list(tool_call.get("options", []))
            request_id = str(uuid4())
            tool_call["_request_id"] = request_id  # pass through to executor
            special_step: dict[str, Any] = {
                "type": "user_input_request",
                "content": f"[ask_user_input] {question}",
                "question": question,
                "options": options,
                "request_id": request_id,
                "steering": [],
            }
            steps.append(special_step)
            if on_step:
                await on_step(special_step)
        else:
            await emit_step(f"[{tool_name}] {json.dumps({k: v for k, v in tool_call.items() if k != 'tool'})[:120]}")

        # Execute tool
        result_text, screenshot_bytes = await tool_executor.run(tool_call)

        # Send frame to client if we captured a screenshot
        if screenshot_bytes and on_frame:
            b64 = base64.b64encode(screenshot_bytes).decode()
            await on_frame(b64)

        # Build next user message with result (and image if screenshot)
        if screenshot_bytes:
            follow_up = ChatMessage(
                role="user",
                content=f"Tool result: {result_text}\nHere is the current screenshot. Decide your next action.",
                images=[screenshot_bytes],
            )
        else:
            follow_up = ChatMessage(
                role="user",
                content=f"Tool result: {result_text}\nDecide your next action.",
            )
        messages.append(follow_up)

    # Reached step limit
    await emit_step("Reached maximum step limit without completing task.", step_type="error")
    return {"status": "failed", "instruction": instruction, "steps": steps, "error": "Max steps reached", "input_tokens": total_input_tokens, "output_tokens": total_output_tokens}
