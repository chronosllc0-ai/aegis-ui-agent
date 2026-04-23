"""Connectors-as-tools adapter for the always-on runtime.

Phase 4 of the always-on rewrite (`PLAN.md` §Phase 4). Every connector
that lives under :mod:`backend.connectors` — Notion, GitHub, Google
(Gmail + Drive + Calendar), Linear, Slack — already declares a
structured list of actions via :meth:`BaseConnector.list_actions`.
This module turns each action into an OpenAI Agents SDK
:class:`agents.FunctionTool` so the supervisor loop can invoke it
exactly like a native tool.

High-level shape
----------------

* :func:`load_connector_tools` — resolves the set of *active* user
  connections (``UserConnection.status == "active"``) and returns one
  :class:`FunctionTool` per connector ⨯ action combination.
* :func:`connector_tool_name` — tool-name builder locked to
  ``{connector_id}_{action_id}`` (single underscore) per PLAN.md §4.
* :func:`build_connector_tools_for_connection` — lower-level helper
  used by the loader and the tests.

Every tool call does a fresh database round-trip to pick up the latest
access token + rotate expired ones through the connector's
``refresh_tokens`` contract. This keeps long-running agent sessions
resilient to silent expiry without leaking per-tool state to the caller.

Tools return JSON text so the Agents SDK runner hands a structured
payload back to the model. Errors are surfaced as ``ERROR: …`` strings
so the model can recover gracefully without crashing the run loop.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from agents import FunctionTool, RunContextWrapper
from sqlalchemy import select

from backend.connectors import CONNECTOR_CATALOGUE, get_connector
from backend.connectors.base import BaseConnector, ConnectorAction

logger = logging.getLogger(__name__)

# Per-tool timeout for connector action invocations. Individual connectors
# can still use shorter timeouts inside their own httpx clients; this is the
# outer bound so a hung upstream never blocks the agent loop forever.
CONNECTOR_TOOL_TIMEOUT_SECONDS = 60

# Namespace separator for connector tools. MCP uses a double underscore
# (see :mod:`backend.runtime.tools.mcp_host`); connector tools stay on a
# *single* underscore per PLAN.md §4 so the model sees names like
# ``google_gmail_send`` and ``linear_create_issue``.
CONNECTOR_NAMESPACE_SEPARATOR = "_"

ConnectorLoader = Callable[[str], Awaitable[list[FunctionTool]]]
"""Async callable returning the agent tools available to ``user_uid``.

Phase 4 ships :func:`load_connector_tools` as the default loader; the
type alias exists so the runtime's :class:`DispatchConfig` can accept
alternative loaders in tests or multi-tenant deployments.
"""


def connector_tool_name(connector_id: str, action_id: str) -> str:
    """Return the canonical tool name for a connector action.

    The format is locked to ``{connector_id}_{action_id}`` (PLAN.md §4).
    Both segments keep their own internal underscores — e.g. Google's
    ``gmail_send`` action becomes ``google_gmail_send``.
    """
    cid = (connector_id or "").strip()
    aid = (action_id or "").strip()
    if not cid or not aid:
        raise ValueError(
            f"connector_tool_name requires both ids; got {connector_id!r}/{action_id!r}"
        )
    return f"{cid}{CONNECTOR_NAMESPACE_SEPARATOR}{aid}"


# ----------------------------------------------------------------------
# Token lookup / refresh helpers
# ----------------------------------------------------------------------


async def _load_connection_record(user_uid: str, connector_id: str):
    """Fetch the :class:`UserConnection` row or ``None``.

    Imported lazily so this module stays cheap at process start time.
    """
    from backend.database import UserConnection, _session_factory

    if _session_factory is None:
        return None, None
    async with _session_factory() as session:
        result = await session.execute(
            select(UserConnection).where(
                UserConnection.user_id == user_uid,
                UserConnection.connector_id == connector_id,
            )
        )
        connection = result.scalar_one_or_none()
        return connection, session


async def _get_fresh_access_token(
    user_uid: str,
    connector: BaseConnector,
) -> str | None:
    """Decrypt — and if necessary refresh — the user's access token.

    Returns ``None`` when the user has no active connection or when the
    token is expired and no refresh token is on file. Callers are
    expected to surface a friendly ``ERROR: …`` back to the model in
    those cases rather than raising.
    """
    from backend.database import UserConnection, _session_factory
    from backend.key_management import KeyManager
    from config import settings

    if _session_factory is None:
        return None
    km = KeyManager(settings.ENCRYPTION_SECRET)

    async with _session_factory() as session:
        result = await session.execute(
            select(UserConnection).where(
                UserConnection.user_id == user_uid,
                UserConnection.connector_id == connector.connector_id,
            )
        )
        connection = result.scalar_one_or_none()
        if connection is None or connection.status != "active":
            return None

        try:
            access_token = km.decrypt(connection.access_token_enc)
        except Exception:  # noqa: BLE001
            logger.warning(
                "connectors: failed to decrypt access token for %s/%s",
                user_uid,
                connector.connector_id,
            )
            connection.status = "expired"
            await session.commit()
            return None

        # Refresh on the way in when we know the token is expired.
        # SQLite returns naive datetimes even for TIMESTAMP WITH TIME
        # ZONE columns; Postgres returns aware values. Normalise to UTC
        # so the comparison works identically in both environments.
        now = datetime.now(timezone.utc)
        expires_at = connection.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at is not None and expires_at < now:
            if not connection.refresh_token_enc:
                connection.status = "expired"
                await session.commit()
                return None
            try:
                refresh_token = km.decrypt(connection.refresh_token_enc)
                new_tokens = await connector.refresh_tokens(refresh_token)
                connection.access_token_enc = km.encrypt(new_tokens.access_token)
                if new_tokens.refresh_token:
                    connection.refresh_token_enc = km.encrypt(new_tokens.refresh_token)
                if new_tokens.expires_in:
                    connection.expires_at = now + timedelta(seconds=new_tokens.expires_in)
                connection.status = "active"
                await session.commit()
                access_token = new_tokens.access_token
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "connectors: token refresh failed for %s/%s: %s",
                    user_uid,
                    connector.connector_id,
                    exc,
                )
                connection.status = "expired"
                await session.commit()
                return None

        return access_token


# ----------------------------------------------------------------------
# Tool factory
# ----------------------------------------------------------------------


def _action_params_schema(action: ConnectorAction) -> dict[str, Any]:
    """Turn the connector's free-form ``parameters`` dict into a
    JSON-schema object the Agents SDK accepts.

    Connector authors currently declare parameters as a flat
    ``{name: "type annotation"}`` dict (e.g. ``{"to": "string"}``).
    We translate that to a JSON-Schema ``object`` with ``string``
    properties by default — structured enough for the model to fill the
    slots, loose enough that unusual types (ints, datetimes) still
    round-trip through the generic ``Any`` pipeline.

    ``strict_json_schema`` is disabled on the tool, so optional fields
    and unknown properties remain permissible at call time.
    """
    properties: dict[str, Any] = {}
    for key, ptype in (action.parameters or {}).items():
        descriptor = str(ptype).strip().lower()
        if "int" in descriptor:
            prop_type: str = "integer"
        elif "bool" in descriptor:
            prop_type = "boolean"
        elif "float" in descriptor or "number" in descriptor:
            prop_type = "number"
        elif "object" in descriptor or "dict" in descriptor:
            prop_type = "object"
        elif "array" in descriptor or "list" in descriptor:
            prop_type = "array"
        else:
            prop_type = "string"
        properties[key] = {
            "type": prop_type,
            "description": f"{key} ({ptype})",
        }

    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }


def _serialize_connector_result(result: Any) -> str:
    """Collapse a connector's return value into model-readable text.

    Connectors typically return a plain ``dict``; we JSON-encode that so
    the agent can read it back out of context. Non-dict returns are
    stringified through ``json.dumps`` with ``default=str`` to survive
    datetime / UUID / bytes payloads without crashing the runner.
    """
    try:
        return json.dumps(result, default=str, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return str(result)


def _build_single_tool(
    *,
    connector_id: str,
    display_name: str,
    action: ConnectorAction,
    user_uid: str,
) -> FunctionTool:
    """Wrap one connector action as an Agents SDK tool.

    A fresh connector instance + access token are resolved on each
    invocation — this keeps token rotation correct for long-lived
    supervisors and avoids leaking decrypted secrets into closures that
    outlive the call.
    """
    tool_name = connector_tool_name(connector_id, action.id)
    description_suffix = f" [{display_name} · {action.category}]"
    description = (action.description or action.name).strip() + description_suffix
    schema = _action_params_schema(action)

    async def _invoke(run_ctx: RunContextWrapper[Any], args_json: str) -> str:
        try:
            arguments = json.loads(args_json) if args_json else {}
        except json.JSONDecodeError as exc:
            return f"ERROR: invalid JSON arguments for {tool_name}: {exc}"
        if not isinstance(arguments, dict):
            return f"ERROR: {tool_name} arguments must be a JSON object"

        try:
            connector = get_connector(connector_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("connectors: failed to instantiate %s", connector_id)
            return f"ERROR: connector {connector_id} unavailable: {exc}"

        access_token = await _get_fresh_access_token(user_uid, connector)
        if not access_token:
            return (
                f"ERROR: no active {display_name} connection for this user. "
                f"Ask the user to connect {display_name} first."
            )

        import asyncio  # local import to keep module import cheap

        try:
            result = await asyncio.wait_for(
                connector.execute_action(action.id, arguments, access_token),
                timeout=CONNECTOR_TOOL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return (
                f"ERROR: {tool_name} timed out after "
                f"{CONNECTOR_TOOL_TIMEOUT_SECONDS}s"
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "connectors: action failed name=%s connector=%s",
                tool_name,
                connector_id,
            )
            return f"ERROR: {tool_name} raised {type(exc).__name__}: {exc}"

        return _serialize_connector_result(result)

    return FunctionTool(
        name=tool_name,
        description=description,
        params_json_schema=schema,
        on_invoke_tool=_invoke,
        strict_json_schema=False,
    )


def build_connector_tools_for_connection(
    connector_id: str,
    user_uid: str,
) -> list[FunctionTool]:
    """Return the agent tools for one connector/user pair.

    This is the piece the tests exercise directly. ``load_connector_tools``
    (below) loops over every active connection for a user.

    Unknown connector IDs (not in :data:`CONNECTOR_CATALOGUE`) yield an
    empty list instead of raising — the runtime should never lose a
    dispatch because a single stale row points at a connector that was
    deleted in code.
    """
    if connector_id not in CONNECTOR_CATALOGUE:
        logger.warning(
            "connectors: skipping unknown connector_id=%s for user=%s",
            connector_id,
            user_uid,
        )
        return []
    try:
        connector = get_connector(connector_id)
    except Exception:  # noqa: BLE001
        logger.exception(
            "connectors: failed to instantiate connector %s for user %s",
            connector_id,
            user_uid,
        )
        return []
    display_name = CONNECTOR_CATALOGUE[connector_id].get("name", connector_id)
    actions = connector.list_actions()
    return [
        _build_single_tool(
            connector_id=connector_id,
            display_name=display_name,
            action=action,
            user_uid=user_uid,
        )
        for action in actions
    ]


async def load_connector_tools(user_uid: str) -> list[FunctionTool]:
    """Primary entry point consumed by the runtime.

    Returns one :class:`FunctionTool` per *active* connection × action
    for ``user_uid``. When the database layer is not initialised (e.g.
    a unit test running without the global ``_session_factory``) the
    function returns an empty list — callers should treat this as "no
    connectors available" rather than a hard failure.
    """
    if not user_uid:
        return []

    from backend.database import UserConnection, _session_factory

    if _session_factory is None:
        return []

    async with _session_factory() as session:
        result = await session.execute(
            select(UserConnection.connector_id).where(
                UserConnection.user_id == user_uid,
                UserConnection.status == "active",
            )
        )
        connector_ids: list[str] = [row[0] for row in result.all() if row and row[0]]

    tools: list[FunctionTool] = []
    seen: set[str] = set()
    for connector_id in connector_ids:
        if connector_id in seen:
            continue
        seen.add(connector_id)
        tools.extend(build_connector_tools_for_connection(connector_id, user_uid))
    return tools


__all__ = [
    "CONNECTOR_NAMESPACE_SEPARATOR",
    "CONNECTOR_TOOL_TIMEOUT_SECONDS",
    "ConnectorLoader",
    "build_connector_tools_for_connection",
    "connector_tool_name",
    "load_connector_tools",
]
