from __future__ import annotations

import asyncio

from universal_navigator import UniversalToolExecutor


class _DummyExecutor:
    pass


def test_hybrid_memory_write_requires_auth_before_file_write(monkeypatch) -> None:
    called = {"append": False}

    def _fail_append(*args, **kwargs):
        called["append"] = True
        raise AssertionError("append_daily_memory should not be called without auth in hybrid mode")

    monkeypatch.setattr("universal_navigator.append_daily_memory", _fail_append)

    tool_executor = UniversalToolExecutor(
        _DummyExecutor(),
        session_id="session-auth-check",
        settings={"memory_mode": "hybrid"},
        user_uid=None,
    )

    result = asyncio.run(tool_executor._memory_write({"content": "hello", "category": "general"}))

    assert result == "Memory tools require an authenticated user."
    assert called["append"] is False


def test_hybrid_memory_search_logs_warning_when_db_unavailable(monkeypatch, caplog) -> None:
    caplog.set_level("WARNING")

    import backend.database as database_module

    monkeypatch.setattr(database_module, "_session_factory", None)

    tool_executor = UniversalToolExecutor(
        _DummyExecutor(),
        session_id="session-hybrid-warning",
        settings={"memory_mode": "hybrid", "memory_long_term_main_session_only": False},
        user_uid="user-1",
    )

    result = asyncio.run(tool_executor._memory_search({"query": "anything"}))

    assert '"ok": true' in result
    assert any("hybrid mode without DB session factory" in record.message for record in caplog.records)
