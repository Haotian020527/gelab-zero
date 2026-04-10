"""Authentication API for deterministic cockpit safety flows."""

from __future__ import annotations

import time

from fastapi import APIRouter

from ..state import get_state_manager

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def get_auth_status():
    sm = get_state_manager()
    return sm.get("auth")


@router.post("/biometric_verify")
def biometric_verify():
    sm = get_state_manager()
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    sm.update(
        "auth",
        biometric_verified=True,
        last_verified_at=ts,
        two_factor_method="biometric",
    )
    return {"status": "ok", "biometric_verified": True, "last_verified_at": ts}


@router.post("/reset")
def reset_auth():
    sm = get_state_manager()
    sm.update(
        "auth",
        biometric_verified=False,
        last_verified_at="",
        two_factor_method="biometric",
    )
    return {"status": "ok", "biometric_verified": False}
