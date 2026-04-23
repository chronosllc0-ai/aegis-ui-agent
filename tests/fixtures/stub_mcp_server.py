"""Trivial in-repo MCP stdio server used by ``tests/test_runtime_mcp_host.py``.

Exposes two tools:

* ``echo(message: str)`` → returns the input string wrapped with a prefix.
* ``add(a: number, b: number)`` → returns ``a + b`` as text.

The server is intentionally minimal — no external dependencies beyond
the ``mcp`` Python SDK — so CI does not need Node or ``npx`` to exercise
the MCP host plumbing.
"""

from __future__ import annotations

import asyncio
import sys

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
import mcp.types as mcp_types


SERVER_NAME = "aegis-stub-mcp"


def _build() -> Server:
    server: Server = Server(SERVER_NAME)

    @server.list_tools()
    async def _list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name="echo",
                description="Echo a message back with a fixed prefix.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Message to echo.",
                        }
                    },
                    "required": ["message"],
                },
            ),
            mcp_types.Tool(
                name="add",
                description="Add two numbers.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                    },
                    "required": ["a", "b"],
                },
            ),
        ]

    @server.call_tool()
    async def _call_tool(
        name: str, arguments: dict | None
    ) -> list[mcp_types.ContentBlock]:
        arguments = arguments or {}
        if name == "echo":
            message = str(arguments.get("message", ""))
            return [mcp_types.TextContent(type="text", text=f"stub:{message}")]
        if name == "add":
            total = float(arguments.get("a", 0)) + float(arguments.get("b", 0))
            # Keep integer formatting when possible to make assertions tidy.
            if total.is_integer():
                total_str = str(int(total))
            else:
                total_str = str(total)
            return [mcp_types.TextContent(type="text", text=total_str)]
        raise ValueError(f"unknown tool: {name}")

    return server


async def _main() -> None:
    server = _build()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(0)
