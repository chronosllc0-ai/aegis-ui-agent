"""Helpers for extracting bounded runtime guidance blocks from skill markdown."""

from __future__ import annotations

import re


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*(?:\n|$)", re.DOTALL)
_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s*(?P<title>.+?)\s*$", re.MULTILINE)


def extract_runtime_guidance_block(markdown: str) -> tuple[str, str]:
    """Extract frontmatter and Runtime Guidance section from markdown.

    Returns a tuple of `(frontmatter, runtime_guidance)`, where each value may be empty.
    This helper is intentionally fail-soft and never raises for malformed markdown.
    """
    text = (markdown or "").replace("\r\n", "\n").strip()
    if not text:
        return "", ""

    frontmatter = ""
    frontmatter_match = _FRONTMATTER_RE.match(text)
    if frontmatter_match:
        frontmatter = frontmatter_match.group("body").strip()
        text = text[frontmatter_match.end() :].lstrip()

    runtime_guidance = _extract_section(text, section_name="Runtime Guidance")
    return frontmatter, runtime_guidance


def _extract_section(markdown_body: str, *, section_name: str) -> str:
    target_heading = section_name.strip().lower()
    for heading_match in _HEADING_RE.finditer(markdown_body):
        heading_title = heading_match.group("title").strip().lower()
        if heading_title != target_heading:
            continue
        level = len(heading_match.group("hashes"))
        start = heading_match.end()
        end = len(markdown_body)
        for next_match in _HEADING_RE.finditer(markdown_body, pos=start):
            next_level = len(next_match.group("hashes"))
            if next_level <= level:
                end = next_match.start()
                break
        return markdown_body[start:end].strip()
    return ""
