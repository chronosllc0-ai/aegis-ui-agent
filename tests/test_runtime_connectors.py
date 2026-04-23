"""Phase 4 tests — connectors as agent tools.

Covers :mod:`backend.runtime.tools.connectors`:

* Tool-name canonicalisation (``{connector_id}_{action_id}``).
* Parameter-schema translation from the flat connector
  ``{name: "type"}`` dict to JSON-Schema.
* Tool-list construction per connector (Notion + Google + GitHub +
  Linear + Slack).
* Dispatch path: a tool invocation re-reads the DB, decrypts the
  token, refreshes if expired, and calls
  :meth:`BaseConnector.execute_action`.
* No-connection error path (active connection missing).
* Refresh-on-expiry: expired token triggers ``refresh_tokens`` and the
  new access token is written back to the database.

We exercise everything against an in-memory SQLite database bound
directly via ``backend.database._session_factory`` — no FastAPI, no
global service wiring.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

# Set encryption secret BEFORE importing config/key_management — the
# settings module reads the env once at import time.
os.environ.setdefault("ENCRYPTION_SECRET", "test-secret-for-connectors-phase4")

from agents import FunctionTool  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend import database as db  # noqa: E402
from backend.connectors.base import ConnectorAction, OAuthTokens  # noqa: E402
from backend.database import Base, User, UserConnection  # noqa: E402
from backend.key_management import KeyManager  # noqa: E402
from backend.runtime.tools import connectors as connectors_mod  # noqa: E402
from backend.runtime.tools.connectors import (  # noqa: E402
    build_connector_tools_for_connection,
    connector_tool_name,
    load_connector_tools,
)
from config import settings  # noqa: E402


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def session_factory(monkeypatch):
    """Spin up an in-memory SQLite + bind ``db._session_factory``.

    The production code pulls ``_session_factory`` lazily via
    ``from backend.database import _session_factory``; we monkeypatch
    the module attribute so every production code-path sees the test
    database. Cleanup drops all tables so tests stay hermetic.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run(_setup())

    monkeypatch.setattr(db, "_session_factory", factory)
    # The connectors module imports ``_session_factory`` lazily inside
    # its helper functions, so patching ``backend.database`` is enough.
    yield factory

    async def _teardown() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    _run(_teardown())


async def _seed_user(factory: async_sessionmaker[AsyncSession], uid: str) -> None:
    async with factory() as session:
        session.add(
            User(
                uid=uid,
                email=f"{uid}@example.com",
                name=uid,
            )
        )
        await session.commit()


async def _seed_connection(
    factory: async_sessionmaker[AsyncSession],
    *,
    uid: str,
    connector_id: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
    status: str = "active",
) -> str:
    km = KeyManager(settings.ENCRYPTION_SECRET)
    async with factory() as session:
        row = UserConnection(
            user_id=uid,
            connector_id=connector_id,
            access_token_enc=km.encrypt(access_token),
            refresh_token_enc=km.encrypt(refresh_token) if refresh_token else None,
            expires_at=expires_at,
            status=status,
        )
        session.add(row)
        await session.commit()
        return row.id


# ----------------------------------------------------------------------
# Name + schema unit tests
# ----------------------------------------------------------------------


def test_connector_tool_name_uses_single_underscore() -> None:
    assert connector_tool_name("notion", "search") == "notion_search"
    assert connector_tool_name("linear", "create_issue") == "linear_create_issue"
    # Google actions already embed a product prefix (gmail_/drive_/calendar_)
    # — confirm we preserve those inner underscores verbatim.
    assert connector_tool_name("google", "gmail_send") == "google_gmail_send"
    assert (
        connector_tool_name("google", "calendar_create_event")
        == "google_calendar_create_event"
    )


def test_connector_tool_name_rejects_empty_segments() -> None:
    with pytest.raises(ValueError):
        connector_tool_name("", "search")
    with pytest.raises(ValueError):
        connector_tool_name("notion", "")


def test_action_params_schema_translates_basic_types() -> None:
    action = ConnectorAction(
        id="create_issue",
        name="Create Issue",
        description="",
        parameters={
            "team_id": "string",
            "priority": "int (optional)",
            "paused": "boolean",
            "weight": "float",
            "properties": "object",
            "labels": "array",
        },
    )
    schema = connectors_mod._action_params_schema(action)
    props = schema["properties"]
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is True
    assert props["team_id"]["type"] == "string"
    assert props["priority"]["type"] == "integer"
    assert props["paused"]["type"] == "boolean"
    assert props["weight"]["type"] == "number"
    assert props["properties"]["type"] == "object"
    assert props["labels"]["type"] == "array"


# ----------------------------------------------------------------------
# Tool-list construction
# ----------------------------------------------------------------------


def test_build_connector_tools_for_connection_covers_every_connector() -> None:
    # We don't need a DB for this — the builder only reads the connector
    # class's static ``list_actions`` output.
    expected = {
        "notion": [
            "notion_search",
            "notion_list_databases",
            "notion_query_database",
            "notion_get_page",
            "notion_create_page",
            "notion_get_block_children",
        ],
        "github": [
            "github_list_repos",
            "github_get_repo",
            "github_list_issues",
            "github_create_issue",
            "github_list_prs",
            "github_get_pr",
            "github_create_pr",
            "github_search_code",
            "github_get_file",
        ],
        "google": [
            "google_gmail_list_messages",
            "google_gmail_read_message",
            "google_gmail_send",
            "google_gmail_search",
            "google_drive_list_files",
            "google_drive_read_file",
            "google_drive_upload",
            "google_calendar_list_events",
            "google_calendar_create_event",
        ],
        "linear": [
            "linear_list_issues",
            "linear_get_issue",
            "linear_create_issue",
            "linear_update_issue",
            "linear_list_projects",
            "linear_list_teams",
            "linear_search_issues",
        ],
        "slack": [
            "slack_list_channels",
            "slack_read_channel",
            "slack_send_message",
            "slack_search_messages",
            "slack_list_users",
            "slack_list_files",
        ],
    }
    for connector_id, names in expected.items():
        tools = build_connector_tools_for_connection(connector_id, "user-xyz")
        actual = [t.name for t in tools]
        assert actual == names, (
            f"{connector_id} tools changed: expected {names}, got {actual}"
        )
        for tool in tools:
            assert isinstance(tool, FunctionTool)
            assert tool.strict_json_schema is False
            assert tool.description  # non-empty, includes [DisplayName · cat]


def test_build_connector_tools_unknown_returns_empty() -> None:
    assert build_connector_tools_for_connection("not-a-real-connector", "u") == []


# ----------------------------------------------------------------------
# load_connector_tools: DB-backed discovery
# ----------------------------------------------------------------------


def test_load_connector_tools_returns_empty_without_session_factory(
    monkeypatch,
) -> None:
    monkeypatch.setattr(db, "_session_factory", None)
    assert _run(load_connector_tools("anyone")) == []


def test_load_connector_tools_returns_tools_only_for_active_connections(
    session_factory,
) -> None:
    uid = "user-1"

    async def scenario() -> None:
        await _seed_user(session_factory, uid)
        # Active notion + linear, revoked slack — slack must be filtered out.
        await _seed_connection(
            session_factory,
            uid=uid,
            connector_id="notion",
            access_token="ntn-access",
        )
        await _seed_connection(
            session_factory,
            uid=uid,
            connector_id="linear",
            access_token="lin-access",
        )
        await _seed_connection(
            session_factory,
            uid=uid,
            connector_id="slack",
            access_token="slk-access",
            status="revoked",
        )

        tools = await load_connector_tools(uid)
        names = {t.name for t in tools}
        assert any(n.startswith("notion_") for n in names)
        assert any(n.startswith("linear_") for n in names)
        assert not any(n.startswith("slack_") for n in names)
        # Notion has 6 actions, Linear 7 → 13 total.
        assert len(tools) == 13

    _run(scenario())


# ----------------------------------------------------------------------
# Tool invocation: end-to-end dispatch
# ----------------------------------------------------------------------


def test_tool_invocation_calls_execute_action_with_decrypted_token(
    session_factory, monkeypatch
) -> None:
    uid = "user-exec"
    captured: dict[str, Any] = {}

    async def fake_execute_action(
        self: Any, action_id: str, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        captured["action_id"] = action_id
        captured["params"] = params
        captured["access_token"] = access_token
        return {"ok": True, "echo": params}

    # Patch the NotionConnector's execute_action at the class level so
    # our FunctionTool invocation path goes through it.
    from backend.connectors.notion_connector import NotionConnector

    monkeypatch.setattr(
        NotionConnector, "execute_action", fake_execute_action
    )

    async def scenario() -> None:
        await _seed_user(session_factory, uid)
        await _seed_connection(
            session_factory,
            uid=uid,
            connector_id="notion",
            access_token="plain-access-token",
        )

        tools = await load_connector_tools(uid)
        search = next(t for t in tools if t.name == "notion_search")
        # Agents SDK hands tools a RunContextWrapper and the raw JSON
        # argument string; we mirror that contract.
        from agents import RunContextWrapper

        ctx = RunContextWrapper(context=None)
        raw = await search.on_invoke_tool(
            ctx, json.dumps({"query": "design docs"})
        )

        payload = json.loads(raw)
        assert payload == {"ok": True, "echo": {"query": "design docs"}}
        assert captured["action_id"] == "search"
        assert captured["params"] == {"query": "design docs"}
        # Confirm the token was decrypted back to the plaintext we
        # originally stored.
        assert captured["access_token"] == "plain-access-token"

    _run(scenario())


def test_tool_invocation_no_active_connection_returns_friendly_error(
    session_factory, monkeypatch
) -> None:
    uid = "user-no-conn"

    async def fake_execute_action(*args, **kwargs) -> dict[str, Any]:
        raise AssertionError("execute_action must not run when no active connection")

    from backend.connectors.notion_connector import NotionConnector

    monkeypatch.setattr(
        NotionConnector, "execute_action", fake_execute_action
    )

    async def scenario() -> None:
        await _seed_user(session_factory, uid)
        # No UserConnection row for this user.
        tools = build_connector_tools_for_connection("notion", uid)
        search = next(t for t in tools if t.name == "notion_search")
        from agents import RunContextWrapper

        ctx = RunContextWrapper(context=None)
        result = await search.on_invoke_tool(ctx, "{}")
        assert result.startswith("ERROR: no active Notion connection")

    _run(scenario())


def test_tool_invocation_refreshes_expired_token(
    session_factory, monkeypatch
) -> None:
    uid = "user-refresh"
    captured: dict[str, Any] = {}

    async def fake_execute_action(
        self: Any, action_id: str, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        captured["access_token"] = access_token
        return {"ok": True}

    async def fake_refresh_tokens(self: Any, refresh_token: str) -> OAuthTokens:
        captured["refresh_token_used"] = refresh_token
        return OAuthTokens(
            access_token="refreshed-access",
            refresh_token="refreshed-refresh",
            expires_in=3600,
        )

    # Use Google connector so the refresh path has a realistic target.
    from backend.connectors.google_connector import GoogleConnector

    monkeypatch.setattr(GoogleConnector, "execute_action", fake_execute_action)
    monkeypatch.setattr(GoogleConnector, "refresh_tokens", fake_refresh_tokens)

    async def scenario() -> None:
        await _seed_user(session_factory, uid)
        expired = datetime.now(timezone.utc) - timedelta(minutes=5)
        conn_id = await _seed_connection(
            session_factory,
            uid=uid,
            connector_id="google",
            access_token="old-access",
            refresh_token="stored-refresh",
            expires_at=expired,
        )

        tools = await load_connector_tools(uid)
        send = next(t for t in tools if t.name == "google_gmail_send")
        from agents import RunContextWrapper

        ctx = RunContextWrapper(context=None)
        raw = await send.on_invoke_tool(
            ctx,
            json.dumps(
                {"to": "a@b.com", "subject": "hi", "body": "hello"}
            ),
        )
        assert json.loads(raw) == {"ok": True}

        # Refresh path must have been exercised with the stored refresh
        # token and the resulting access token is what got handed to
        # execute_action.
        assert captured["refresh_token_used"] == "stored-refresh"
        assert captured["access_token"] == "refreshed-access"

        # And the DB row must have been updated to the new ciphertext +
        # expiry.
        km = KeyManager(settings.ENCRYPTION_SECRET)
        async with session_factory() as session:
            row = await session.get(UserConnection, conn_id)
            assert row is not None
            assert km.decrypt(row.access_token_enc) == "refreshed-access"
            assert row.refresh_token_enc is not None
            assert km.decrypt(row.refresh_token_enc) == "refreshed-refresh"
            assert row.status == "active"
            assert row.expires_at is not None
            stored_expires = row.expires_at
            if stored_expires.tzinfo is None:
                stored_expires = stored_expires.replace(tzinfo=timezone.utc)
            assert stored_expires > datetime.now(timezone.utc)

    _run(scenario())


def test_tool_invocation_surfaces_connector_errors_as_error_string(
    session_factory, monkeypatch
) -> None:
    uid = "user-raises"

    async def fake_execute_action(
        self: Any, action_id: str, params: dict[str, Any], access_token: str
    ) -> dict[str, Any]:
        raise RuntimeError("upstream exploded")

    from backend.connectors.github_connector import GitHubConnector

    monkeypatch.setattr(GitHubConnector, "execute_action", fake_execute_action)

    async def scenario() -> None:
        await _seed_user(session_factory, uid)
        await _seed_connection(
            session_factory,
            uid=uid,
            connector_id="github",
            access_token="ghp_xxx",
        )
        tools = await load_connector_tools(uid)
        list_repos = next(t for t in tools if t.name == "github_list_repos")
        from agents import RunContextWrapper

        ctx = RunContextWrapper(context=None)
        raw = await list_repos.on_invoke_tool(ctx, "{}")
        assert raw.startswith("ERROR: github_list_repos raised RuntimeError")
        assert "upstream exploded" in raw

    _run(scenario())


def test_tool_invocation_rejects_non_object_args(session_factory) -> None:
    async def scenario() -> None:
        tools = build_connector_tools_for_connection("notion", "some-user")
        search = next(t for t in tools if t.name == "notion_search")
        from agents import RunContextWrapper

        ctx = RunContextWrapper(context=None)
        # Top-level JSON array → the runtime should refuse the call
        # before ever hitting the DB / connector.
        raw = await search.on_invoke_tool(ctx, "[1, 2, 3]")
        assert raw.startswith("ERROR: notion_search arguments must be a JSON object")
        # Malformed JSON.
        raw = await search.on_invoke_tool(ctx, "not-json")
        assert raw.startswith("ERROR: invalid JSON arguments for notion_search")

    _run(scenario())


__all__: list[str] = []


# ----------------------------------------------------------------------
# Codex P1 regression: native tools must not be shadowed by connectors
# ----------------------------------------------------------------------


def test_default_build_agent_does_not_shadow_native_github_tools(caplog) -> None:
    """Regression test for Codex P1 on PR #338.

    Native tools and connector tools both use ``github_*`` names (native
    is the PAT-backed workspace manager, connector is the OAuth wrapper).
    Without de-duplication the Agents SDK's last-wins resolution lets
    the connector silently replace the native tool, breaking every flow
    that currently relies on PAT auth. We must keep native, drop the
    colliding connector version, and log a warning.
    """
    import logging

    from backend.runtime import agent_loop
    from backend.runtime.session import ChannelSession, ChannelSessionKey
    from backend.runtime.tools.native import get_enabled_native_tools

    native = list(get_enabled_native_tools())
    native_names = {t.name for t in native if getattr(t, "name", None)}
    # Sanity: the three PLAN-level collisions we care about really do
    # exist on the native side.
    for colliding_name in ("github_list_repos", "github_create_issue", "github_get_file"):
        assert colliding_name in native_names, (
            f"native tools unexpectedly lost {colliding_name!r} — update this "
            "regression test if the native surface changed on purpose"
        )

    connector_tools = build_connector_tools_for_connection("github", "user-xyz")
    # Isolate just the two classes we care about for this assertion so
    # the test stays deterministic even if native tools drift.
    caplog.set_level(logging.WARNING, logger="backend.runtime.agent_loop")

    session = ChannelSession(key=ChannelSessionKey(owner_uid="user-xyz", channel="web"))
    agent = agent_loop._default_build_agent(
        session,
        None,  # ToolContext is unused by _default_build_agent
        agent_loop.DispatchConfig(),
        mcp_tools=None,
        connector_tools=connector_tools,
    )
    names = [getattr(t, "name", None) for t in agent.tools]

    # Every native tool survived.
    for native_name in native_names:
        assert native_name in names, f"native tool {native_name!r} disappeared"

    # Connector-unique github tools did get added (not every github
    # connector action collides with native).
    for unique_name in (
        "github_get_repo",
        "github_list_issues",
        "github_list_prs",
        "github_get_pr",
        "github_create_pr",
        "github_search_code",
    ):
        assert unique_name in names, (
            f"connector-only tool {unique_name!r} should still register"
        )

    # Colliding connector tools were dropped — each name appears
    # exactly once in the final list.
    for colliding_name in ("github_list_repos", "github_create_issue", "github_get_file"):
        assert names.count(colliding_name) == 1, (
            f"{colliding_name!r} appears {names.count(colliding_name)} times; "
            "connector version must be deduped against native"
        )

    # And the warning actually fired, so the shadowing is visible in
    # production logs.
    warnings = [r for r in caplog.records if "shadowed by earlier layer" in r.getMessage()]
    assert warnings, "expected a warning log when connector tools are dropped"
    msg = warnings[-1].getMessage()
    for colliding_name in ("github_list_repos", "github_create_issue", "github_get_file"):
        assert colliding_name in msg, f"warning should name {colliding_name!r}"


def test_default_build_agent_dedupes_mcp_and_connector_tools() -> None:
    """MCP tools de-duplicate against native too, and connectors then
    de-duplicate against both earlier layers."""
    from agents import FunctionTool

    from backend.runtime import agent_loop
    from backend.runtime.session import ChannelSession, ChannelSessionKey

    async def _noop(ctx, args):  # pragma: no cover - never invoked
        return "ok"

    schema = {"type": "object", "properties": {}, "additionalProperties": True}

    # Fake MCP tool whose name collides with a native tool.
    mcp_dup = FunctionTool(
        name="github_list_repos",
        description="mcp dup",
        params_json_schema=schema,
        on_invoke_tool=_noop,
        strict_json_schema=False,
    )
    # Fake MCP tool with a brand-new name that should survive.
    mcp_new = FunctionTool(
        name="browser__goto",
        description="mcp unique",
        params_json_schema=schema,
        on_invoke_tool=_noop,
        strict_json_schema=False,
    )
    # Fake connector tool that collides with the MCP unique tool.
    connector_dup = FunctionTool(
        name="browser__goto",
        description="connector dup",
        params_json_schema=schema,
        on_invoke_tool=_noop,
        strict_json_schema=False,
    )
    connector_unique = FunctionTool(
        name="notion_search",
        description="connector unique",
        params_json_schema=schema,
        on_invoke_tool=_noop,
        strict_json_schema=False,
    )

    session = ChannelSession(key=ChannelSessionKey(owner_uid="user-xyz", channel="web"))
    agent = agent_loop._default_build_agent(
        session,
        None,
        agent_loop.DispatchConfig(),
        mcp_tools=[mcp_dup, mcp_new],
        connector_tools=[connector_dup, connector_unique],
    )
    names = [getattr(t, "name", None) for t in agent.tools]

    # github_list_repos stays native (MCP dup dropped).
    descriptions_for_github = [
        getattr(t, "description", "") for t in agent.tools if t.name == "github_list_repos"
    ]
    assert len(descriptions_for_github) == 1
    assert "mcp dup" not in descriptions_for_github[0]

    # browser__goto survives exactly once, from MCP (connector dup dropped).
    goto_tools = [t for t in agent.tools if t.name == "browser__goto"]
    assert len(goto_tools) == 1
    assert goto_tools[0].description == "mcp unique"

    # Connector-unique tool survives.
    assert "notion_search" in names
