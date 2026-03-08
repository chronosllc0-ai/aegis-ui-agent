"""Basic websocket smoke client for local manual testing."""

from __future__ import annotations

import asyncio
import json
import logging

import websockets

from aegis_logging import setup_logging


async def main() -> None:
    """Connect to /ws/navigate and submit a simple navigation instruction."""
    setup_logging()
    logger = logging.getLogger(__name__)
    uri = "ws://127.0.0.1:8080/ws/navigate"
    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({"action": "navigate", "instruction": "go to google.com and search for weather in new york"}))
        for _ in range(2):
            message = await websocket.recv()
            logger.info("Received: %s", message)
        await websocket.send(json.dumps({"action": "stop"}))


if __name__ == "__main__":
    asyncio.run(main())
