"""Transactional email service using the Resend API.

All outgoing emails go through this module.  We use httpx directly
(already in requirements.txt) so no extra package is required.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"
_FROM_ADDRESS = "Aegis <noreply@mohex.org>"

# ── Brand tokens ─────────────────────────────────────────────────────────────

_BRAND_BG = "#050C18"
_BRAND_CARD = "#0D1B2E"
_BRAND_BORDER = "#1A2E45"
_BRAND_CYAN = "#00D4FF"
_BRAND_CYAN_DIM = "#0099BB"
_BRAND_TEXT = "#E2E8F0"
_BRAND_MUTED = "#64748B"

# ── Shield SVG logo (inline) ─────────────────────────────────────────────────

_SHIELD_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="48" viewBox="0 0 40 48" fill="none">'
    '<path d="M20 2L4 9v12c0 10.5 6.8 20.3 16 23.4C29.2 41.3 36 31.5 36 21V9L20 2z" '
    'fill="#00D4FF" fill-opacity="0.15" stroke="#00D4FF" stroke-width="1.5"/>'
    '<path d="M14 24l4 4 8-8" stroke="#00D4FF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
    '</svg>'
)

# ── HTML wrapper ─────────────────────────────────────────────────────────────


def _wrap_html(body_html: str) -> str:
    """Wrap body content in the branded Aegis email shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Aegis</title>
  <style>
    body {{ margin: 0; padding: 0; background-color: {_BRAND_BG}; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
    a {{ color: {_BRAND_CYAN}; text-decoration: none; }}
  </style>
</head>
<body style="background-color:{_BRAND_BG}; margin:0; padding:0;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{_BRAND_BG}; padding: 40px 16px;">
    <tr>
      <td align="center">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:580px;">
          <!-- Header -->
          <tr>
            <td align="center" style="padding-bottom:32px;">
              <table cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="padding-right:12px; vertical-align:middle;">{_SHIELD_SVG}</td>
                  <td style="vertical-align:middle;">
                    <span style="font-size:22px; font-weight:700; letter-spacing:0.05em; color:{_BRAND_TEXT};">AEGIS</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Card -->
          <tr>
            <td style="background-color:{_BRAND_CARD}; border:1px solid {_BRAND_BORDER}; border-radius:12px; padding:40px 36px;">
              {body_html}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td align="center" style="padding-top:28px;">
              <p style="margin:0; font-size:11px; color:{_BRAND_MUTED}; line-height:1.6;">
                © 2025 Aegis · <a href="https://mohex.org" style="color:{_BRAND_MUTED};">mohex.org</a><br/>
                You received this email because you have an Aegis account.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _cta_button(label: str, url: str) -> str:
    return (
        f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:28px;">'
        f'<tr><td align="center">'
        f'<a href="{url}" style="display:inline-block; background-color:{_BRAND_CYAN}; color:#000; '
        f'font-size:14px; font-weight:700; letter-spacing:0.03em; padding:13px 36px; '
        f'border-radius:8px; text-decoration:none;">{label}</a>'
        f'</td></tr></table>'
    )


# ── Resend HTTP call ──────────────────────────────────────────────────────────


async def _send(*, to: str, subject: str, html: str, from_address: str | None = None) -> None:
    """Low-level send via Resend API.  Raises on failure so callers can handle errors."""
    if not settings.RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is not configured on this server")

    # Validate custom from_address — must end in @mohex.org for safety
    sender = _FROM_ADDRESS
    if from_address:
        import re
        # Extract the email part from "Name <email>" or bare "email"
        match = re.search(r"[\w._%+\-]+@mohex\.org", from_address, re.IGNORECASE)
        if match:
            sender = from_address
        else:
            logger.warning("Ignoring invalid from_address (not @mohex.org): %s", from_address)

    payload: dict[str, Any] = {
        "from": sender,
        "to": [to],
        "subject": subject,
        "html": html,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            _RESEND_API_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
        )
    if resp.status_code >= 400:
        # Surface the actual Resend error message for debugging
        try:
            err_body = resp.json()
            err_msg = err_body.get("message") or err_body.get("name") or resp.text[:200]
        except Exception:  # noqa: BLE001
            err_msg = resp.text[:200]
        logger.error("Resend API error %s sending to %s: %s", resp.status_code, to, err_msg)
        raise RuntimeError(f"Resend error ({resp.status_code}): {err_msg}")
    logger.info("Email sent to %s — subject: %s", to, subject)


# ── Public email helpers ──────────────────────────────────────────────────────


async def send_welcome_email(email: str, name: str) -> None:
    """Send a welcome email to a newly registered user."""
    display_name = name or email.split("@")[0]
    body = f"""
      <h1 style="margin:0 0 8px; font-size:24px; font-weight:700; color:{_BRAND_TEXT};">
        Welcome to Aegis, {display_name}! 🎉
      </h1>
      <p style="margin:0 0 24px; font-size:15px; color:{_BRAND_MUTED}; line-height:1.7;">
        Your intelligent AI workspace is ready. Here's what you get with your account:
      </p>

      <!-- Feature list -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:8px;">
        <tr>
          <td style="padding:10px 0; border-bottom:1px solid {_BRAND_BORDER};">
            <span style="color:{_BRAND_CYAN}; font-size:14px; margin-right:10px;">✦</span>
            <span style="font-size:14px; color:{_BRAND_TEXT}; font-weight:600;">Monthly credit allowance</span>
            <span style="font-size:13px; color:{_BRAND_MUTED}; display:block; margin-left:24px;">
              Use credits across all supported AI providers.
            </span>
          </td>
        </tr>
        <tr>
          <td style="padding:10px 0; border-bottom:1px solid {_BRAND_BORDER};">
            <span style="color:{_BRAND_CYAN}; font-size:14px; margin-right:10px;">✦</span>
            <span style="font-size:14px; color:{_BRAND_TEXT}; font-weight:600;">Multi-provider AI access</span>
            <span style="font-size:13px; color:{_BRAND_MUTED}; display:block; margin-left:24px;">
              OpenAI, Anthropic, Google Gemini, xAI and more in one place.
            </span>
          </td>
        </tr>
        <tr>
          <td style="padding:10px 0; border-bottom:1px solid {_BRAND_BORDER};">
            <span style="color:{_BRAND_CYAN}; font-size:14px; margin-right:10px;">✦</span>
            <span style="font-size:14px; color:{_BRAND_TEXT}; font-weight:600;">Bring Your Own Keys (BYOK)</span>
            <span style="font-size:13px; color:{_BRAND_MUTED}; display:block; margin-left:24px;">
              Connect your own provider API keys for unlimited usage.
            </span>
          </td>
        </tr>
        <tr>
          <td style="padding:10px 0;">
            <span style="color:{_BRAND_CYAN}; font-size:14px; margin-right:10px;">✦</span>
            <span style="font-size:14px; color:{_BRAND_TEXT}; font-weight:600;">Conversation history</span>
            <span style="font-size:13px; color:{_BRAND_MUTED}; display:block; margin-left:24px;">
              All your chats saved and searchable, forever.
            </span>
          </td>
        </tr>
      </table>

      {_cta_button("Open Aegis →", "https://mohex.org")}

      <p style="margin-top:28px; font-size:13px; color:{_BRAND_MUTED}; line-height:1.6; text-align:center;">
        Questions? Reply to this email or visit our support page.
      </p>
    """
    await _send(to=email, subject="Welcome to Aegis", html=_wrap_html(body))


async def send_magic_link_email(email: str, code: str) -> None:
    """Send a one-time sign-in code via Resend (replaces SMTP path)."""
    body = f"""
      <h1 style="margin:0 0 8px; font-size:22px; font-weight:700; color:{_BRAND_TEXT};">
        Your sign-in code
      </h1>
      <p style="margin:0 0 28px; font-size:14px; color:{_BRAND_MUTED}; line-height:1.7;">
        Use the code below to sign in to your Aegis account. It expires in 10 minutes.
      </p>

      <!-- Code block -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:28px;">
        <tr>
          <td align="center" style="background-color:{_BRAND_BG}; border:1px solid {_BRAND_BORDER};
              border-radius:8px; padding:24px;">
            <span style="font-size:36px; font-weight:700; letter-spacing:0.18em; color:{_BRAND_CYAN};
                font-family: 'Courier New', monospace;">{code}</span>
          </td>
        </tr>
      </table>

      <p style="margin:0; font-size:13px; color:{_BRAND_MUTED}; line-height:1.6; text-align:center;">
        If you didn't request this code, you can safely ignore this email.
      </p>
    """
    await _send(to=email, subject="Your Aegis sign-in code", html=_wrap_html(body))


async def send_plan_upgrade_email(email: str, name: str, new_plan: str, new_allowance: int) -> None:
    """Send a plan upgrade confirmation email."""
    display_name = name or email.split("@")[0]
    plan_label = new_plan.title()
    body = f"""
      <h1 style="margin:0 0 8px; font-size:22px; font-weight:700; color:{_BRAND_TEXT};">
        Plan upgraded — you're on {plan_label}! 🚀
      </h1>
      <p style="margin:0 0 24px; font-size:14px; color:{_BRAND_MUTED}; line-height:1.7;">
        Hi {display_name}, your Aegis plan has been upgraded to <strong style="color:{_BRAND_TEXT};">{plan_label}</strong>.
      </p>

      <table width="100%" cellpadding="0" cellspacing="0" border="0"
          style="background-color:{_BRAND_BG}; border:1px solid {_BRAND_BORDER}; border-radius:8px;
          margin-bottom:28px; padding:20px 24px;">
        <tr>
          <td>
            <p style="margin:0 0 6px; font-size:12px; color:{_BRAND_MUTED}; text-transform:uppercase;
                letter-spacing:0.08em;">Your new plan</p>
            <p style="margin:0; font-size:20px; font-weight:700; color:{_BRAND_CYAN};">{plan_label}</p>
          </td>
          <td align="right">
            <p style="margin:0 0 6px; font-size:12px; color:{_BRAND_MUTED}; text-transform:uppercase;
                letter-spacing:0.08em;">Monthly credits</p>
            <p style="margin:0; font-size:20px; font-weight:700; color:{_BRAND_TEXT};">
                {new_allowance:,}</p>
          </td>
        </tr>
      </table>

      {_cta_button("Go to Dashboard →", "https://mohex.org")}

      <p style="margin-top:24px; font-size:13px; color:{_BRAND_MUTED}; line-height:1.6; text-align:center;">
        Your new allowance takes effect immediately.  Enjoy!
      </p>
    """
    await _send(to=email, subject=f"You're now on the {plan_label} plan", html=_wrap_html(body))


async def send_credit_low_warning_email(
    email: str,
    name: str,
    percent_used: float,
    credits_remaining: int,
) -> None:
    """Send a credit low-balance warning email."""
    display_name = name or email.split("@")[0]
    body = f"""
      <h1 style="margin:0 0 8px; font-size:22px; font-weight:700; color:{_BRAND_TEXT};">
        ⚠️ Your credits are running low
      </h1>
      <p style="margin:0 0 24px; font-size:14px; color:{_BRAND_MUTED}; line-height:1.7;">
        Hi {display_name}, you've used <strong style="color:{_BRAND_TEXT};">{percent_used:.0f}%</strong>
        of your monthly credits. Only <strong style="color:#F59E0B;">{credits_remaining:,} credits</strong>
        remain in your current billing cycle.
      </p>

      <!-- Progress bar -->
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:28px;">
        <tr>
          <td style="background-color:{_BRAND_BG}; border:1px solid {_BRAND_BORDER};
              border-radius:6px; padding:16px 20px;">
            <p style="margin:0 0 8px; font-size:12px; color:{_BRAND_MUTED};">Usage this cycle</p>
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td width="{min(percent_used, 100):.0f}%" height="8"
                    style="background-color:#F59E0B; border-radius:4px;"></td>
                <td style="background-color:{_BRAND_BORDER}; border-radius:4px;"></td>
              </tr>
            </table>
            <p style="margin:6px 0 0; font-size:12px; color:{_BRAND_MUTED}; text-align:right;">
              {percent_used:.0f}% used</p>
          </td>
        </tr>
      </table>

      {_cta_button("Top up or upgrade →", "https://mohex.org")}

      <p style="margin-top:24px; font-size:13px; color:{_BRAND_MUTED}; line-height:1.6; text-align:center;">
        Upgrade your plan or add top-up credits to keep working without interruption.
      </p>
    """
    await _send(
        to=email,
        subject="Your Aegis credits are running low",
        html=_wrap_html(body),
    )


async def send_custom_email(
    email: str,
    subject: str,
    body_html: str,
    *,
    from_address: str | None = None,
) -> None:
    """Send a custom HTML email (used by the admin broadcast endpoint)."""
    # Wrap plain text body in a simple card if it looks like plain text
    if not body_html.strip().startswith("<"):
        # Convert plain text to HTML paragraphs
        paragraphs = "".join(
            f'<p style="margin:0 0 14px; font-size:14px; color:{_BRAND_TEXT}; line-height:1.7;">'
            f"{line}</p>"
            for line in body_html.strip().split("\n")
            if line.strip()
        )
        body_html = paragraphs
    await _send(to=email, subject=subject, html=_wrap_html(body_html), from_address=from_address)
