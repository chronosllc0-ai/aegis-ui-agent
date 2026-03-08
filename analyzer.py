"""Screenshot analysis using Gemini multimodal vision."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import logging
import re
from typing import Any

from google import genai

from config import settings

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """You are a UI vision parser.
Analyze this screenshot and return STRICT JSON matching this schema:
{
  "page_type": "string",
  "elements": [
    {
      "description": "string",
      "element_type": "button|link|input|dropdown|checkbox|other",
      "x_pct": 0-100,
      "y_pct": 0-100,
      "state": "string",
      "text": "string"
    }
  ],
  "current_state": "string",
  "navigation_context": "string"
}
No markdown, no prose, only JSON."""


@dataclass
class UIElement:
    """Structured representation of a detected UI element."""

    description: str
    element_type: str
    x_pct: float
    y_pct: float
    state: str
    text: str = ""


@dataclass
class ScreenAnalysis:
    """Structured screenshot analysis from Gemini."""

    page_type: str
    elements: list[UIElement]
    current_state: str
    navigation_context: str
    raw_response: str


class ScreenshotAnalyzer:
    """Analyzes screenshots using Gemini vision to understand UI state."""

    def __init__(self, client: genai.Client) -> None:
        self.client = client
        self.model = settings.GEMINI_MODEL

    async def analyze(self, screenshot_bytes: bytes, task_context: str = "") -> ScreenAnalysis:
        """Analyze screenshot bytes and return structured UI data."""
        prompt = ANALYSIS_PROMPT
        if task_context:
            prompt += f"\nUser goal: {task_context}"

        b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/png", "data": b64_image}},
                    ],
                }
            ],
        )
        raw_text = response.text or "{}"
        parsed = self._parse_response(raw_text)
        elements = [UIElement(**element) for element in parsed.get("elements", [])]
        logger.info("Analyzed screen; detected %s elements", len(elements))

        return ScreenAnalysis(
            page_type=parsed.get("page_type", "unknown"),
            elements=elements,
            current_state=parsed.get("current_state", ""),
            navigation_context=parsed.get("navigation_context", ""),
            raw_response=raw_text,
        )

    async def find_element(self, screenshot_bytes: bytes, description: str) -> dict[str, Any]:
        """Find element coordinates by textual description."""
        task = f"Find this element: {description}. Return JSON: {{\"x\":int,\"y\":int,\"found\":bool,\"confidence\":float}}"
        analysis = await self.analyze(screenshot_bytes, task_context=task)
        if analysis.elements:
            first = analysis.elements[0]
            return {
                "x": int(first.x_pct * settings.VIEWPORT_WIDTH / 100),
                "y": int(first.y_pct * settings.VIEWPORT_HEIGHT / 100),
                "found": True,
                "confidence": 0.5,
            }
        return {"x": 0, "y": 0, "found": False, "confidence": 0.0}

    @staticmethod
    def _parse_response(raw_text: str) -> dict[str, Any]:
        """Parse model response, tolerating code fences and extra text."""
        text = raw_text.strip()
        fenced = re.sub(r"^```json\s*|```$", "", text, flags=re.MULTILINE).strip()
        try:
            data = json.loads(fenced)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", fenced, re.DOTALL)
            if not match:
                return {}
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}

        normalized_elements: list[dict[str, Any]] = []
        for element in data.get("elements", []):
            normalized_elements.append(
                {
                    "description": str(element.get("description", "")),
                    "element_type": str(element.get("element_type", "other")),
                    "x_pct": float(element.get("x_pct", 0.0)),
                    "y_pct": float(element.get("y_pct", 0.0)),
                    "state": str(element.get("state", "unknown")),
                    "text": str(element.get("text", "")),
                }
            )
        data["elements"] = normalized_elements
        return data


async def detect_available_model(client: genai.Client) -> str:
    """Select the best available Gemini model from a preferred list."""
    preferred_models = ["gemini-3-pro", "gemini-2.5-pro-preview-03-25", "gemini-2.5-pro"]
    models = await client.aio.models.list()
    available_names = {model.name.split("/")[-1] for model in models}
    for candidate in preferred_models:
        if candidate in available_names:
            return candidate
    raise ValueError("No supported Gemini model found in account")
