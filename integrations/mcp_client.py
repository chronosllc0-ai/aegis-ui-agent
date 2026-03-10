"""Custom MCP server client wrapper using official mcp SDK transports."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from integrations.base import IntegrationError

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamable_http_client
except Exception:  # pragma: no cover - optional dependency at runtime
    ClientSession = Any  # type: ignore[misc,assignment]
    StdioServerParameters = Any  # type: ignore[misc,assignment]
    sse_client = None
    stdio_client = None
    streamable_http_client = None


class MCPTransportClient:
    """Runs transport-specific MCP session initialize/list/call flows."""

    @asynccontextmanager
    async def session_for(self, transport: str, config: dict[str, Any]):
        if streamable_http_client is None or sse_client is None or stdio_client is None:
            raise IntegrationError("mcp SDK is not installed in this environment")

        if transport == "streamable_http":
            url = str(config.get("url", "")).strip()
            headers = config.get("headers", {})
            async with streamable_http_client(url, headers=headers) as streams:
                read_stream, write_stream, _ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
            return

        if transport == "sse":
            url = str(config.get("url", "")).strip()
            headers = config.get("headers", {})
            async with sse_client(url, headers=headers) as streams:
                read_stream, write_stream = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
            return

        if transport == "stdio":
            command = str(config.get("command", "")).strip()
            args = [str(item) for item in config.get("args", [])]
            env_map = {str(k): str(v) for k, v in dict(config.get("env", {})).items()}
            params = StdioServerParameters(command=command, args=args, env=env_map)
            async with stdio_client(params) as streams:
                read_stream, write_stream = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session
            return

        raise IntegrationError(f"Unsupported MCP transport: {transport}")

    async def list_tools(self, transport: str, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Initialize a session and return list of server tools."""
        async with self.session_for(transport, config) as session:
            tools_response = await session.list_tools()
            tools = getattr(tools_response, "tools", [])
            output: list[dict[str, Any]] = []
            for tool in tools:
                output.append(
                    {
                        "name": getattr(tool, "name", "unknown"),
                        "description": getattr(tool, "description", ""),
                        "inputSchema": getattr(tool, "inputSchema", {}),
                    }
                )
            return output

    async def call_tool(self, transport: str, config: dict[str, Any], tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Initialize a session and call one tool."""
        async with self.session_for(transport, config) as session:
            result = await session.call_tool(tool_name, args)
            return {"content": getattr(result, "content", []), "is_error": bool(getattr(result, "isError", False))}
