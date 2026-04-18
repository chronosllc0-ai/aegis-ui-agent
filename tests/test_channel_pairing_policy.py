"""Regression tests for channel pairing and ingress policy enforcement."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

import auth
import main
from backend import database
from backend.database import PairedChannelIdentity, User
from backend.integrations.channel_runtime import TelegramChannelAdapter
from config import settings


class _StubTelegramIntegration:
    def __init__(self) -> None:
        self.sent_texts: list[str] = []

    def validate_webhook_secret(self, secret: str) -> bool:
        _ = secret
        return True

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "telegram_webhook_update":
            return {"ok": True, "tool": tool_name, "result": {"handled": True}}
        if tool_name == "telegram_send_message":
            self.sent_texts.append(str(params.get("text") or ""))
            return {"ok": True, "result": {"message_id": 1}}
        return {"ok": True, "tool": tool_name, "result": params}


def _init_test_db(tmp_path: Path, name: str) -> None:
    database.init_db(f"sqlite+aiosqlite:///{tmp_path / name}")
    asyncio.run(database.create_tables())


async def _seed_users() -> None:
    async with database._session_factory() as session:  # type: ignore[union-attr]
        session.add_all(
            [
                User(uid="owner-1", provider="password", provider_id="owner@example.com", email="owner@example.com", name="Owner", role="user", status="active"),
                User(uid="admin-1", provider="password", provider_id="admin@example.com", email="admin@example.com", name="Admin", role="admin", status="active"),
            ]
        )
        await session.commit()


def _owner_client() -> TestClient:
    token = auth._sign_session({"uid": "owner-1", "email": "owner@example.com"})
    client = TestClient(main.app)
    client.cookies.set("aegis_session", token)
    return client


def _telegram_update(*, sender_id: str, text: str) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "message_id": 9,
            "chat": {"id": 101, "type": "private"},
            "from": {"id": sender_id, "username": "external_user"},
            "text": text,
        },
    }


def test_pairing_policy_blocks_unapproved_and_allows_approved_then_blocks_denied(tmp_path: Path) -> None:
    _init_test_db(tmp_path, "pairing_policy.db")
    asyncio.run(_seed_users())
    settings.SESSION_SECRET = "test-secret"
    stub = _StubTelegramIntegration()
    main.channel_registry.upsert(
        "telegram",
        "tg-1",
        TelegramChannelAdapter(stub),
        {"owner_user_id": "owner-1", "webhook_secret": "x"},
    )

    client = _owner_client()
    policy_resp = client.put(
        "/api/integrations/telegram/tg-1/policy",
        json={"require_pairing": True, "allow_dm": True, "allow_group": False, "allow_unpaired_commands": False},
    )
    assert policy_resp.status_code == 200

    blocked = client.post("/api/integrations/telegram/webhook/tg-1", json=_telegram_update(sender_id="ext-1", text="/run hi"))
    assert blocked.status_code == 200
    assert any("pairing approval is required" in text.lower() for text in stub.sent_texts)

    pending = client.get("/api/integrations/telegram/tg-1/pairing/pending")
    assert pending.status_code == 200
    request_id = pending.json()["requests"][0]["request_id"]

    approved = client.post(f"/api/integrations/telegram/tg-1/pairing/{request_id}/approve")
    assert approved.status_code == 200

    before_len = len(stub.sent_texts)
    allowed = client.post("/api/integrations/telegram/webhook/tg-1", json=_telegram_update(sender_id="ext-1", text="/run hi"))
    assert allowed.status_code == 200
    after_messages = stub.sent_texts[before_len:]
    assert not any("pairing approval is required" in text.lower() for text in after_messages)

    denied = client.post(f"/api/integrations/telegram/tg-1/pairing/{request_id}/deny")
    assert denied.status_code == 200

    blocked_again = client.post("/api/integrations/telegram/webhook/tg-1", json=_telegram_update(sender_id="ext-1", text="/run hi"))
    assert blocked_again.status_code == 200
    assert any("access denied" in text.lower() for text in stub.sent_texts)


def test_pairing_code_is_short_lived_and_one_time(tmp_path: Path) -> None:
    _init_test_db(tmp_path, "pairing_code.db")
    asyncio.run(_seed_users())
    settings.SESSION_SECRET = "test-secret"
    stub = _StubTelegramIntegration()
    main.channel_registry.upsert(
        "telegram",
        "tg-2",
        TelegramChannelAdapter(stub),
        {"owner_user_id": "owner-1", "webhook_secret": "x"},
    )
    client = _owner_client()
    client.put("/api/integrations/telegram/tg-2/policy", json={"require_pairing": True, "allow_dm": True})

    first = client.post("/api/integrations/telegram/webhook/tg-2", json=_telegram_update(sender_id="ext-2", text="/pair"))
    assert first.status_code == 200
    code_message = next(text for text in reversed(stub.sent_texts) if "one-time code" in text.lower())
    code_match = re.search(r"`([A-F0-9]{6})`", code_message)
    assert code_match is not None
    code = code_match.group(1)

    verify_ok = client.post("/api/integrations/telegram/webhook/tg-2", json=_telegram_update(sender_id="ext-2", text=f"/pair {code}"))
    assert verify_ok.status_code == 200
    assert any("code verified" in text.lower() for text in stub.sent_texts)

    verify_again = client.post("/api/integrations/telegram/webhook/tg-2", json=_telegram_update(sender_id="ext-2", text=f"/pair {code}"))
    assert verify_again.status_code == 200
    assert any("invalid or expired pairing code" in text.lower() for text in stub.sent_texts)

    async def _assert_used() -> None:
        async with database._session_factory() as session:  # type: ignore[union-attr]
            row = (
                await session.execute(
                    select(PairedChannelIdentity).where(
                        PairedChannelIdentity.platform == "telegram",
                        PairedChannelIdentity.integration_id == "tg-2",
                        PairedChannelIdentity.external_user_id == "ext-2",
                    )
                )
            ).scalar_one()
            assert row.pairing_code_used_at is not None

    asyncio.run(_assert_used())
