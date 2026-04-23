"""MCP host for the always-on runtime.

This module wraps the official ``mcp`` Python SDK so that MCP servers —
stdio subprocesses, streamable-HTTP endpoints, or legacy SSE endpoints —
can be exposed to the OpenAI Agents SDK runner alongside the native
tools in :mod:`backend.runtime.tools.native`.

High-level shape
----------------

* :class:`MCPServerSpec` — declarative description of how to reach one
  MCP server (transport + endpoint/command/env/headers, plus a stable
  ``server_id``).

* :class:`MCPToolProvider` — the stateful piece. One provider per user
  (keyed by ``owner_uid``) per :class:`backend.runtime.supervisor.SessionSupervisor`.
  Responsibilities:

  - Spawn the MCP session lazily on first use, reuse it for the lifetime
    of the supervisor.
  - Run a `tools/list` call, turn the result into
    :class:`agents.FunctionTool` instances, and namespace tool names as
    ``{server_id}__{tool_name}`` (double underscore) per PLAN.md §4.
  - Tear all sessions down cleanly on :meth:`MCPToolProvider.aclose`.

* :func:`default_server_specs` — loads the built-in default-on MCP
  servers (Playwright today) based on env flags so Phase 3's
  "fresh user with Playwright MCP enabled can run `go_to_url` +
  `screenshot`" acceptance criterion can be wired into
  :mod:`backend.runtime.agent_loop`.

* :func:`scan_mcp_server` — replacement for the deprecated
  :func:`backend.mcp.transport.scan_mcp_tools`. Dials a real server,
  calls ``tools/list`` and returns the serialized manifest + status.
  Used by ``/api/connections/mcp/servers/{id}/scan``.

Design constraints:

* Real SDK usage only. No fixture manifests in production paths.
* Lifetime: the provider is *async-context-safe* (it is implemented on
  top of :class:`contextlib.AsyncExitStack`). Callers must call
  :meth:`aclose` (typically through :meth:`SessionSupervisor.stop`).
* Zero cross-talk between users: each provider instance is isolated.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Iterable, Optional

from agents import FunctionTool, RunContextWrapper

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
import mcp.types as mcp_types

logger = logging.getLogger(__name__)


TOOL_NAMESPACE_SEPARATOR = "__"
"""Separator used when building fully-qualified MCP tool names.

Locked in PLAN.md §4 — double underscore so model output parsers that
treat ``.`` or ``-`` specially don't choke. The matching
:func:`split_namespaced_tool_name` helper is exported for consumers
(logging, dispatcher) that need to inspect the server/tool parts.
"""


MCP_DEFAULT_CALL_TIMEOUT = 120.0
"""Maximum seconds a single MCP tool call may take before the runner
aborts it. Matches the legacy MCPClient's ``asyncio.wait_for`` bound,
scaled up for browser tools that may block on page loads."""


def namespaced_tool_name(server_id: str, tool_name: str) -> str:
    """Join ``server_id`` + ``tool_name`` using the locked separator."""
    return f"{server_id}{TOOL_NAMESPACE_SEPARATOR}{tool_name}"


def split_namespaced_tool_name(fqn: str) -> tuple[str, str] | None:
    """Inverse of :func:`namespaced_tool_name`.

    Returns ``(server_id, tool_name)`` or ``None`` if the separator is
    absent (native tools will hit this branch).
    """
    if TOOL_NAMESPACE_SEPARATOR not in fqn:
        return None
    server_id, _, tool_name = fqn.partition(TOOL_NAMESPACE_SEPARATOR)
    return server_id, tool_name


# ----------------------------------------------------------------------
# Server specs
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class MCPServerSpec:
    """Declarative configuration for one MCP server connection."""

    server_id: str
    """Stable identifier. Used in tool namespacing and in log lines."""

    transport: str
    """``stdio`` | ``http`` | ``sse``."""

    command: Optional[str] = None
    """Executable path for ``stdio`` transport."""

    args: tuple[str, ...] = ()
    """CLI args for ``stdio`` transport."""

    env: dict[str, str] = field(default_factory=dict)
    """Extra env vars for ``stdio`` subprocess. ``PATH`` is always
    inherited from the parent env."""

    endpoint: Optional[str] = None
    """URL for ``http`` / ``sse`` transports."""

    headers: dict[str, str] = field(default_factory=dict)
    """HTTP headers (e.g. Authorization)."""

    display_name: Optional[str] = None
    """Optional human-readable label for logging / UI."""

    def validate(self) -> None:
        t = (self.transport or "").lower()
        if t not in {"stdio", "http", "sse"}:
            raise ValueError(f"unsupported MCP transport: {self.transport!r}")
        if t == "stdio":
            if not self.command:
                raise ValueError("stdio MCP server requires a command")
        else:
            if not self.endpoint:
                raise ValueError(f"{t} MCP server requires an endpoint")


def _clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build a child-process env: inherit PATH + minimal, then overlay."""
    keep_keys = (
        "PATH",
        "HOME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "PYTHONPATH",
        "NODE_PATH",
        "NODE_OPTIONS",
    )
    env: dict[str, str] = {k: os.environ[k] for k in keep_keys if k in os.environ}
    if extra:
        env.update(extra)
    return env


# ----------------------------------------------------------------------
# Session manager
# ----------------------------------------------------------------------


class _MCPSessionHandle:
    """Holds a live :class:`mcp.ClientSession` + its transport streams.

    The client session and the underlying transport context manager are
    entered through a per-server :class:`AsyncExitStack` so we can tear
    them down deterministically on ``close()``.
    """

    def __init__(self, spec: MCPServerSpec) -> None:
        self.spec = spec
        self._stack: contextlib.AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._init_result: mcp_types.InitializeResult | None = None
        self._lock = asyncio.Lock()

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError(
                f"MCP session for {self.spec.server_id!r} is not open yet"
            )
        return self._session

    async def ensure_open(self) -> ClientSession:
        if self._session is not None:
            return self._session
        async with self._lock:
            if self._session is not None:
                return self._session
            stack = contextlib.AsyncExitStack()
            try:
                streams = await _enter_transport(stack, self.spec)
                session = await stack.enter_async_context(
                    ClientSession(streams[0], streams[1])
                )
                self._init_result = await session.initialize()
                self._session = session
                self._stack = stack
                logger.info(
                    "mcp_host: opened session server_id=%s transport=%s",
                    self.spec.server_id,
                    self.spec.transport,
                )
                return session
            except BaseException:
                with contextlib.suppress(Exception):
                    await stack.aclose()
                raise

    async def close(self) -> None:
        stack = self._stack
        self._stack = None
        self._session = None
        self._init_result = None
        if stack is not None:
            try:
                await stack.aclose()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "mcp_host: error closing session server_id=%s",
                    self.spec.server_id,
                )


async def _enter_transport(
    stack: contextlib.AsyncExitStack,
    spec: MCPServerSpec,
) -> tuple[Any, Any]:
    """Open the MCP transport and return ``(read_stream, write_stream)``.

    The underlying SDK context managers may return 2- or 3-tuples
    (streamable HTTP returns a session id accessor too); we always
    normalize to the 2-tuple the :class:`ClientSession` constructor
    expects.
    """
    transport = spec.transport.lower()
    if transport == "stdio":
        params = StdioServerParameters(
            command=spec.command or "",
            args=list(spec.args),
            env=_clean_env(spec.env),
        )
        streams = await stack.enter_async_context(stdio_client(params))
    elif transport == "http":
        streams = await stack.enter_async_context(
            streamablehttp_client(
                url=spec.endpoint or "",
                headers=dict(spec.headers) if spec.headers else None,
            )
        )
    elif transport == "sse":
        streams = await stack.enter_async_context(
            sse_client(
                url=spec.endpoint or "",
                headers=dict(spec.headers) if spec.headers else None,
            )
        )
    else:
        raise ValueError(f"unsupported MCP transport: {transport!r}")

    # Both stdio_client / sse_client yield 2-tuples; streamablehttp yields
    # (read, write, session_id_cb). Keep only the streams.
    if len(streams) >= 2:
        return streams[0], streams[1]
    raise RuntimeError(f"MCP transport returned unexpected streams: {streams!r}")


# ----------------------------------------------------------------------
# Tool adapter
# ----------------------------------------------------------------------


def _ensure_object_schema(raw: Any) -> dict[str, Any]:
    """Normalize an MCP tool's inputSchema into a dict the Agents SDK
    accepts.

    Servers sometimes send ``None`` or missing schemas; we fall back to
    an empty object schema with ``additionalProperties: true`` so the
    runner can still invoke the tool.
    """
    if isinstance(raw, dict):
        schema = dict(raw)
    else:
        schema = {}
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    # The Agents SDK's strict-JSON mode expects ``additionalProperties:
    # false`` and ``required`` listing every property. MCP servers rarely
    # produce such schemas; relax strictness on a per-tool basis instead
    # of mutating the schema.
    return schema


def _render_content_block(block: Any) -> tuple[str, dict[str, Any] | None]:
    """Return a (text_fragment, attachment_record) pair for one block.

    ``attachment_record`` is a structured dict (image base64, resource
    uri, etc.) that downstream observers can surface; the text fragment
    is what the model actually reads in the next turn.
    """
    if isinstance(block, mcp_types.TextContent):
        return block.text or "", None
    if isinstance(block, mcp_types.ImageContent):
        summary = f"[image:{block.mimeType or 'unknown'}]"
        record = {
            "type": "image",
            "mime_type": block.mimeType,
            "data_base64": block.data,
        }
        return summary, record
    if isinstance(block, mcp_types.AudioContent):
        summary = f"[audio:{block.mimeType or 'unknown'}]"
        record = {
            "type": "audio",
            "mime_type": block.mimeType,
            "data_base64": block.data,
        }
        return summary, record
    # Fallback: stringify. This covers embedded resource + future types.
    try:
        payload = block.model_dump(mode="json")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        payload = {"repr": repr(block)}
    return json.dumps(payload, default=str), {"type": "other", "payload": payload}


def _serialize_tool_result(result: mcp_types.CallToolResult) -> str:
    """Turn a CallToolResult into a string the Agents SDK can hand to
    the model.

    We collapse every content block into text, preserving a trailing
    JSON note for non-text content so the model knows what it saw
    without bloating prompts with base64.
    """
    parts: list[str] = []
    attachments: list[dict[str, Any]] = []
    for block in result.content or []:
        text, attachment = _render_content_block(block)
        if text:
            parts.append(text)
        if attachment is not None:
            attachments.append(attachment)

    body = "\n".join(p for p in parts if p).strip()
    if result.isError:
        body = f"ERROR: {body or 'MCP tool reported an error.'}"

    payload: dict[str, Any] = {}
    structured = getattr(result, "structuredContent", None)
    if structured:
        payload["structured"] = structured
    if attachments:
        payload["attachments"] = attachments
    if payload:
        suffix = json.dumps(payload, default=str)
        if body:
            return f"{body}\n\n<mcp-meta>{suffix}</mcp-meta>"
        return f"<mcp-meta>{suffix}</mcp-meta>"
    return body or "(empty result)"


def _make_tool(
    session_handle: _MCPSessionHandle,
    tool: mcp_types.Tool,
) -> FunctionTool:
    """Build a FunctionTool that proxies to ``session.call_tool``.

    The returned callable re-enters ``session_handle.ensure_open`` on
    every invocation; if the session died between calls it will be
    re-spawned transparently (handled by the caller via
    :meth:`MCPToolProvider.refresh`, not here — here we assume the
    session is reused for the supervisor lifetime).
    """
    fq_name = namespaced_tool_name(session_handle.spec.server_id, tool.name)
    description = (tool.description or f"MCP tool {tool.name}").strip()
    params_schema = _ensure_object_schema(tool.inputSchema)

    async def _invoke(run_ctx: RunContextWrapper[Any], args_json: str) -> str:
        try:
            arguments = json.loads(args_json) if args_json else {}
        except json.JSONDecodeError as exc:
            return f"ERROR: invalid JSON arguments for {fq_name}: {exc}"
        if not isinstance(arguments, dict):
            return f"ERROR: {fq_name} arguments must be a JSON object"

        session = await session_handle.ensure_open()
        try:
            result = await asyncio.wait_for(
                session.call_tool(tool.name, arguments),
                timeout=MCP_DEFAULT_CALL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return f"ERROR: MCP tool {fq_name} timed out after {MCP_DEFAULT_CALL_TIMEOUT}s"
        except Exception as exc:  # noqa: BLE001
            logger.exception("mcp_host: tool call failed name=%s", fq_name)
            return f"ERROR: MCP tool {fq_name} raised {type(exc).__name__}: {exc}"
        return _serialize_tool_result(result)

    return FunctionTool(
        name=fq_name,
        description=description,
        params_json_schema=params_schema,
        on_invoke_tool=_invoke,
        strict_json_schema=False,
    )


# ----------------------------------------------------------------------
# Provider
# ----------------------------------------------------------------------


SpecLoader = Callable[[str | None], Awaitable[list[MCPServerSpec]]]
"""Async callable that returns the MCP servers configured for a user.

Phase 3 ships a built-in loader backed by :func:`default_server_specs`.
Phase 4+ will extend this to pull user-registered servers from Postgres
(:class:`backend.connections.models.MCPServerConfig`).
"""


@dataclass
class ScanReport:
    """Serializable summary of a server scan."""

    ok: bool
    server_id: str
    transport: str
    tools: list[dict[str, Any]]
    message: str
    error: Optional[str] = None
    tested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MCPToolProvider:
    """Per-user registry of live MCP sessions + their Agents SDK tools.

    Lifetime:
        * Instantiated once per :class:`SessionSupervisor`.
        * :meth:`get_tools` lazily opens every configured server on
          first call; subsequent calls reuse the same
          :class:`ClientSession` objects.
        * :meth:`aclose` must be called when the supervisor stops (Phase
          2 wires this via :meth:`SessionSupervisor.stop`).

    Concurrency:
        * :meth:`get_tools` is protected by a single lock to avoid
          racing two dispatch-hook invocations both trying to spawn the
          same stdio subprocess.
    """

    def __init__(
        self,
        *,
        owner_uid: str | None,
        spec_loader: SpecLoader | None = None,
        specs: Iterable[MCPServerSpec] | None = None,
    ) -> None:
        self.owner_uid = owner_uid
        self._spec_loader = spec_loader
        self._static_specs: tuple[MCPServerSpec, ...] = tuple(specs or ())
        self._handles: dict[str, _MCPSessionHandle] = {}
        self._tools_cache: list[FunctionTool] | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    async def _resolve_specs(self) -> list[MCPServerSpec]:
        if self._static_specs:
            return list(self._static_specs)
        if self._spec_loader is None:
            return list(default_server_specs())
        return list(await self._spec_loader(self.owner_uid))

    async def get_tools(self) -> list[FunctionTool]:
        """Return the list of Agents SDK tools exported by every
        configured MCP server, spawning sessions on first call."""
        if self._closed:
            raise RuntimeError("MCPToolProvider is closed")
        if self._tools_cache is not None:
            return list(self._tools_cache)
        async with self._lock:
            if self._tools_cache is not None:
                return list(self._tools_cache)
            specs = await self._resolve_specs()
            tools: list[FunctionTool] = []
            had_failures = False
            for spec in specs:
                try:
                    spec.validate()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "mcp_host: skipping invalid spec %s: %s",
                        spec.server_id,
                        exc,
                    )
                    # Invalid specs are a permanent configuration bug,
                    # not a transient failure — it's safe to keep caching
                    # around them. Don't flip ``had_failures`` for these.
                    continue
                # Reuse an already-open handle when retrying after a
                # partial failure — otherwise we'd orphan the previous
                # stdio subprocess + its anyio task group and trip a
                # cross-task cancel-scope error at teardown.
                handle = self._handles.get(spec.server_id) or _MCPSessionHandle(spec)
                try:
                    session = await handle.ensure_open()
                    listing = await session.list_tools()
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "mcp_host: failed to initialize server %s",
                        spec.server_id,
                    )
                    # Only close if this handle isn't already tracked;
                    # an already-tracked handle means a previous call
                    # succeeded and the failure is on this round only.
                    if self._handles.get(spec.server_id) is not handle:
                        await handle.close()
                    had_failures = True
                    continue
                self._handles[spec.server_id] = handle
                for mcp_tool in listing.tools or []:
                    tools.append(_make_tool(handle, mcp_tool))
            # Only memoise a clean load. If any server failed (network
            # blip, subprocess crash, …), leave ``_tools_cache`` unset so
            # the next dispatch retries the handshake. We still return
            # the successful tools so in-flight turns keep working with
            # whatever loaded.
            if not had_failures:
                self._tools_cache = tools
            return list(tools)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._tools_cache = None
        for handle in list(self._handles.values()):
            await handle.close()
        self._handles.clear()

    # ------------------------------------------------------------------
    # Scan (ad-hoc, no caching) — replacement for ``scan_mcp_tools``.
    # ------------------------------------------------------------------

    async def scan(self, user_uid: str | None = None) -> list[ScanReport]:
        """Scan every configured server for this user and return reports.

        Does *not* reuse live sessions — each scan opens a fresh session,
        lists tools, and tears it down. This makes scanning safe to run
        from HTTP handlers without interfering with an active supervisor.
        """
        reports: list[ScanReport] = []
        owner = user_uid if user_uid is not None else self.owner_uid
        if self._spec_loader is not None:
            specs = list(await self._spec_loader(owner))
        elif self._static_specs:
            specs = list(self._static_specs)
        else:
            specs = list(default_server_specs())
        for spec in specs:
            reports.append(await scan_mcp_server(spec))
        return reports


async def scan_mcp_server(spec: MCPServerSpec) -> ScanReport:
    """One-shot: spawn a session, call ``tools/list``, tear down."""
    try:
        spec.validate()
    except Exception as exc:  # noqa: BLE001
        return ScanReport(
            ok=False,
            server_id=spec.server_id,
            transport=spec.transport,
            tools=[],
            message=f"Invalid MCP config: {exc}",
            error=str(exc),
        )

    stack = contextlib.AsyncExitStack()
    try:
        streams = await _enter_transport(stack, spec)
        session = await stack.enter_async_context(ClientSession(streams[0], streams[1]))
        await session.initialize()
        listing = await session.list_tools()
        tools_manifest = [
            {
                "name": t.name,
                "description": (t.description or "").strip(),
                "inputSchema": t.inputSchema or {"type": "object", "properties": {}},
            }
            for t in (listing.tools or [])
        ]
        return ScanReport(
            ok=True,
            server_id=spec.server_id,
            transport=spec.transport,
            tools=tools_manifest,
            message=f"Discovered {len(tools_manifest)} tools via {spec.transport.upper()}.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("mcp_host: scan failed for %s", spec.server_id)
        return ScanReport(
            ok=False,
            server_id=spec.server_id,
            transport=spec.transport,
            tools=[],
            message=f"Scan failed: {type(exc).__name__}: {exc}",
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        with contextlib.suppress(Exception):
            await stack.aclose()


# ----------------------------------------------------------------------
# Default-on servers (Playwright MCP, Browser MCP opt-in)
# ----------------------------------------------------------------------


PLAYWRIGHT_MCP_ENV_FLAG = "PLAYWRIGHT_MCP_ENABLED"
"""When unset, defaults to *true* in :func:`default_server_specs` so
fresh users get browser navigation tools by default per PLAN.md §Phase 3.
Operators can force-disable by setting it to ``0`` / ``false``."""

PLAYWRIGHT_MCP_COMMAND_ENV = "PLAYWRIGHT_MCP_COMMAND"
"""Override the command used to spawn Playwright MCP. Defaults to
``npx`` (``@playwright/mcp``). Used in CI to point at a bundled path."""

BROWSERMCP_ENV_FLAG = "BROWSERMCP_ENABLED"
"""Opt-in flag for the `@browsermcp/mcp` stdio subprocess. Phase 3
selects option (a) from PLAN.md §4 — bundled server, off by default."""

BROWSERMCP_COMMAND_ENV = "BROWSERMCP_COMMAND"


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def resolve_playwright_mcp_command() -> list[str] | None:
    """Return the argv used to spawn Playwright MCP, or ``None``.

    Order of resolution:

    1. ``PLAYWRIGHT_MCP_COMMAND`` env — honored verbatim (space split).
    2. ``npx`` on PATH → ``["npx", "-y", "@playwright/mcp@latest"]``.

    ``None`` when neither is available — callers skip the server.
    """
    override = os.environ.get(PLAYWRIGHT_MCP_COMMAND_ENV, "").strip()
    if override:
        parts = override.split()
        exe = parts[0]
        if shutil.which(exe) or os.path.exists(exe):
            return parts
    if shutil.which("npx"):
        return ["npx", "-y", "@playwright/mcp@latest"]
    return None


def resolve_browsermcp_command() -> list[str] | None:
    """Return the argv used to spawn ``@browsermcp/mcp``, or ``None``."""
    override = os.environ.get(BROWSERMCP_COMMAND_ENV, "").strip()
    if override:
        parts = override.split()
        exe = parts[0]
        if shutil.which(exe) or os.path.exists(exe):
            return parts
    if shutil.which("npx"):
        return ["npx", "-y", "@browsermcp/mcp@latest"]
    return None


def default_server_specs() -> list[MCPServerSpec]:
    """Return the default-on MCP server specs derived from env flags.

    * Playwright MCP is enabled unless ``PLAYWRIGHT_MCP_ENABLED`` is
      explicitly falsey **and** the binary is resolvable. If the binary
      is missing we silently skip the server (callers log).
    * Browser MCP is opt-in via ``BROWSERMCP_ENABLED`` per PLAN.md §4
      option (a).
    """
    specs: list[MCPServerSpec] = []
    if _env_truthy(PLAYWRIGHT_MCP_ENV_FLAG, default=True):
        argv = resolve_playwright_mcp_command()
        if argv:
            specs.append(
                MCPServerSpec(
                    server_id="playwright",
                    transport="stdio",
                    command=argv[0],
                    args=tuple(argv[1:]),
                    display_name="Playwright MCP",
                )
            )
        else:
            logger.info(
                "mcp_host: PLAYWRIGHT_MCP_ENABLED=true but no npx/override on PATH; skipping",
            )
    if _env_truthy(BROWSERMCP_ENV_FLAG, default=False):
        argv = resolve_browsermcp_command()
        if argv:
            specs.append(
                MCPServerSpec(
                    server_id="browsermcp",
                    transport="stdio",
                    command=argv[0],
                    args=tuple(argv[1:]),
                    display_name="Browser MCP",
                )
            )
        else:
            logger.info(
                "mcp_host: BROWSERMCP_ENABLED=true but no npx/override on PATH; skipping",
            )
    return specs


__all__ = [
    "TOOL_NAMESPACE_SEPARATOR",
    "MCPServerSpec",
    "MCPToolProvider",
    "ScanReport",
    "default_server_specs",
    "namespaced_tool_name",
    "resolve_browsermcp_command",
    "resolve_playwright_mcp_command",
    "scan_mcp_server",
    "split_namespaced_tool_name",
    # env flag names exported for tests
    "PLAYWRIGHT_MCP_ENV_FLAG",
    "PLAYWRIGHT_MCP_COMMAND_ENV",
    "BROWSERMCP_ENV_FLAG",
    "BROWSERMCP_COMMAND_ENV",
]
