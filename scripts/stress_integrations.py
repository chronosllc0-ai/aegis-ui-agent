"""Stress validation script for integration manager and safety paths."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from time import perf_counter

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.manager import IntegrationManager


async def main() -> None:
    manager = IntegrationManager()
    report: dict[str, object] = {"checks": []}

    async def record(name: str, coro):
        start = perf_counter()
        try:
            result = await coro
            report["checks"].append({"name": name, "ok": True, "latency_ms": int((perf_counter() - start) * 1000), "result": str(result)[:400]})
        except Exception as exc:  # noqa: BLE001
            report["checks"].append({"name": name, "ok": False, "latency_ms": int((perf_counter() - start) * 1000), "error": str(exc)})

    # connect/test/disconnect cycles (native local integrations)
    await record("filesystem_connect", manager.connect_native("stress", "filesystem", {"roots": ["."], "allow_delete": False}, {}))
    await record("filesystem_list", manager.execute_native("stress", "filesystem", "filesystem.list_dir", {"path": "."}))
    await record("filesystem_traversal_block", manager.execute_native("stress", "filesystem", "filesystem.read_text", {"path": "../etc/passwd"}))

    await record("codeexec_connect", manager.connect_native("stress", "code-exec", {"enabled": True, "timeout_seconds": 1, "output_cap": 128}, {}))
    await record("codeexec_timeout", manager.execute_native("stress", "code-exec", "code.exec_python", {"code": "while True:\n  pass"}))
    await record("codeexec_syntax_error", manager.execute_native("stress", "code-exec", "code.exec_python", {"code": "print('x'"}))

    # concurrent executions
    async def run_concurrent(index: int):
        return await manager.execute_native("stress", "code-exec", "code.exec_python", {"code": f"print('run-{index}')"})

    await record("codeexec_concurrent", asyncio.gather(*(run_concurrent(i) for i in range(5))))

    # mocked custom MCP reconnect behavior
    async def fake_list_tools(transport: str, config: dict):
        return [{"name": "echo", "description": "Echo"}]

    async def fake_call_tool(transport: str, config: dict, tool_name: str, args: dict):
        return {"content": [{"type": "text", "text": args.get("value", "")}], "is_error": False}

    manager.mcp.list_tools = fake_list_tools  # type: ignore[assignment]
    manager.mcp.call_tool = fake_call_tool  # type: ignore[assignment]

    created = await manager.add_mcp_server("stress", "local-mcp", "streamable_http", {"url": "http://localhost:3000/mcp"}, {})
    await record("mcp_test", manager.test_mcp_server("stress", created["server_id"]))
    await record("mcp_execute", manager.execute_mcp_server("stress", created["server_id"], "echo", {"value": "hello"}))

    output_dir = Path("artifacts")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "stress_integrations_report.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out_file}")


if __name__ == "__main__":
    asyncio.run(main())
