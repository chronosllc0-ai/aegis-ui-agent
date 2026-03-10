"""Tests for custom MCP server management and transport invocation."""

from __future__ import annotations

import asyncio

import pytest

from integrations.manager import IntegrationManager
from integrations.mcp_client import MCPTransportClient


def test_mcp_manager_add_test_execute_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        manager = IntegrationManager()

        async def fake_list_tools(transport: str, config: dict):
            return [{"name": "echo", "description": "Echo"}]

        async def fake_call_tool(transport: str, config: dict, tool_name: str, args: dict):
            return {"content": [{"type": "text", "text": args.get("value", "")}], "is_error": False}

        monkeypatch.setattr(manager.mcp, "list_tools", fake_list_tools)
        monkeypatch.setattr(manager.mcp, "call_tool", fake_call_tool)

        created = await manager.add_mcp_server("u1", "local", "streamable_http", {"url": "http://localhost:3000/mcp"}, {"bearer_token": "abc"})
        tested = await manager.test_mcp_server("u1", created["server_id"])
        executed = await manager.execute_mcp_server("u1", created["server_id"], "echo", {"value": "hi"})
        deleted = await manager.delete_mcp_server("u1", created["server_id"])

        assert created["tool_count"] == 1
        assert tested["tool_count"] == 1
        assert executed["ok"] is True
        assert deleted["deleted"] is True

    asyncio.run(scenario())


def test_mcp_sdk_missing_raises() -> None:
    async def scenario() -> None:
        client = MCPTransportClient()
        with pytest.raises(Exception):
            await client.list_tools("unknown", {})

    asyncio.run(scenario())
