"""Sandboxed local code execution integration."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from integrations.base import BaseIntegration, IntegrationError
from integrations.models import IntegrationRecord, ToolDefinition, ToolExecutionResult


class CodeExecutionIntegration(BaseIntegration):
    """Execute Python/Node snippets with timeout and output caps."""

    kind = "code-exec"

    async def connect(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        if not bool(record.config.get("enabled", False)):
            raise IntegrationError("Code execution is disabled by configuration")
        return {"connected": True, "languages": ["python", "node"]}

    async def disconnect(self, record: IntegrationRecord) -> None:
        return None

    async def health_check(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        return {"ok": bool(record.config.get("enabled", False)), "timeout_seconds": int(record.config.get("timeout_seconds", 5))}

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("code.exec_python", "Execute python snippet."),
            ToolDefinition("code.exec_node", "Execute node snippet."),
        ]

    async def _run(self, command: list[str], code: str, timeout_seconds: int, output_cap: int) -> dict[str, Any]:
        clean_env = {k: v for k, v in os.environ.items() if "KEY" not in k and "TOKEN" not in k and "SECRET" not in k}
        with tempfile.TemporaryDirectory(prefix="aegis-codeexec-") as temp_dir:
            workdir = Path(temp_dir)
            script_path = workdir / ("snippet.py" if command[0].endswith("python") else "snippet.js")
            script_path.write_text(code, encoding="utf-8")
            process = await asyncio.create_subprocess_exec(
                *command,
                str(script_path),
                cwd=str(workdir),
                env=clean_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return {"timeout": True, "stdout": "", "stderr": "Execution timed out"}

        stdout_text = stdout.decode("utf-8", errors="replace")[:output_cap]
        stderr_text = stderr.decode("utf-8", errors="replace")[:output_cap]
        return {"timeout": False, "returncode": process.returncode, "stdout": stdout_text, "stderr": stderr_text}

    async def execute_tool(
        self,
        record: IntegrationRecord,
        secrets: dict[str, str],
        tool_name: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        if not bool(record.config.get("enabled", False)):
            return ToolExecutionResult(ok=False, tool=tool_name, error="Code execution disabled")
        timeout_seconds = int(record.config.get("timeout_seconds", 5))
        output_cap = int(record.config.get("output_cap", 8000))
        try:
            code = str(params.get("code", ""))
            if tool_name == "code.exec_python":
                data = await self._run(["python"], code, timeout_seconds, output_cap)
            elif tool_name == "code.exec_node":
                data = await self._run(["node"], code, timeout_seconds, output_cap)
            else:
                raise IntegrationError(f"Unsupported code tool: {tool_name}")
            ok = not data.get("timeout", False) and int(data.get("returncode", 1)) == 0
            return ToolExecutionResult(ok=ok, tool=tool_name, data=data, error=None if ok else data.get("stderr"))
        except (IntegrationError, OSError, ValueError) as exc:
            return ToolExecutionResult(ok=False, tool=tool_name, error=str(exc))
