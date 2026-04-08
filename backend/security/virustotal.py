"""VirusTotal scanning helpers and risk-tag mapping utilities."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from config import settings

RiskTag = Literal["clean", "low_risk", "suspicious", "malicious", "scan_pending", "scan_failed"]


async def submit_file_for_scan(*, file_name: str, content: bytes) -> dict[str, Any]:
    """Submit a file hash/content to VirusTotal and return queued/completed metadata."""
    now = datetime.now(timezone.utc)
    if not settings.VIRUSTOTAL_ENABLED:
        return {"status": "disabled", "risk_tag": "scan_failed", "raw_json": {"reason": "disabled"}, "scanned_at": now}
    if not settings.VIRUSTOTAL_API_KEY:
        return {"status": "failed", "risk_tag": "scan_failed", "raw_json": {"reason": "missing_api_key"}, "scanned_at": now}

    headers = {"x-apikey": settings.VIRUSTOTAL_API_KEY}
    timeout = httpx.Timeout(settings.VIRUSTOTAL_TIMEOUT_SECONDS)
    sha256 = hashlib.sha256(content).hexdigest()

    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        lookup = await client.get(f"https://www.virustotal.com/api/v3/files/{sha256}")
        if lookup.status_code == 200:
            data = lookup.json()
            return {
                "status": "completed",
                "analysis_id": data.get("data", {}).get("id"),
                "sha256": sha256,
                "raw_json": data,
                "report_url": f"https://www.virustotal.com/gui/file/{sha256}",
                "scanned_at": now,
            }
        if lookup.status_code != 404:
            return {
                "status": "failed",
                "sha256": sha256,
                "raw_json": {"reason": "lookup_failed", "status_code": lookup.status_code},
                "report_url": f"https://www.virustotal.com/gui/file/{sha256}",
                "scanned_at": now,
            }

        upload = await client.post(
            "https://www.virustotal.com/api/v3/files",
            files={"file": (file_name, content, "application/octet-stream")},
        )
        if upload.status_code >= 400:
            return {
                "status": "failed",
                "sha256": sha256,
                "raw_json": {"reason": "upload_failed", "status_code": upload.status_code},
                "report_url": None,
                "scanned_at": now,
            }

        upload_data = upload.json()
        analysis_id = upload_data.get("data", {}).get("id")
        return {
            "status": "queued",
            "analysis_id": analysis_id,
            "sha256": sha256,
            "raw_json": upload_data,
            "report_url": f"https://www.virustotal.com/gui/file/{sha256}",
            "scanned_at": now,
        }


async def fetch_scan_report(*, analysis_id: str | None, sha256: str | None) -> dict[str, Any]:
    """Fetch a VirusTotal report with bounded polling for queued scans."""
    now = datetime.now(timezone.utc)
    if not settings.VIRUSTOTAL_ENABLED:
        return {"status": "disabled", "risk_tag": "scan_failed", "raw_json": {"reason": "disabled"}, "scanned_at": now}
    if not settings.VIRUSTOTAL_API_KEY:
        return {"status": "failed", "risk_tag": "scan_failed", "raw_json": {"reason": "missing_api_key"}, "scanned_at": now}

    headers = {"x-apikey": settings.VIRUSTOTAL_API_KEY}
    timeout = httpx.Timeout(settings.VIRUSTOTAL_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        if analysis_id:
            max_polls = max(1, int(settings.VIRUSTOTAL_MAX_POLLS))
            for _ in range(max_polls):
                analysis = await client.get(f"https://www.virustotal.com/api/v3/analyses/{analysis_id}")
                if analysis.status_code >= 400:
                    return {
                        "status": "failed",
                        "risk_tag": "scan_failed",
                        "raw_json": {"reason": "analysis_fetch_failed", "status_code": analysis.status_code},
                        "scanned_at": datetime.now(timezone.utc),
                    }
                payload = analysis.json()
                status = payload.get("data", {}).get("attributes", {}).get("status")
                if status == "completed":
                    break
                await asyncio.sleep(settings.VIRUSTOTAL_POLL_INTERVAL_SECONDS)
            else:
                return {
                    "status": "pending",
                    "risk_tag": "scan_pending",
                    "raw_json": {"reason": "analysis_timeout", "analysis_id": analysis_id},
                    "scanned_at": datetime.now(timezone.utc),
                }

        if not sha256:
            return {
                "status": "failed",
                "risk_tag": "scan_failed",
                "raw_json": {"reason": "missing_sha256"},
                "scanned_at": datetime.now(timezone.utc),
            }

        report = await client.get(f"https://www.virustotal.com/api/v3/files/{sha256}")
        if report.status_code == 404:
            return {
                "status": "pending",
                "risk_tag": "scan_pending",
                "raw_json": {"reason": "report_not_found", "sha256": sha256},
                "report_url": f"https://www.virustotal.com/gui/file/{sha256}",
                "scanned_at": datetime.now(timezone.utc),
            }
        if report.status_code >= 400:
            return {
                "status": "failed",
                "risk_tag": "scan_failed",
                "raw_json": {"reason": "report_fetch_failed", "status_code": report.status_code, "sha256": sha256},
                "report_url": f"https://www.virustotal.com/gui/file/{sha256}",
                "scanned_at": datetime.now(timezone.utc),
            }

        report_json = report.json()
        risk_tag = map_report_to_risk_tag(report_json)
        return {
            "status": "completed",
            "risk_tag": risk_tag,
            "raw_json": report_json,
            "report_url": f"https://www.virustotal.com/gui/file/{sha256}",
            "scanned_at": datetime.now(timezone.utc),
        }


def map_report_to_risk_tag(report: dict[str, Any] | None) -> RiskTag:
    """Map a VirusTotal file report payload into normalized skill risk tags."""
    if not isinstance(report, dict):
        return "scan_failed"

    attributes = report.get("data", {}).get("attributes", {})
    stats = attributes.get("last_analysis_stats") or attributes.get("stats") or {}
    harmless = int(stats.get("harmless", 0))
    malicious = int(stats.get("malicious", 0))
    suspicious = int(stats.get("suspicious", 0))
    undetected = int(stats.get("undetected", 0))
    total = harmless + malicious + suspicious + undetected

    if malicious > 0:
        return "malicious"
    if suspicious > 0:
        return "suspicious"
    if total <= 0:
        return "scan_pending"
    if undetected > 0 and harmless == 0:
        return "low_risk"
    return "clean"
