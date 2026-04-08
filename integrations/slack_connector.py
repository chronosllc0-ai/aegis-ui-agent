"""Slack MCP-style integration client."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

import httpx

from backend.integrations.contracts import ChannelAdapter
from backend.integrations.text_normalization import normalize_for_channel
from integrations.base import BaseIntegration
from integrations.idempotency import DeliveryDeduper

logger = logging.getLogger(__name__)

SLACK_API_BASE = "https://slack.com/api"


class SlackIntegration(BaseIntegration, ChannelAdapter):
    """Slack adapter with compatibility wrappers for legacy tool names."""

    name = "slack"

    def __init__(self) -> None:
        self.connected = False
        self._token: str | None = None
        self._workspace: str | None = None
        self._delivery_deduper = DeliveryDeduper(max_entries=10_000)

    async def connect(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate the provided token and store workspace metadata."""
        token = str(config.get("bot_token") or config.get("oauth_token") or "").strip()
        workspace = str(config.get("workspace", "")).strip()
        self._token = token or None
        if not self._token:
            self.connected = False
            self._workspace = None
            return {"connected": False, "workspace": None, "error": "Missing token"}

        try:
            auth = await self._request("GET", "auth.test")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Slack auth test failed: %s", exc)
            self.connected = False
            self._workspace = None
            return {"connected": False, "workspace": None, "error": str(exc)}

        if auth.get("ok"):
            self.connected = True
            self._workspace = str(auth.get("team") or workspace or "") or None
            return {"connected": True, "workspace": self._workspace}

        self.connected = False
        self._workspace = workspace or None
        return {"connected": False, "workspace": self._workspace, "error": auth.get("error") or "Auth failed"}

    async def disconnect(self) -> None:
        self.connected = False
        self._token = None
        self._workspace = None
        self._delivery_deduper.clear()

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": "slack_get_messages", "description": "Fetch recent channel messages"},
            {"name": "slack_send_message", "description": "Post a message to a channel"},
            {"name": "slack_edit_message", "description": "Edit an existing message"},
            {"name": "slack_list_channels", "description": "List channels in the workspace"},
            {"name": "slack_send_file", "description": "Upload a file to a channel"},
            {"name": "slack_handle_event", "description": "Normalize and process inbound Slack events"},
        ]

    @staticmethod
    def mode_selector_blocks(*, current_mode_label: str, mode_labels: dict[str, str]) -> list[dict[str, Any]]:
        """Render Slack Block Kit payload for current mode + selector actions."""
        blocks: list[dict[str, Any]] = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Current mode:* {current_mode_label}"},
            }
        ]
        action_elements = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": label},
                "value": f"mode:{mode_name}",
                "action_id": "mode_select",
            }
            for mode_name, label in mode_labels.items()
        ]
        if action_elements:
            blocks.append({"type": "actions", "elements": action_elements})
        return blocks

    @staticmethod
    def extract_mode_selection(payload: dict[str, Any]) -> str | None:
        """Extract raw mode token from a Slack interaction payload."""
        actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_value = str(action.get("value") or "").strip()
            if action_value.startswith("mode:"):
                raw_mode = action_value[5:].strip().lower().replace("-", "_").replace(" ", "_")
                return raw_mode or None
        return None

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "slack_handle_event":
            payload = params.get("payload") if isinstance(params.get("payload"), dict) else params
            headers = params.get("headers") if isinstance(params.get("headers"), dict) else {}
            return await self.handle_event(payload, {str(k): str(v) for k, v in headers.items()})

        if not self.connected or not self._token:
            return {"ok": False, "tool": tool_name, "error": "Slack integration is not connected"}

        if tool_name == "slack_list_channels":
            return await self._list_channels(params)
        if tool_name == "slack_get_messages":
            return await self._get_messages(params)
        if tool_name == "slack_send_message":
            channel = str(params.get("channel", "")).strip()
            text = str(params.get("text", "")).strip()
            return await self.send_text(channel, text, metadata=params)
        if tool_name == "slack_edit_message":
            channel = str(params.get("channel", "")).strip()
            message_id = str(params.get("message_id") or params.get("ts") or "").strip()
            text = str(params.get("text", "")).strip()
            return await self.edit_text(channel, message_id, text, metadata=params)
        if tool_name == "slack_send_file":
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

        return {"ok": False, "tool": tool_name, "error": "Unsupported tool"}

    async def send_text(self, destination: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a message with optional metadata."""
        channel = destination.strip()
        if not channel:
            return {"ok": False, "tool": "slack_send_message", "error": "Channel is required"}
        if not text.strip():
            return {"ok": False, "tool": "slack_send_message", "error": "Text is required"}
        normalized_text, _ = normalize_for_channel(text, channel="slack")

        payload: dict[str, Any] = {"channel": channel, "text": normalized_text}
        if metadata and metadata.get("thread_ts"):
            payload["thread_ts"] = str(metadata["thread_ts"])
        if metadata and isinstance(metadata.get("blocks"), list):
            payload["blocks"] = metadata["blocks"]
        data = await self._request("POST", "chat.postMessage", json_payload=payload)
        return {"ok": bool(data.get("ok")), "tool": "slack_send_message", "result": data}

    async def edit_text(
        self,
        destination: str,
        message_id: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Edit an existing message via chat.update (stream-safe updates)."""
        channel = destination.strip()
        ts = message_id.strip()
        if not channel:
            return {"ok": False, "tool": "slack_edit_message", "error": "Channel is required"}
        if not ts:
            return {"ok": False, "tool": "slack_edit_message", "error": "message_id/ts is required"}
        if not text.strip():
            return {"ok": False, "tool": "slack_edit_message", "error": "Text is required"}
        normalized_text, _ = normalize_for_channel(text, channel="slack")

        payload: dict[str, Any] = {"channel": channel, "ts": ts, "text": normalized_text}
        if metadata and metadata.get("blocks"):
            payload["blocks"] = metadata["blocks"]
        data = await self._request("POST", "chat.update", json_payload=payload)
        return {"ok": bool(data.get("ok")), "tool": "slack_edit_message", "result": data}

    async def send_file(
        self,
        destination: str,
        file_bytes: bytes,
        *,
        filename: str,
        mime_type: str,
        caption: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file to Slack using external upload flow."""
        channel = destination.strip()
        if not channel:
            return {"ok": False, "tool": "slack_send_file", "error": "Channel is required"}
        if not file_bytes:
            return {"ok": False, "tool": "slack_send_file", "error": "file_bytes is required"}

        prep = await self._request(
            "POST",
            "files.getUploadURLExternal",
            json_payload={"filename": filename, "length": len(file_bytes)},
        )
        if not prep.get("ok"):
            return {"ok": False, "tool": "slack_send_file", "result": prep, "error": prep.get("error", "Upload init failed")}

        upload_url = str(prep.get("upload_url") or "")
        file_id = str(prep.get("file_id") or "")
        if not upload_url or not file_id:
            return {"ok": False, "tool": "slack_send_file", "error": "Slack upload URL exchange failed"}

        async with httpx.AsyncClient(timeout=30) as client:
            upload_response = await client.post(
                upload_url,
                headers={"Content-Type": mime_type},
                content=file_bytes,
            )
        if upload_response.status_code >= 400:
            return {"ok": False, "tool": "slack_send_file", "error": f"Upload binary failed: HTTP {upload_response.status_code}"}

        complete_payload: dict[str, Any] = {
            "files": [{"id": file_id, "title": filename}],
            "channel_id": channel,
        }
        if caption:
            complete_payload["initial_comment"] = caption
        complete = await self._request("POST", "files.completeUploadExternal", json_payload=complete_payload)
        return {"ok": bool(complete.get("ok")), "tool": "slack_send_file", "result": complete}

    async def handle_event(self, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        """Normalize inbound Slack event/interaction payloads with idempotency guards."""
        delivery_id = self._delivery_id(payload, headers)
        if self._delivery_deduper.seen_or_add(delivery_id):
            return {"ok": True, "duplicate": True, "envelope": {"provider": "slack", "deduped": True, "delivery_id": delivery_id}}

        payload_type = str(payload.get("type") or "")
        if payload_type == "url_verification":
            return {
                "ok": True,
                "response": {"challenge": payload.get("challenge", "")},
                "envelope": {
                    "provider": "slack",
                    "kind": "verification",
                    "event_type": "url_verification",
                    "delivery_id": delivery_id,
                },
            }

        event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        envelope = {
            "provider": "slack",
            "kind": "event" if payload_type == "event_callback" else "interaction",
            "event_type": str(event.get("type") or payload.get("command") or payload_type or "unknown"),
            "destination": str(event.get("channel") or payload.get("channel_id") or ""),
            "message_id": str(event.get("ts") or payload.get("message_ts") or ""),
            "user_id": str(event.get("user") or payload.get("user_id") or ""),
            "text": str(event.get("text") or payload.get("text") or ""),
            "raw": payload,
            "delivery_id": delivery_id,
        }
        return {"ok": True, "duplicate": False, "envelope": envelope}

    async def _list_channels(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit", 100))
        cursor = str(params.get("cursor", "")).strip() or None
        payload: dict[str, Any] = {"limit": limit, "types": "public_channel,private_channel"}
        if cursor:
            payload["cursor"] = cursor
        data = await self._request("GET", "conversations.list", params=payload)
        return {"ok": bool(data.get("ok")), "tool": "slack_list_channels", "result": data}

    async def _get_messages(self, params: dict[str, Any]) -> dict[str, Any]:
        channel = str(params.get("channel", "")).strip()
        if not channel:
            return {"ok": False, "tool": "slack_get_messages", "error": "Channel is required"}
        limit = int(params.get("limit", 20))
        payload = {"channel": channel, "limit": limit}
        data = await self._request("GET", "conversations.history", params=payload)
        return {"ok": bool(data.get("ok")), "tool": "slack_get_messages", "result": data}

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        if not self._token:
            return {"ok": False, "error": "Missing token"}

        url = f"{SLACK_API_BASE}/{endpoint}"
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=10) as client:
            attempt = 0
            while True:
                response = await client.request(method, url, headers=headers, params=params, json=json_payload)

                if response.status_code == 429 and attempt < retries:
                    retry_after = 1.0
                    try:
                        retry_after = float(response.headers.get("Retry-After", "1"))
                    except (TypeError, ValueError):
                        retry_after = 1.0
                    logger.warning("Slack rate limited on %s, retrying in %ss", endpoint, retry_after)
                    await asyncio.sleep(retry_after)
                    attempt += 1
                    continue

                try:
                    data = response.json()
                except ValueError:
                    data = {"ok": False, "error": response.text}

                if response.status_code >= 400:
                    error = data.get("error") if isinstance(data, dict) else response.text
                    return {
                        "ok": False,
                        "error": error or f"HTTP {response.status_code}",
                        "status": response.status_code,
                        "rate_limited": response.status_code == 429,
                    }

                if isinstance(data, dict):
                    return data
                return {"ok": False, "error": "Invalid response"}

    def _delivery_id(self, payload: dict[str, Any], headers: dict[str, str]) -> str:
        event_id = str(payload.get("event_id") or "").strip()
        if event_id:
            return f"event:{event_id}"
        normalized = {k.lower(): v for k, v in headers.items()}
        signature = str(normalized.get("x-slack-signature") or "").strip()
        timestamp = str(normalized.get("x-slack-request-timestamp") or "").strip()
        if signature and timestamp:
            return f"sig:{timestamp}:{signature}"
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return f"fallback:{digest}"
