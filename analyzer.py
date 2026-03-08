"""Screenshot analysis using Gemini multimodal vision."""
import base64
import logging
from dataclasses import dataclass
from google import genai

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """Analyze this screenshot of a UI. Identify and describe:

1. **Page type**: What kind of page/app is this? (e.g., search results, form, dashboard)
2. **Interactive elements**: List all clickable buttons, links, input fields, dropdowns, checkboxes with:
   - Description of the element
   - Approximate location (x, y coordinates as percentage of screen)
   - Current state (enabled/disabled, checked/unchecked, filled/empty)
3. **Current state**: What content is displayed? Any errors, loading indicators, or popups?
4. **Navigation context**: Where are we in the app flow? What's the URL/title if visible?

Return structured JSON with the above fields."""


@dataclass
class UIElement:
    description: str
    element_type: str  # button, link, input, dropdown, etc.
    x_pct: float  # x position as percentage
    y_pct: float  # y position as percentage
    state: str
    text: str = ""


@dataclass
class ScreenAnalysis:
    page_type: str
    elements: list[UIElement]
    current_state: str
    navigation_context: str
    raw_response: str


class ScreenshotAnalyzer:
    """Analyzes screenshots using Gemini vision to understand UI state."""

    def __init__(self, client: genai.Client):
        self.client = client
        self.model = "gemini-3-pro"

    async def analyze(self, screenshot_bytes: bytes, task_context: str = "") -> ScreenAnalysis:
        """Analyze a screenshot and return structured UI understanding."""
        b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")

        prompt = ANALYSIS_PROMPT
        if task_context:
            prompt += f"\n\nThe user is trying to: {task_context}\nHighlight elements relevant to this goal."

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                {"role": "user", "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/png", "data": b64_image}},
                ]},
            ],
        )

        # Parse the response into structured data
        raw_text = response.text
        logger.info(f"Screen analysis complete: {raw_text[:200]}...")

        return ScreenAnalysis(
            page_type="detected",
            elements=[],
            current_state=raw_text,
            navigation_context="",
            raw_response=raw_text,
        )

    async def find_element(self, screenshot_bytes: bytes, description: str) -> tuple[float, float]:
        """Find a specific element on screen and return its coordinates."""
        b64_image = base64.b64encode(screenshot_bytes).decode("utf-8")

        response = self.client.models.generate_content(
            model=self.model,
            contents=[
                {"role": "user", "parts": [
                    {"text": f"""Look at this screenshot and find the element described as: "{description}"
                    Return ONLY the x,y pixel coordinates of the center of that element as JSON: 
                    {{"x": <pixels>, "y": <pixels>, "found": true/false, "confidence": 0-1}}"""},
                    {"inline_data": {"mime_type": "image/png", "data": b64_image}},
                ]},
            ],
        )

        logger.info(f"Element search for '{description}': {response.text[:200]}")
        return response.text
