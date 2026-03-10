"""Integration manager handling secure credentials and connector execution."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from integrations.base import BaseIntegration, IntegrationError
from integrations.brave_search import BraveSearchIntegration
from integrations.code_execution import CodeExecutionIntegration
from integrations.discord import DiscordIntegration
from integrations.filesystem import FileSystemIntegration
from integrations.mcp_client import MCPTransportClient
from integrations.models import IntegrationRecord, MCPServerRecord, ToolDefinition, utc_now_iso
from integrations.secure_store import SecureStore
from integrations.slack_connector import SlackIntegration
from integrations.telegram import TelegramIntegration


class IntegrationManager:
    """Owns native integrations and custom MCP registry by user."""

    def __init__(self) -> None:
        self.secure_store = SecureStore()
        self.records: dict[str, dict[str, IntegrationRecord]] = {}
        self.mcp_records: dict[str, dict[str, MCPServerRecord]] = {}
        self._connectors: dict[str, BaseIntegration] = {
            "telegram": TelegramIntegration(),
            "slack": SlackIntegration(),
            "discord": DiscordIntegration(),
            "brave-search": BraveSearchIntegration(),
            "filesystem": FileSystemIntegration(),
            "code-exec": CodeExecutionIntegration(),
        }
        self.mcp = MCPTransportClient()

    def _record_for(self, user_id: str, kind: str) -> IntegrationRecord:
        return self.records.setdefault(user_id, {}).setdefault(kind, IntegrationRecord(user_id=user_id, kind=kind))

    def _mask_secret_fields(self, payload: dict[str, str]) -> dict[str, str]:
        return {key: self.secure_store.mask(value) for key, value in payload.items()}

    async def connect_native(self, user_id: str, kind: str, config: dict[str, Any], secrets: dict[str, str]) -> dict[str, Any]:
        connector = self._connectors.get(kind)
        if connector is None:
            raise IntegrationError(f"Unsupported integration kind: {kind}")
        record = self._record_for(user_id, kind)
        secret_ref = self.secure_store.set_secret(f"native:{user_id}:{kind}", secrets)
        record.secret_ref = secret_ref
        record.config = config
        connect_meta = await connector.connect(record, secrets)
        record.status = "connected"
        record.last_health_check = utc_now_iso()
        return {
            "kind": kind,
            "status": record.status,
            "last_health_check": record.last_health_check,
            "masked_credentials": self._mask_secret_fields(secrets),
            "meta": connect_meta,
            "tools": [tool.__dict__ for tool in connector.list_tools()],
        }

    async def disconnect_native(self, user_id: str, kind: str) -> dict[str, Any]:
        connector = self._connectors.get(kind)
        record = self._record_for(user_id, kind)
        if connector is not None:
            await connector.disconnect(record)
        record.status = "disabled"
        return {"kind": kind, "status": "disabled"}

    async def test_native(self, user_id: str, kind: str) -> dict[str, Any]:
        connector = self._connectors.get(kind)
        if connector is None:
            raise IntegrationError(f"Unsupported integration kind: {kind}")
        record = self._record_for(user_id, kind)
        secrets = self.secure_store.get_secret(record.secret_ref)
        health = await connector.health_check(record, secrets)
        record.last_health_check = utc_now_iso()
        record.status = "connected" if health.get("ok", True) else "error"
        return {"kind": kind, "health": health, "status": record.status, "last_health_check": record.last_health_check}

    async def execute_native(self, user_id: str, kind: str, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        connector = self._connectors.get(kind)
        if connector is None:
            raise IntegrationError(f"Unsupported integration kind: {kind}")
        record = self._record_for(user_id, kind)
        secrets = self.secure_store.get_secret(record.secret_ref)
        result = await connector.timed_execute(record, secrets, tool_name, params)
        if result.ok:
            record.last_success_action = utc_now_iso()
            record.status = "connected"
            record.last_error = None
        else:
            record.status = "error"
            record.last_error = result.error
        return result.as_dict()

    def list_native(self, user_id: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for kind, connector in self._connectors.items():
            record = self._record_for(user_id, kind)
            secrets = self.secure_store.get_secret(record.secret_ref)
            output.append(
                {
                    "kind": kind,
                    "status": record.status,
                    "config": record.config,
                    "masked_credentials": self._mask_secret_fields(secrets),
                    "last_health_check": record.last_health_check,
                    "last_success_action": record.last_success_action,
                    "last_error": record.last_error,
                    "tools": [tool.__dict__ for tool in connector.list_tools()],
                }
            )
        return output

    async def add_mcp_server(
        self,
        user_id: str,
        name: str,
        transport: str,
        config: dict[str, Any],
        secrets: dict[str, str],
    ) -> dict[str, Any]:
        server_id = str(uuid4())
        secret_ref = self.secure_store.set_secret(f"mcp:{user_id}:{server_id}", secrets)
        record = MCPServerRecord(server_id=server_id, user_id=user_id, name=name, transport=transport, config=config, secret_ref=secret_ref)
        self.mcp_records.setdefault(user_id, {})[server_id] = record
        tools = await self._test_mcp_record(record)
        record.connected = True
        record.tool_count = len(tools)
        record.last_test_at = utc_now_iso()
        return {"server_id": server_id, "name": name, "transport": transport, "tool_count": len(tools), "tools": tools}

    async def _test_mcp_record(self, record: MCPServerRecord) -> list[dict[str, Any]]:
        secrets = self.secure_store.get_secret(record.secret_ref)
        transport_config = record.config | {"headers": record.config.get("headers", {})}
        if bearer := secrets.get("bearer_token"):
            transport_config["headers"] = dict(transport_config.get("headers", {})) | {"Authorization": f"Bearer {bearer}"}
        return await self.mcp.list_tools(record.transport, transport_config)

    async def test_mcp_server(self, user_id: str, server_id: str) -> dict[str, Any]:
        record = self.mcp_records.get(user_id, {}).get(server_id)
        if record is None:
            raise IntegrationError("Unknown MCP server")
        tools = await self._test_mcp_record(record)
        record.tool_count = len(tools)
        record.last_test_at = utc_now_iso()
        record.connected = True
        return {"server_id": server_id, "tools": tools, "tool_count": len(tools), "last_test_at": record.last_test_at}

    async def execute_mcp_server(self, user_id: str, server_id: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        record = self.mcp_records.get(user_id, {}).get(server_id)
        if record is None:
            raise IntegrationError("Unknown MCP server")
        secrets = self.secure_store.get_secret(record.secret_ref)
        transport_config = record.config | {"headers": record.config.get("headers", {})}
        if bearer := secrets.get("bearer_token"):
            transport_config["headers"] = dict(transport_config.get("headers", {})) | {"Authorization": f"Bearer {bearer}"}
        result = await self.mcp.call_tool(record.transport, transport_config, tool_name, args)
        return {"ok": not result.get("is_error", False), "tool": tool_name, "data": result}

    async def delete_mcp_server(self, user_id: str, server_id: str) -> dict[str, Any]:
        user_servers = self.mcp_records.get(user_id, {})
        if server_id in user_servers:
            user_servers.pop(server_id)
        return {"deleted": True, "server_id": server_id}

    def list_mcp_servers(self, user_id: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for record in self.mcp_records.get(user_id, {}).values():
            output.append(
                {
                    "server_id": record.server_id,
                    "name": record.name,
                    "transport": record.transport,
                    "connected": record.connected,
                    "tool_count": record.tool_count,
                    "last_test_at": record.last_test_at,
                    "last_error": record.last_error,
                    "config_summary": {
                        "url": record.config.get("url"),
                        "command": record.config.get("command"),
                    },
                }
            )
        return output

    def tool_manifest(self, user_id: str) -> list[ToolDefinition]:
        """Return all connected integration tools for agent registration/use."""
        tools: list[ToolDefinition] = []
        for kind, connector in self._connectors.items():
            record = self._record_for(user_id, kind)
            if record.status == "connected":
                tools.extend(connector.list_tools())
        return tools
