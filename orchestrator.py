"""ADK-based agent orchestrator for UI navigation tasks."""
import logging
from google import genai
from google.adk import Agent, Runner
from google.adk.sessions import InMemorySessionService
from src.agent.navigator import NavigatorAgent
from src.agent.analyzer import ScreenshotAnalyzer
from src.agent.executor import ActionExecutor
from src.utils.config import settings

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrates the UI navigation pipeline using ADK."""

    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.analyzer = ScreenshotAnalyzer(self.client)
        self.executor = ActionExecutor()
        self.navigator = NavigatorAgent(
            analyzer=self.analyzer,
            executor=self.executor,
        )
        self.session_service = InMemorySessionService()

        # Build the ADK agent
        self.agent = Agent(
            name="aegis_navigator",
            model="gemini-3-pro",
            description="An AI agent that navigates UIs by seeing screenshots and executing actions.",
            instruction="""You are Aegis, a UI navigation agent. You help users accomplish tasks 
            on websites and applications by:
            1. Taking screenshots of the current screen state
            2. Analyzing the visual layout to identify interactive elements
            3. Planning a sequence of actions to accomplish the user's goal
            4. Executing actions (click, type, scroll, etc.) step by step
            5. Verifying each action succeeded before proceeding
            
            Always narrate what you're doing so the user can follow along.
            If something unexpected happens (popup, error, CAPTCHA), adapt your approach.
            """,
            tools=[
                self.navigator.take_screenshot,
                self.navigator.analyze_screen,
                self.navigator.click_element,
                self.navigator.type_text,
                self.navigator.scroll_page,
                self.navigator.go_to_url,
                self.navigator.wait_for_load,
                self.navigator.go_back,
            ],
        )

    async def execute_task(self, session_id: str, instruction: str, on_step=None):
        """Execute a UI navigation task from a natural language instruction."""
        logger.info(f"Executing task: {instruction[:100]}...")

        session = self.session_service.get_or_create_session(
            app_name="aegis", user_id="user", session_id=session_id
        )

        runner = Runner(
            agent=self.agent,
            app_name="aegis",
            session_service=self.session_service,
        )

        steps = []
        async for event in runner.run_async(
            user_id="user", session_id=session_id, new_message=instruction
        ):
            step_data = {
                "type": event.type,
                "content": str(event.content) if event.content else None,
            }
            steps.append(step_data)
            if on_step:
                await on_step(step_data)

        return {"status": "completed", "steps": steps}
