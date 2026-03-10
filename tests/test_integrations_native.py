"""Tests for native integration implementations and manager behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import main
from integrations.code_execution import CodeExecutionIntegration
from integrations.filesystem import FileSystemIntegration
from integrations.manager import IntegrationManager
from integrations.telegram import TelegramIntegration


class _MockResponse:
    def __init__(self, status_code: int = 200, body: dict | None = None, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}
        self.headers = headers or {}
        self.text = "json"

    def json(self):
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


def test_telegram_get_updates_persists_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        integration = TelegramIntegration()
        responses = [_MockResponse(body={"ok": True, "result": [{"update_id": 42}]})]

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json):
                return responses.pop(0)

        monkeypatch.setattr("integrations.telegram.httpx.AsyncClient", lambda *args, **kwargs: _Client())

        record = main.integration_manager._record_for("u1", "telegram")
        result = await integration.execute_tool(record, {"bot_token": "x"}, "telegram.get_updates", {})
        assert result.ok is True
        assert result.data["next_offset"] == 43
        assert integration.get_polling_offset("u1") == 43

    asyncio.run(scenario())


def test_telegram_webhook_secret_validation() -> None:
    manager = main.integration_manager
    record = manager._record_for("demo-user", "telegram")
    record.config = {"webhook_secret": "secret-token"}

    from fastapi.testclient import TestClient

    with TestClient(main.app) as api:
        bad = api.post("/api/integrations/telegram/webhook/test-id", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
        ok = api.post("/api/integrations/telegram/webhook/test-id", json={"update_id": 2}, headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"})

    assert bad.status_code == 403
    assert ok.status_code == 200


def test_filesystem_blocks_traversal(tmp_path: Path) -> None:
    async def scenario() -> None:
        integration = FileSystemIntegration()
        record = main.integration_manager._record_for("u2", "filesystem")
        record.config = {"roots": [str(tmp_path)]}
        result = await integration.execute_tool(record, {}, "filesystem.read_text", {"path": "../etc/passwd"})
        assert result.ok is False
        assert "allowlisted" in (result.error or "")

    asyncio.run(scenario())


def test_filesystem_list_and_write(tmp_path: Path) -> None:
    async def scenario() -> None:
        integration = FileSystemIntegration()
        record = main.integration_manager._record_for("u3", "filesystem")
        record.config = {"roots": [str(tmp_path)], "max_file_bytes": 1000}
        write = await integration.execute_tool(record, {}, "filesystem.write_text", {"path": "notes/a.txt", "content": "hello"})
        read = await integration.execute_tool(record, {}, "filesystem.read_text", {"path": "notes/a.txt"})
        assert write.ok is True
        assert read.data["content"] == "hello"

    asyncio.run(scenario())


def test_code_execution_timeout_and_truncation() -> None:
    async def scenario() -> None:
        integration = CodeExecutionIntegration()
        record = main.integration_manager._record_for("u4", "code-exec")
        record.config = {"enabled": True, "timeout_seconds": 1, "output_cap": 20}

        timed_out = await integration.execute_tool(record, {}, "code.exec_python", {"code": "while True:\n  pass"})
        truncated = await integration.execute_tool(record, {}, "code.exec_python", {"code": "print('x'*200)"})

        assert timed_out.ok is False
        assert timed_out.data["timeout"] is True
        assert len(truncated.data["stdout"]) <= 20

    asyncio.run(scenario())


def test_code_execution_concurrent_runs() -> None:
    async def scenario() -> None:
        integration = CodeExecutionIntegration()
        record = main.integration_manager._record_for("u5", "code-exec")
        record.config = {"enabled": True, "timeout_seconds": 3, "output_cap": 200}

        async def run_one(index: int):
            return await integration.execute_tool(record, {}, "code.exec_python", {"code": f"print('run-{index}')"})

        results = await asyncio.gather(*(run_one(i) for i in range(4)))
        assert all(result.ok for result in results)

    asyncio.run(scenario())


def test_secure_store_masking() -> None:
    manager = IntegrationManager()
    masked = manager.secure_store.mask("abcd123456")
    assert masked.endswith("3456")
    assert masked.startswith("••••")
