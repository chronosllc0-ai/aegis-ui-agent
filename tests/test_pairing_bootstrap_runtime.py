"""Pairing approval bootstrap wake regressions."""

from __future__ import annotations

import asyncio
from pathlib import Path

import backend.session_workspace as session_workspace
from backend.runtime_telemetry import RuntimeEventStore
from backend.workspace_files_service import consume_session_bootstrap_file
import main


def test_consume_session_bootstrap_file_archives_once(tmp_path: Path, monkeypatch) -> None:
    """BOOTSTRAP.md should be archived (not deleted) and consumed only once."""
    monkeypatch.setattr(session_workspace, "SESSION_WORKSPACE_ROOT", tmp_path)
    session_id = "bot-owner-1"
    files_root = session_workspace.get_session_files_root(session_id)
    bootstrap_file = files_root / "BOOTSTRAP.md"
    bootstrap_file.write_text("wake up", encoding="utf-8")

    archived = consume_session_bootstrap_file(session_id)
    archived_again = consume_session_bootstrap_file(session_id)

    assert archived is not None
    assert archived.exists()
    assert archived.name.startswith("BOOTSTRAP.consumed.")
    assert not bootstrap_file.exists()
    assert archived_again is None


def test_pairing_approval_wakes_runtime_and_emits_bootstrap_events(monkeypatch) -> None:
    """Approvals should wake owner runtime and log bootstrap load/consume events once."""

    async def _fake_send_channel_text(*args, **kwargs):  # noqa: ANN002, ANN003
        return {"ok": True}

    async def _fake_publish_to_user(*args, **kwargs):  # noqa: ANN002, ANN003
        return 1

    async def _fake_materialize(*args, **kwargs):  # noqa: ANN002, ANN003
        return None

    session_closed = False

    async def _fake_get_session():
        nonlocal session_closed
        try:
            yield object()
        finally:
            session_closed = True

    file_store: dict[str, str] = {
        "AGENTS.md": "# agents",
        "BOOTSTRAP.md": "# bootstrap",
    }

    def _fake_load(session_id: str, file_name: str) -> str | None:
        return file_store.get(file_name)

    def _fake_consume(session_id: str) -> Path | None:
        if "BOOTSTRAP.md" not in file_store:
            return None
        file_store.pop("BOOTSTRAP.md", None)
        return Path(f"/tmp/aegis-session-workspaces/{session_id}/files/BOOTSTRAP.consumed.20260418T000000Z.md")

    monkeypatch.setattr(main, "_send_channel_text", _fake_send_channel_text)
    monkeypatch.setattr(main.session_events, "publish_to_user", _fake_publish_to_user)
    monkeypatch.setattr(main, "materialize_workspace_files_for_session_safe", _fake_materialize)
    monkeypatch.setattr(main, "load_session_workspace_file", _fake_load)
    monkeypatch.setattr(main, "consume_session_bootstrap_file", _fake_consume)
    monkeypatch.setattr(main, "get_session", _fake_get_session)

    main._user_runtimes.clear()
    main._session_runtimes.clear()
    main.runtime_events = RuntimeEventStore(ttl_seconds=6 * 60 * 60, max_events=10000)

    async def _run() -> None:
        await main._post_pairing_approval_effects(
            platform="telegram",
            integration_id="integration-1",
            owner_uid="owner-1",
            external_channel_id="chat-1",
        )
        first_runtime = main._user_runtimes.get("owner-1")
        await main._post_pairing_approval_effects(
            platform="telegram",
            integration_id="integration-1",
            owner_uid="owner-1",
            external_channel_id="chat-1",
        )
        second_runtime = main._user_runtimes.get("owner-1")
        assert first_runtime is not None
        assert first_runtime is second_runtime

    asyncio.run(_run())
    assert session_closed is True

    events = main.runtime_events.list_events(session_id="bot_owner-1", limit=30)["events"]
    categories = [str(event["category"]) for event in events]
    assert "pairing_approved" in categories
    assert "bootstrap_loaded" in categories
    bootstrap_consumed_events = [event for event in events if event["category"] == "bootstrap_consumed"]
    assert len(bootstrap_consumed_events) == 1
    assert str(bootstrap_consumed_events[0]["details"].get("archived_name", "")).startswith("BOOTSTRAP.consumed.")
