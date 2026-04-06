"""Snapshot-style coverage for shared text normalization and channel adapters."""

from __future__ import annotations

from backend.integrations.text_normalization import IncrementalTextNormalizer, normalize_for_channel


def test_channel_normalization_snapshots() -> None:
    raw = "Hello\\nWorld\r\n\u0007```python\r\nprint('x\\\\n')\n```\n<&>"
    web_text, _ = normalize_for_channel(raw, channel="web")
    telegram_text, telegram_mode = normalize_for_channel(raw, channel="telegram", parse_mode="MarkdownV2")
    slack_text, _ = normalize_for_channel(raw, channel="slack")
    discord_text, _ = normalize_for_channel(raw, channel="discord")

    assert web_text == "Hello\nWorld\n```python\nprint('x\\\\n')\n```\n<&>"
    assert telegram_mode == "MarkdownV2"
    assert telegram_text == "Hello\nWorld\n```python\nprint('x\\\\n')\n```\n<&\\>"
    assert slack_text == "Hello\nWorld\n```python\nprint('x\\\\n')\n```\n&lt;&amp;&gt;"
    assert discord_text == "Hello\nWorld\n```python\nprint('x\\\\n')\n```\n<&\\>"


def test_incremental_streaming_normalizer_supports_partial_chunks_and_final_reconcile() -> None:
    normalizer = IncrementalTextNormalizer(channel="web")

    c1 = normalizer.push("Line 1\\nLi")
    c2 = normalizer.push("ne 2\r\n```py")
    c3 = normalizer.push("\nprint('ok')\n```")
    final_text = normalizer.finalize()

    assert c1 == "Line 1\nLi"
    assert c2 == "Line 1\nLine 2\n```py"
    assert c3 == "Line 1\nLine 2\n```py\nprint('ok')\n```"
    assert final_text == c3
