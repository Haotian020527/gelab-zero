"""Settings app API — brightness, connectivity, display preferences."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..state import get_state_manager

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SetBrightnessRequest(BaseModel):
    brightness: int  # 0-100


class SetVolumeRequest(BaseModel):
    volume: int  # 0-100


class SetLanguageRequest(BaseModel):
    language: str  # zh-CN, en-US, etc.


class SetDisplayModeRequest(BaseModel):
    mode: str  # standard, night, vivid


# ---------------------------------------------------------------------------

@router.get("/status")
def get_settings_status():
    sm = get_state_manager()
    return sm.get("settings")


@router.post("/brightness")
def set_brightness(req: SetBrightnessRequest):
    sm = get_state_manager()
    b = max(0, min(100, req.brightness))
    sm.update("settings", brightness=b, current_screen="settings_display")
    sm.set_active_app("settings")
    return {"status": "ok", "brightness": b}


@router.post("/volume")
def set_volume(req: SetVolumeRequest):
    sm = get_state_manager()
    v = max(0, min(100, req.volume))
    sm.update("settings", sound_volume=v, current_screen="settings_sound")
    return {"status": "ok", "sound_volume": v}


@router.post("/toggle_wifi")
def toggle_wifi():
    sm = get_state_manager()
    settings = sm.get("settings")
    new_state = not settings.get("wifi_on", False)
    sm.update("settings", wifi_on=new_state, current_screen="settings_wifi")

    # Update status bar
    status_bar = sm.get("status_bar")
    status_bar["wifi_connected"] = new_state
    sm.update("status_bar", **status_bar)

    return {"status": "ok", "wifi_on": new_state, "wifi_status": "enabled" if new_state else "disabled"}


@router.post("/toggle_bluetooth")
def toggle_bluetooth():
    sm = get_state_manager()
    settings = sm.get("settings")
    new_state = not settings.get("bluetooth_on", False)
    sm.update("settings", bluetooth_on=new_state,
              bluetooth_status="enabled" if new_state else "disabled",
              current_screen="settings_bluetooth")

    # Update status bar
    status_bar = sm.get("status_bar")
    status_bar["bluetooth_connected"] = new_state
    sm.update("status_bar", **status_bar)

    # Also update phone bluetooth state
    sm.update("phone", bluetooth_on=new_state)

    return {"status": "ok", "bluetooth_on": new_state,
            "bluetooth_status": "enabled" if new_state else "disabled"}


@router.post("/language")
def set_language(req: SetLanguageRequest):
    sm = get_state_manager()
    sm.update("settings", language=req.language, current_screen="settings_language")
    return {"status": "ok", "language": req.language}


@router.post("/display_mode")
def set_display_mode(req: SetDisplayModeRequest):
    sm = get_state_manager()
    sm.update("settings", display_mode=req.mode, current_screen="settings_display")
    return {"status": "ok", "display_mode": req.mode}


@router.post("/toggle_notification")
def toggle_notification():
    sm = get_state_manager()
    settings = sm.get("settings")
    new_state = not settings.get("notification_sound", True)
    sm.update("settings", notification_sound=new_state)
    return {"status": "ok", "notification_sound": new_state}
