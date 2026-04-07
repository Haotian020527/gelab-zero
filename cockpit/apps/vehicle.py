"""Vehicle info app API — drive mode, lights, doors, diagnostics."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..state import get_state_manager

router = APIRouter(prefix="/api/vehicle", tags=["vehicle"])


class SetDriveModeRequest(BaseModel):
    mode: str  # eco, comfort, sport, snow


class SetHeadlightsRequest(BaseModel):
    mode: str  # off, auto, low, high


class SetWindowRequest(BaseModel):
    window: str  # fl, fr, rl, rr
    position: int  # 0=closed, 100=full open


# ---------------------------------------------------------------------------

@router.get("/status")
def get_vehicle_status():
    sm = get_state_manager()
    return sm.get("vehicle")


@router.post("/drive_mode")
def set_drive_mode(req: SetDriveModeRequest):
    sm = get_state_manager()
    sm.update("vehicle", drive_mode=req.mode, current_screen="vehicle_drive_mode")
    sm.set_active_app("vehicle")
    return {"status": "ok", "drive_mode": req.mode}


@router.post("/headlights")
def set_headlights(req: SetHeadlightsRequest):
    sm = get_state_manager()
    sm.update("vehicle", headlights=req.mode, current_screen="vehicle_lights")
    return {"status": "ok", "headlights": req.mode}


@router.post("/lock_doors")
def lock_doors():
    sm = get_state_manager()
    sm.update("vehicle", doors_locked=True, current_screen="vehicle_home")
    return {"status": "ok", "doors_locked": True}


@router.post("/unlock_doors")
def unlock_doors():
    sm = get_state_manager()
    sm.update("vehicle", doors_locked=False, current_screen="vehicle_home")
    return {"status": "ok", "doors_locked": False}


@router.post("/trunk")
def toggle_trunk():
    sm = get_state_manager()
    vehicle = sm.get("vehicle")
    new_state = not vehicle.get("trunk_open", False)
    sm.update("vehicle", trunk_open=new_state)
    return {"status": "ok", "trunk_open": new_state}


@router.post("/window")
def set_window(req: SetWindowRequest):
    sm = get_state_manager()
    vehicle = sm.get("vehicle")
    windows = vehicle.get("windows", {})
    windows[req.window] = max(0, min(100, req.position))
    sm.update("vehicle", windows=windows)
    return {"status": "ok", "window": req.window, "position": windows[req.window]}


@router.get("/diagnostics")
def get_diagnostics():
    sm = get_state_manager()
    v = sm.get("vehicle")
    return {
        "fuel_percent": v.get("fuel_percent"),
        "battery_percent": v.get("battery_percent"),
        "engine_temp_c": v.get("engine_temp_c"),
        "oil_life_percent": v.get("oil_life_percent"),
        "tire_pressure": v.get("tire_pressure"),
        "odometer_km": v.get("odometer_km"),
    }


@router.post("/trip_reset")
def reset_trip():
    sm = get_state_manager()
    sm.update("vehicle", trip_km=0.0)
    return {"status": "ok", "trip_km": 0.0}
