"""Shared stream-safe text normalization and channel formatting adapters."""

from __future__ import annotations

from dataclasses import dataclass
import html
import re
from typing import Literal

ChannelName = Literal["web", "telegram", "slack", "discord"]

_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TELEGRAM_MARKDOWN_V2_SPECIALS_PATTERN = re.compile(r"([_*\[\]()~`>#+\-=|{}.!])")
_DISCORD_MARKDOWN_SPECIALS_PATTERN = re.compile(r"([\\*_{}\[\]()#+\-.!|>~])")


def _split_by_code_fences(text: str) -> list[tuple[bool, str]]:
    """Split text into (is_code, segment) pairs using triple-backtick fences."""
    parts: list[tuple[bool, str]] = []
    fence = "```"
    index = 0
    inside_code = False
    while index < len(text):
        fence_index = text.find(fence, index)
        if fence_index < 0:
            parts.append((inside_code, text[index:]))
            break
        if fence_index > index:
            parts.append((inside_code, text[index:fence_index]))
        parts.append((inside_code, fence))
        inside_code = not inside_code
        index = fence_index + len(fence)
    if not parts:
        return [(False, "")]
    return parts


def _normalize_non_code_segment(text: str) -> str:
    """Normalize newline artifacts and control chars for plain markdown text."""
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    normalized = _CONTROL_CHAR_PATTERN.sub("", normalized)
    return normalized


def normalize_text_preserving_markdown(text: str) -> str:
    """Normalize text incrementally while preserving markdown/code-fence integrity."""
    segments = _split_by_code_fences(text)
    normalized_parts: list[str] = []
    for is_code, segment in segments:
        if segment == "```":
            normalized_parts.append(segment)
            continue
        if is_code:
            code_clean = segment.replace("\r\n", "\n").replace("\r", "\n")
            normalized_parts.append(_CONTROL_CHAR_PATTERN.sub("", code_clean))
        else:
            normalized_parts.append(_normalize_non_code_segment(segment))
    return "".join(normalized_parts)


def _escape_for_telegram(text: str, parse_mode: str | None) -> tuple[str, str | None]:
    mode = (parse_mode or "").strip()
    if not mode:
        return text, None
    lowered = mode.lower()
    if lowered == "html":
        return html.escape(text, quote=False), "HTML"
    if lowered in {"markdownv2", "markdown2"}:
        escaped_parts: list[str] = []
        for is_code, segment in _split_by_code_fences(text):
            if segment == "```" or is_code:
                escaped_parts.append(segment)
            else:
                escaped_parts.append(_TELEGRAM_MARKDOWN_V2_SPECIALS_PATTERN.sub(r"\\\1", segment))
        return "".join(escaped_parts), "MarkdownV2"
    if lowered == "markdown":
        escaped_parts: list[str] = []
        for is_code, segment in _split_by_code_fences(text):
            if segment == "```" or is_code:
                escaped_parts.append(segment)
            else:
                escaped_parts.append(segment.replace("_", r"\_").replace("*", r"\*").replace("`", r"\`"))
        escaped = "".join(escaped_parts)
        return escaped, "Markdown"
    return text, mode


def _escape_for_slack(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_for_discord(text: str) -> str:
    escaped_parts: list[str] = []
    for is_code, segment in _split_by_code_fences(text):
        if segment == "```" or is_code:
            escaped_parts.append(segment)
        else:
            escaped_parts.append(_DISCORD_MARKDOWN_SPECIALS_PATTERN.sub(r"\\\1", segment))
    safe = "".join(escaped_parts)
    safe = safe.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    return safe


def normalize_for_channel(
    text: str,
    *,
    channel: ChannelName,
    parse_mode: str | None = None,
) -> tuple[str, str | None]:
    """Normalize stream text and apply channel-specific escaping rules."""
    normalized = normalize_text_preserving_markdown(text)
    if channel == "telegram":
        return _escape_for_telegram(normalized, parse_mode)
    if channel == "slack":
        return _escape_for_slack(normalized), None
    if channel == "discord":
        return _escape_for_discord(normalized), None
    return normalized, None


@dataclass
class IncrementalTextNormalizer:
    """Stateful stream normalizer used for chunk-level rendering + final pass."""

    channel: ChannelName
    parse_mode: str | None = None
    _raw_text: str = ""

    def push(self, chunk: str) -> str:
        """Append a stream chunk and return normalized cumulative text."""
        self._raw_text += chunk
        normalized, _ = normalize_for_channel(self._raw_text, channel=self.channel, parse_mode=self.parse_mode)
        return normalized

    def finalize(self) -> str:
        """Return fully normalized text for reconciliation at stream completion."""
        normalized, _ = normalize_for_channel(self._raw_text, channel=self.channel, parse_mode=self.parse_mode)
        return normalized
