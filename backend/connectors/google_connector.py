"""Google OAuth2 connector — Gmail, Google Drive, Google Calendar.

Uses a single OAuth consent that requests scopes for all three services.
The user authorizes once and Aegis can read/send email, manage Drive files,
and query Calendar events.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.connectors.base import BaseConnector, ConnectorAction, OAuthTokens

logger = logging.getLogger(__name__)

_GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
_DRIVE_API = "https://www.googleapis.com/drive/v3"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3"


class GoogleConnector(BaseConnector):
    connector_id = "google"
    display_name = "Google"
    oauth_authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    oauth_token_url = "https://oauth2.googleapis.com/token"
    default_scopes = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]

    def get_authorize_url(self, redirect_uri: str, state: str, scopes: list[str] | None = None) -> str:
        return self._build_authorize_url(
            redirect_uri,
            state,
            scopes,
            extra_params={"access_type": "offline", "prompt": "consent"},
        )

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        data = await self._post_token_request({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        })
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope", ""),
            raw=data,
        )

    async def refresh_tokens(self, refresh_token: str) -> OAuthTokens:
        data = await self._post_token_request({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        })
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=refresh_token,
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope", ""),
            raw=data,
        )

    async def revoke(self, access_token: str) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": access_token},
            )
            return resp.status_code == 200

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()

    def list_actions(self) -> list[ConnectorAction]:
        return [
            ConnectorAction(id="gmail_list_messages", name="List Emails", description="List recent emails from inbox", category="gmail"),
            ConnectorAction(id="gmail_read_message", name="Read Email", description="Read a specific email by ID", parameters={"message_id": "string"}, category="gmail"),
            ConnectorAction(id="gmail_send", name="Send Email", description="Send an email", parameters={"to": "string", "subject": "string", "body": "string"}, category="gmail"),
            ConnectorAction(id="gmail_search", name="Search Emails", description="Search emails by query", parameters={"query": "string"}, category="gmail"),
            ConnectorAction(id="drive_list_files", name="List Files", description="List files in Google Drive", parameters={"query": "string (optional)"}, category="drive"),
            ConnectorAction(id="drive_read_file", name="Read File", description="Read a file's content or metadata", parameters={"file_id": "string"}, category="drive"),
            ConnectorAction(id="drive_upload", name="Upload File", description="Upload a file to Google Drive", parameters={"name": "string", "content": "string", "mime_type": "string"}, category="drive"),
            ConnectorAction(id="calendar_list_events", name="List Events", description="List upcoming calendar events", parameters={"max_results": "int (optional)"}, category="calendar"),
            ConnectorAction(id="calendar_create_event", name="Create Event", description="Create a calendar event", parameters={"summary": "string", "start": "datetime", "end": "datetime"}, category="calendar"),
        ]

    async def execute_action(self, action_id: str, params: dict[str, Any], access_token: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient() as client:
            if action_id == "gmail_list_messages":
                return await self._gmail_list(client, headers, params)
            elif action_id == "gmail_read_message":
                return await self._gmail_read(client, headers, params)
            elif action_id == "gmail_send":
                return await self._gmail_send(client, headers, params)
            elif action_id == "gmail_search":
                return await self._gmail_search(client, headers, params)
            elif action_id == "drive_list_files":
                return await self._drive_list(client, headers, params)
            elif action_id == "drive_read_file":
                return await self._drive_read(client, headers, params)
            elif action_id == "drive_upload":
                return await self._drive_upload(client, headers, params)
            elif action_id == "calendar_list_events":
                return await self._calendar_list(client, headers, params)
            elif action_id == "calendar_create_event":
                return await self._calendar_create(client, headers, params)
            else:
                return {"error": f"Unknown action: {action_id}"}

    # ── Gmail actions ─────────────────────────────────────────────────

    async def _gmail_list(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        max_results = params.get("max_results", 20)
        resp = await client.get(f"{_GMAIL_API}/users/me/messages", headers=headers, params={"maxResults": max_results})
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("messages", [])
        # Fetch snippet for each message
        results = []
        for msg in messages[:max_results]:
            detail = await client.get(f"{_GMAIL_API}/users/me/messages/{msg['id']}", headers=headers, params={"format": "metadata", "metadataHeaders": "Subject,From,Date"})
            if detail.status_code == 200:
                md = detail.json()
                hdrs = {h["name"]: h["value"] for h in md.get("payload", {}).get("headers", [])}
                results.append({"id": msg["id"], "subject": hdrs.get("Subject", ""), "from": hdrs.get("From", ""), "date": hdrs.get("Date", ""), "snippet": md.get("snippet", "")})
        return {"ok": True, "messages": results, "total": data.get("resultSizeEstimate", 0)}

    async def _gmail_read(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        message_id = params.get("message_id", "")
        if not message_id:
            return {"error": "message_id is required"}
        resp = await client.get(f"{_GMAIL_API}/users/me/messages/{message_id}", headers=headers, params={"format": "full"})
        resp.raise_for_status()
        data = resp.json()
        hdrs = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        # Extract body
        body = ""
        payload = data.get("payload", {})
        if payload.get("body", {}).get("data"):
            import base64
            body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        elif payload.get("parts"):
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    import base64
                    body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                    break
        return {"ok": True, "id": data["id"], "subject": hdrs.get("Subject", ""), "from": hdrs.get("From", ""), "date": hdrs.get("Date", ""), "body": body, "snippet": data.get("snippet", "")}

    async def _gmail_send(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        import base64
        to = params.get("to", "")
        subject = params.get("subject", "")
        body_text = params.get("body", "")
        if not to:
            return {"error": "to is required"}
        raw_message = f"To: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body_text}"
        encoded = base64.urlsafe_b64encode(raw_message.encode("utf-8")).decode("utf-8")
        resp = await client.post(f"{_GMAIL_API}/users/me/messages/send", headers=headers, json={"raw": encoded})
        resp.raise_for_status()
        return {"ok": True, "message_id": resp.json().get("id", "")}

    async def _gmail_search(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        query = params.get("query", "")
        resp = await client.get(f"{_GMAIL_API}/users/me/messages", headers=headers, params={"q": query, "maxResults": 20})
        resp.raise_for_status()
        data = resp.json()
        messages = data.get("messages", [])
        results = []
        for msg in messages[:10]:
            detail = await client.get(f"{_GMAIL_API}/users/me/messages/{msg['id']}", headers=headers, params={"format": "metadata", "metadataHeaders": "Subject,From,Date"})
            if detail.status_code == 200:
                md = detail.json()
                hdrs = {h["name"]: h["value"] for h in md.get("payload", {}).get("headers", [])}
                results.append({"id": msg["id"], "subject": hdrs.get("Subject", ""), "from": hdrs.get("From", ""), "snippet": md.get("snippet", "")})
        return {"ok": True, "messages": results}

    # ── Drive actions ─────────────────────────────────────────────────

    async def _drive_list(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        query = params.get("query")
        api_params: dict[str, Any] = {"pageSize": 20, "fields": "files(id,name,mimeType,modifiedTime,size)"}
        if query:
            api_params["q"] = query
        resp = await client.get(f"{_DRIVE_API}/files", headers=headers, params=api_params)
        resp.raise_for_status()
        return {"ok": True, "files": resp.json().get("files", [])}

    async def _drive_read(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        file_id = params.get("file_id", "")
        if not file_id:
            return {"error": "file_id is required"}
        # Get metadata
        resp = await client.get(f"{_DRIVE_API}/files/{file_id}", headers=headers, params={"fields": "id,name,mimeType,size,modifiedTime,webViewLink"})
        resp.raise_for_status()
        metadata = resp.json()
        # Try to export text content for Google Docs
        content = None
        if metadata.get("mimeType", "").startswith("application/vnd.google-apps."):
            export_resp = await client.get(f"{_DRIVE_API}/files/{file_id}/export", headers=headers, params={"mimeType": "text/plain"})
            if export_resp.status_code == 200:
                content = export_resp.text[:10000]
        return {"ok": True, "metadata": metadata, "content": content}

    async def _drive_upload(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        name = params.get("name", "untitled")
        content = params.get("content", "")
        mime_type = params.get("mime_type", "text/plain")
        # Simple media upload
        resp = await client.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers={**headers},
            json={"name": name, "mimeType": mime_type},
        )
        # For simplicity, use resumable upload with metadata + content
        meta_resp = await client.post(
            f"{_DRIVE_API}/files",
            headers=headers,
            json={"name": name, "mimeType": mime_type},
        )
        meta_resp.raise_for_status()
        file_id = meta_resp.json().get("id", "")
        # Update content
        upload_resp = await client.patch(
            f"https://www.googleapis.com/upload/drive/v3/files/{file_id}?uploadType=media",
            headers={**headers, "Content-Type": mime_type},
            content=content.encode("utf-8"),
        )
        upload_resp.raise_for_status()
        return {"ok": True, "file_id": file_id, "name": name}

    # ── Calendar actions ──────────────────────────────────────────────

    async def _calendar_list(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        from datetime import datetime, timezone
        max_results = params.get("max_results", 10)
        now = datetime.now(timezone.utc).isoformat()
        resp = await client.get(
            f"{_CALENDAR_API}/calendars/primary/events",
            headers=headers,
            params={"timeMin": now, "maxResults": max_results, "singleEvents": True, "orderBy": "startTime"},
        )
        resp.raise_for_status()
        events = resp.json().get("items", [])
        return {"ok": True, "events": [{"id": e["id"], "summary": e.get("summary", ""), "start": e.get("start", {}), "end": e.get("end", {}), "htmlLink": e.get("htmlLink", "")} for e in events]}

    async def _calendar_create(self, client: httpx.AsyncClient, headers: dict, params: dict) -> dict:
        summary = params.get("summary", "")
        start = params.get("start", "")
        end = params.get("end", "")
        if not summary or not start or not end:
            return {"error": "summary, start, and end are required"}
        event = {
            "summary": summary,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
        }
        if params.get("description"):
            event["description"] = params["description"]
        resp = await client.post(f"{_CALENDAR_API}/calendars/primary/events", headers=headers, json=event)
        resp.raise_for_status()
        created = resp.json()
        return {"ok": True, "event_id": created["id"], "htmlLink": created.get("htmlLink", "")}
