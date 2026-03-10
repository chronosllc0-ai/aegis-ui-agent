"""Filesystem integration with root allowlist and traversal protections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from integrations.base import BaseIntegration, IntegrationError
from integrations.models import IntegrationRecord, ToolDefinition, ToolExecutionResult


class FileSystemIntegration(BaseIntegration):
    """Local filesystem tool surface constrained to allowlisted roots."""

    kind = "filesystem"

    def _allowed_roots(self, record: IntegrationRecord) -> list[Path]:
        roots = record.config.get("roots", [])
        return [Path(str(root)).resolve() for root in roots]

    def _resolve_path(self, record: IntegrationRecord, rel_path: str) -> Path:
        requested = Path(rel_path)
        roots = self._allowed_roots(record)
        if not roots:
            raise IntegrationError("No filesystem roots configured")
        candidate = (roots[0] / requested).resolve()
        for root in roots:
            if root == candidate or root in candidate.parents:
                if candidate.is_symlink():
                    raise IntegrationError("Symlink access is not allowed")
                return candidate
        raise IntegrationError("Path escapes allowlisted roots")

    async def connect(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        roots = self._allowed_roots(record)
        if not roots:
            raise IntegrationError("At least one allowlisted root is required")
        return {"connected": True, "roots": [str(root) for root in roots]}

    async def disconnect(self, record: IntegrationRecord) -> None:
        return None

    async def health_check(self, record: IntegrationRecord, secrets: dict[str, str]) -> dict[str, Any]:
        roots = self._allowed_roots(record)
        return {"ok": bool(roots), "roots": [str(root) for root in roots]}

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition("filesystem.list_dir", "List directory entries"),
            ToolDefinition("filesystem.read_text", "Read text file with size cap"),
            ToolDefinition("filesystem.write_text", "Write text file"),
            ToolDefinition("filesystem.search", "Glob search under root"),
            ToolDefinition("filesystem.delete_file", "Delete file if enabled"),
        ]

    async def execute_tool(
        self,
        record: IntegrationRecord,
        secrets: dict[str, str],
        tool_name: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        size_cap = int(record.config.get("max_file_bytes", 200_000))
        try:
            if tool_name == "filesystem.list_dir":
                path = self._resolve_path(record, str(params.get("path", ".")))
                data = {"entries": sorted([entry.name for entry in path.iterdir()])}
            elif tool_name == "filesystem.read_text":
                path = self._resolve_path(record, str(params.get("path", "")))
                if path.stat().st_size > size_cap:
                    raise IntegrationError("File exceeds configured size limit")
                data = {"path": str(path), "content": path.read_text(encoding="utf-8")}
            elif tool_name == "filesystem.write_text":
                path = self._resolve_path(record, str(params.get("path", "")))
                content = str(params.get("content", ""))
                if len(content.encode("utf-8")) > size_cap:
                    raise IntegrationError("Write exceeds configured size limit")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                data = {"path": str(path), "written": True}
            elif tool_name == "filesystem.search":
                pattern = str(params.get("pattern", "**/*"))
                root = self._resolve_path(record, str(params.get("root", ".")))
                matches = [str(path.relative_to(root)) for path in root.glob(pattern) if path.is_file()][:200]
                data = {"matches": matches}
            elif tool_name == "filesystem.delete_file":
                if not bool(record.config.get("allow_delete", False)):
                    raise IntegrationError("Delete is disabled for filesystem integration")
                path = self._resolve_path(record, str(params.get("path", "")))
                path.unlink(missing_ok=True)
                data = {"path": str(path), "deleted": True}
            else:
                raise IntegrationError(f"Unsupported filesystem tool: {tool_name}")
            return ToolExecutionResult(ok=True, tool=tool_name, data=data)
        except (IntegrationError, OSError, ValueError) as exc:
            return ToolExecutionResult(ok=False, tool=tool_name, error=str(exc))
