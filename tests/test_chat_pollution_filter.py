from __future__ import annotations

import pytest

import main


@pytest.mark.parametrize(
    ('step', 'expected'),
    [
        ({'type': 'workflow_step', 'content': 'Navigate to site'}, True),
        ({'type': 'step', 'content': '[extract_page] reading page'}, True),
        ({'type': 'result', 'content': 'Final synthesis: completed'}, True),
        ({'type': 'result', 'content': 'Code summary: delegated implementation finished'}, True),
        ({'type': 'result', 'content': 'Outcome: completed. Specialist mode: code. Worker refs: child:primary.'}, True),
        ({'type': 'result', 'content': 'Task completed'}, True),
        ({'type': 'result', 'content': 'Task completed.'}, True),
        ({'type': 'result', 'content': 'Task completed: open github'}, False),
        ({'type': 'result', 'content': "I'll navigate to that URL to see what the site contains."}, False),
        ({'type': 'assistant_message', 'content': 'Visible assistant text'}, False),
    ],
)
def test_is_browser_chat_pollution(step: dict[str, str], expected: bool) -> None:
    assert main._is_browser_chat_pollution(step) is expected
