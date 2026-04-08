"""Discord MCP-style integration client."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any

import httpx

from backend.integrations.contracts import ChannelAdapter
from backend.integrations.text_normalization import normalize_for_channel
from integrations.base import BaseIntegration
from integrations.idempotency import DeliveryDeduper

logger = logging.getLogger(__name__)

DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordIntegration(BaseIntegration, ChannelAdapter):
    """Discord adapter with API v10 baseline and interaction-safe updates."""

    name = "discord"

    def __init__(self) -> None:
        self.connected = False
        self._token: str | None = None
        self._guild_id: str | None = None
        self._delivery_deduper = DeliveryDeduper(max_entries=10_000)

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate the bot token and cache guild metadata."""
        token = str(config.get("bot_token", "")).strip()
        guild_id = str(config.get("guild_id", "")).strip()
        self._token = token or None
        self._guild_id = guild_id or None
        if not self._token:
            self.connected = False
            return {"connected": False, "guild": None, "error": "Missing bot token"}

        try:
            data = await self._request("GET", "/users/@me")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Discord auth failed: %s", exc)
            self.connected = False
            return {"connected": False, "guild": self._guild_id, "error": str(exc)}

        if "id" in data:
            self.connected = True
            return {"connected": True, "guild": self._guild_id}

        self.connected = False
        return {"connected": False, "guild": self._guild_id, "error": data.get("message") or "Auth failed"}

    async def disconnect(self) -> None:
        self.connected = False
        self._token = None
        self._guild_id = None
        self._delivery_deduper.clear()

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "discord_get_messages", "description": "Fetch recent channel messages"},
            {"name": "discord_send_message", "description": "Send a message to a channel"},
            {"name": "discord_edit_message", "description": "Edit a message in a channel"},
            {"name": "discord_list_channels", "description": "List channels in a guild"},
            {"name": "discord_send_file", "description": "Upload a file to a channel"},
            {"name": "discord_send_image", "description": "Upload an image to a channel"},
            {"name": "discord_handle_event", "description": "Normalize and process Discord interactions/events"},
        ]

    @staticmethod
    def mode_selector_components(mode_labels: dict[str, str]) -> list[dict[str, Any]]:
        """Build Discord button component rows for mode selection."""
        buttons = [
            {
                "type": 2,
                "style": 2,
                "label": label,
                "custom_id": f"mode:{mode_name}",
            }
            for mode_name, label in mode_labels.items()
        ]
        if not buttons:
            return []
        return [{"type": 1, "components": buttons[:5]}]

    @staticmethod
    def extract_mode_selection(payload: dict[str, Any]) -> str | None:
        """Extract raw mode token from Discord interaction payloads."""
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        custom_id = str(data.get("custom_id") or "").strip()
        if custom_id.startswith("mode:"):
            raw_mode = custom_id[5:].strip().lower().replace("-", "_").replace(" ", "_")
            return raw_mode or None
        return None

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "discord_handle_event":
            payload = params.get("payload") if isinstance(params.get("payload"), dict) else params
            headers = params.get("headers") if isinstance(params.get("headers"), dict) else {}
            return await self.handle_event(payload, {str(k): str(v) for k, v in headers.items()})

        if not self.connected or not self._token:
            return {"ok": False, "tool": tool_name, "error": "Discord integration is not connected"}

        if tool_name == "discord_list_channels":
            return await self._list_channels(params)
        if tool_name == "discord_get_messages":
            return await self._get_messages(params)
        if tool_name == "discord_send_message":
            channel = str(params.get("channel", "")).strip()
            text = str(params.get("text", "")).strip()
            return await self.send_text(channel, text, metadata=params)
        if tool_name == "discord_edit_message":
            channel = str(params.get("channel", "")).strip()
            message_id = str(params.get("message_id") or "").strip()
            text = str(params.get("text", "")).strip()
            return await self.edit_text(channel, message_id, text, metadata=params)
        if tool_name == "discord_send_file":
            channel = str(params.get("channel", "")).strip()
            file_bytes = params.get("file_bytes")
            if isinstance(file_bytes, str):
                file_bytes = file_bytes.encode("utf-8")
            if not isinstance(file_bytes, bytes):
                return {"ok": False, "tool": tool_name, "error": "file_bytes is required"}
            filename = str(params.get("filename") or "upload.bin")
            mime_type = str(params.get("mime_type") or "application/octet-stream")
            caption = str(params.get("caption") or "").strip() or None
            return await self.send_file(channel, file_bytes, filename=filename, mime_type=mime_type, caption=caption)
        if tool_name == "discord_send_image":
            channel = str(params.get("channel", "")).strip()
            image_b64 = str(params.get("image_b64", "")).strip()
            if not image_b64:
                return {"ok": False, "tool": tool_name, "error": "image_b64 is required"}

            try:
                image_bytes = base64.b64decode(image_b64, validate=True)
            except Exception:  # noqa: BLE001
                return {"ok": False, "tool": tool_name, "error": "image_b64 must be valid base64"}
            caption = str(params.get("caption") or "").strip() or None
            result = await self.send_file(channel, image_bytes, filename="frame.png", mime_type="image/png", caption=caption)
            result["tool"] = "discord_send_image"
            return result

        return {"ok": False, "tool": tool_name, "error": "Unsupported tool"}

    async def send_text(self, destination: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send Discord text message to a channel."""
        channel = destination.strip()
        if not channel:
            return {"ok": False, "tool": "discord_send_message", "error": "Channel is required"}
        if not text.strip():
            return {"ok": False, "tool": "discord_send_message", "error": "Text is required"}
        normalized_text, _ = normalize_for_channel(text, channel="discord")

        payload: dict[str, Any] = {"content": normalized_text}
        if metadata and metadata.get("tts"):
            payload["tts"] = bool(metadata["tts"])
        if metadata and isinstance(metadata.get("components"), list):
            payload["components"] = metadata["components"]
        data = await self._request("POST", f"/channels/{channel}/messages", json_payload=payload)
        ok = bool(data.get("id")) if isinstance(data, dict) else False
        return {"ok": ok, "tool": "discord_send_message", "result": data}

    async def edit_text(
        self,
        destination: str,
        message_id: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Edit Discord message text for progressive updates."""
        channel = destination.strip()
        msg_id = message_id.strip()
        if not channel:
            return {"ok": False, "tool": "discord_edit_message", "error": "Channel is required"}
        if not msg_id:
            return {"ok": False, "tool": "discord_edit_message", "error": "message_id is required"}
        if not text.strip():
            return {"ok": False, "tool": "discord_edit_message", "error": "Text is required"}
        normalized_text, _ = normalize_for_channel(text, channel="discord")

        payload: dict[str, Any] = {"content": normalized_text}
        if metadata and metadata.get("allowed_mentions"):
            payload["allowed_mentions"] = metadata["allowed_mentions"]
        data = await self._request("PATCH", f"/channels/{channel}/messages/{msg_id}", json_payload=payload)
        ok = bool(data.get("id")) if isinstance(data, dict) else False
        return {"ok": ok, "tool": "discord_edit_message", "result": data}

    async def send_file(
        self,
        destination: str,
        file_bytes: bytes,
        *,
        filename: str,
        mime_type: str,
        caption: str | None = None,
    ) -> dict[str, Any]:
        """Send file to Discord via multipart attachment upload."""
        channel = destination.strip()
        if not channel:
            return {"ok": False, "tool": "discord_send_file", "error": "Channel is required"}
        if not file_bytes:
            return {"ok": False, "tool": "discord_send_file", "error": "file_bytes is required"}

        attachment = {"id": "0", "filename": filename, "description": caption or ""}
        payload = {"content": caption or "", "attachments": [attachment]}
        files = {
            "payload_json": (None, json.dumps(payload), "application/json"),
            "files[0]": (filename, file_bytes, mime_type),
        }
        data = await self._request("POST", f"/channels/{channel}/messages", files=files)
        ok = bool(data.get("id")) if isinstance(data, dict) else False
        return {"ok": ok, "tool": "discord_send_file", "result": data}

    async def handle_event(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        """Normalize Discord gateway/webhook events into canonical envelopes."""
        delivery_id = str(headers.get("X-Signature-Timestamp") or headers.get("x-signature-timestamp") or payload.get("id") or "")
        if self._delivery_deduper.seen_or_add(delivery_id):
            return {"ok": True, "duplicate": True, "envelope": {"provider": "discord", "deduped": True, "delivery_id": delivery_id}}

        interaction_type = int(payload.get("type", 0) or 0)
        if interaction_type == 1:
            return {
                "ok": True,
                "response": {"type": 1},
                "envelope": {
                    "provider": "discord",
                    "kind": "interaction",
                    "event_type": "PING",
                    "delivery_id": delivery_id,
                    "raw": payload,
                },
            }

        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        user_id = self._extract_user_id(payload)
        text = self._extract_option_value(data)
        message_id = self._extract_message_id(payload)

        envelope = {
            "provider": "discord",
            "kind": "interaction" if interaction_type else "event",
            "event_type": str(data.get("name") or payload.get("t") or "unknown"),
            "destination": str(payload.get("channel_id") or ""),
            "message_id": message_id,
            "user_id": user_id,
            "text": text,
            "raw": payload,
            "delivery_id": delivery_id,
        }

        ack_response = None
        if interaction_type in {2, 3, 5}:
            ack_response = {"type": 5}

        return {"ok": True, "duplicate": False, "response": ack_response, "envelope": envelope}

    async def _list_channels(self, params: dict[str, Any]) -> dict[str, Any]:
        guild_id = str(params.get("guild_id", "")).strip() or self._guild_id
        if not guild_id:
            return {"ok": False, "tool": "discord_list_channels", "error": "Guild ID is required"}
        data = await self._request("GET", f"/guilds/{guild_id}/channels")
        ok = isinstance(data, list)
        return {"ok": ok, "tool": "discord_list_channels", "result": data}

    async def _get_messages(self, params: dict[str, Any]) -> dict[str, Any]:
        channel = str(params.get("channel", "")).strip()
        if not channel:
            return {"ok": False, "tool": "discord_get_messages", "error": "Channel is required"}
        limit = int(params.get("limit", 20))
        data = await self._request("GET", f"/channels/{channel}/messages", params={"limit": limit})
        ok = isinstance(data, list)
        return {"ok": ok, "tool": "discord_get_messages", "result": data}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> Any:
        if not self._token:
            return {"message": "Missing bot token"}

        url = f"{DISCORD_API_BASE}{path}"
        headers = {"Authorization": f"Bot {self._token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            attempt = 0
            while True:
                response = await client.request(method, url, headers=headers, params=params, json=json_payload, files=files)

                try:
                    data = response.json()
                except ValueError:
                    data = {"message": response.text}

                if response.status_code == 429 and attempt < retries:
                    retry_after = 1.0
                    if isinstance(data, dict):
                        raw_retry_after = data.get("retry_after")
                        if isinstance(raw_retry_after, (int, float)) and not isinstance(raw_retry_after, bool):
                            retry_after = float(raw_retry_after)
                        elif isinstance(raw_retry_after, str) and raw_retry_after.strip():
                            try:
                                retry_after = float(raw_retry_after)
                            except (ValueError, OverflowError):
                                retry_after = 1.0
                    logger.warning("Discord rate limited on %s, retrying in %ss", path, retry_after)
                    await asyncio.sleep(retry_after)
                    attempt += 1
                    continue

                if response.status_code >= 400:
                    error = data.get("message") if isinstance(data, dict) else response.text
                    return {
                        "message": error or f"HTTP {response.status_code}",
                        "status": response.status_code,
                        "rate_limited": response.status_code == 429,
                    }

                return data

    def _extract_user_id(self, payload: dict[str, Any]) -> str:
        member = payload.get("member")
        user = payload.get("user")
        if isinstance(member, dict):
            member_user = member.get("user")
            if isinstance(member_user, dict):
                return str(member_user.get("id") or "")
        if isinstance(user, dict):
            return str(user.get("id") or "")
        return ""

    def _extract_option_value(self, data: dict[str, Any]) -> str:
        options = data.get("options")
        if isinstance(options, list) and options:
            first = options[0]
            if isinstance(first, dict):
                return str(first.get("value") or "")
        return ""

    def _extract_message_id(self, payload: dict[str, Any]) -> str:
        message = payload.get("message")
        if isinstance(message, dict):
            return str(message.get("id") or "")
        return ""
