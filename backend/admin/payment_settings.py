"""Admin payment settings — toggle which payment methods are active."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.admin.dependencies import get_admin_user

router = APIRouter()

SETTINGS_FILE = Path("/work/repos/aegis-env-fix/payment_settings.json")

DEFAULT_SETTINGS = {
    "stripe": True,
    "coinbase": True,
}

METHOD_META = {
    "stripe": {
        "id": "stripe",
        "name": "Stripe",
        "description": "Accept credit and debit card payments via Stripe Checkout.",
    },
    "coinbase": {
        "id": "coinbase",
        "name": "Coinbase Commerce",
        "description": "Accept cryptocurrency payments via Coinbase Commerce.",
    },
}


def _load() -> dict[str, bool]:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            return {**DEFAULT_SETTINGS, **data}
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def _save(settings: dict[str, bool]) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))


@router.get("/payment-settings")
async def get_payment_settings(_admin=Depends(get_admin_user)) -> dict:
    current = _load()
    methods = [
        {**METHOD_META[key], "enabled": current.get(key, True)}
        for key in ("stripe", "coinbase")
    ]
    return {"methods": methods}


class PatchPaymentSettingsBody(BaseModel):
    methods: dict[str, Optional[bool]]


@router.patch("/payment-settings")
async def patch_payment_settings(body: PatchPaymentSettingsBody, _admin=Depends(get_admin_user)) -> dict:
    current = _load()
    for key, val in body.methods.items():
        if key in ("stripe", "coinbase") and val is not None:
            current[key] = bool(val)
    _save(current)
    return {"ok": True, "methods": current}
