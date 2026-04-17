from __future__ import annotations

from datetime import datetime, timezone

from backend import user_memory


def test_daily_memory_auto_created_and_writable(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(user_memory, "USER_DATA_ROOT", tmp_path)
    session_id = "session-1"

    day = datetime.now(timezone.utc).date().isoformat()
    path = user_memory.ensure_daily_memory_file(session_id)

    assert path.exists()
    assert path.name == f"{day}.md"

    written_day = user_memory.append_daily_memory(session_id, "Met with design", category="notes")
    assert written_day == day
    assert "Met with design" in path.read_text()


def test_long_term_memory_is_separate_from_daily_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(user_memory, "USER_DATA_ROOT", tmp_path)
    session_id = "session-2"

    user_memory.write_memory(session_id, "# MEMORY\n\n## Preferences\n- concise")
    user_memory.append_daily_memory(session_id, "Temporary context", category="context")

    long_term = user_memory.read_long_term_memory(session_id)
    assert "Preferences" in long_term

    short_term_path = user_memory.ensure_daily_memory_file(session_id)
    assert short_term_path.parent.name == "memory"
    assert "Temporary context" in short_term_path.read_text()


def test_read_policy_and_compaction_manual_accept(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(user_memory, "USER_DATA_ROOT", tmp_path)
    session_id = "session-3"

    user_memory.write_memory(session_id, "# MEMORY\n\n## Facts\n- stable fact")
    user_memory.append_daily_memory(session_id, "User mentioned sprint risk", category="status")

    combined_without_long_term = user_memory.read_memory(session_id, include_long_term=False)
    assert "Long-term (MEMORY.md)" not in combined_without_long_term
    assert "Today" in combined_without_long_term
    assert "Yesterday" in combined_without_long_term

    compact_preview = user_memory.compact_daily_memory(session_id, apply_to_long_term=False)
    assert compact_preview["applied"] is False
    assert "Compaction Suggestions" in compact_preview["suggested_patch"]

    compact_apply = user_memory.compact_daily_memory(session_id, apply_to_long_term=True)
    assert compact_apply["applied"] is True
    assert "Compaction Suggestions" in user_memory.read_long_term_memory(session_id)


def test_compaction_preserves_multiline_entry_blocks(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(user_memory, "USER_DATA_ROOT", tmp_path)
    session_id = "session-4"
    day = datetime.now(timezone.utc).date().isoformat()
    path = user_memory.ensure_daily_memory_file(session_id, day=day)
    path.write_text(
        f"# Daily Memory {day}\n\n"
        "## [12:00:00Z] notes\n"
        "We need to fix:\n"
        "1. Memory bugs\n"
        "2. Other bugs\n\n"
    )

    preview = user_memory.compact_daily_memory(session_id, apply_to_long_term=False)
    assert "- [" in preview["suggested_patch"]
    assert "We need to fix:" in preview["suggested_patch"]
    assert "1. Memory bugs" in preview["suggested_patch"]
    assert "2. Other bugs" in preview["suggested_patch"]
