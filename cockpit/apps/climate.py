"""Climate control app API — AC, temperature, fan, seat heating."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..state import get_state_manager

router = APIRouter(prefix="/api/climate", tags=["climate"])


class SetTemperatureRequest(BaseModel):
    zone: str = "driver"  # driver, passenger, both
    temperature: float


class SetFanSpeedRequest(BaseModel):
    speed: int  # 0-7


class SetModeRequest(BaseModel):
    mode: str  # auto, face, feet, face_feet, defrost


class SetSeatHeatingRequest(BaseModel):
    zone: str = "driver"  # driver, passenger
    level: int  # 0=off, 1=low, 2=mid, 3=high


# ---------------------------------------------------------------------------

@router.get("/status")
def get_climate_status():
    sm = get_state_manager()
    return sm.get("climate")


@router.post("/toggle_ac")
def toggle_ac():
    sm = get_state_manager()
    climate = sm.get("climate")
    new_state = not climate.get("ac_on", False)
    sm.update("climate", ac_on=new_state, current_screen="climate_home")
    sm.set_active_app("climate")
    return {"status": "ok", "ac_on": new_state}


@router.post("/temperature")
def set_temperature(req: SetTemperatureRequest):
    sm = get_state_manager()
    temp = max(16.0, min(32.0, req.temperature))
    updates = {"current_screen": "climate_home"}
    if req.zone in ("driver", "both"):
        updates["temperature_driver"] = temp
    if req.zone in ("passenger", "both"):
        updates["temperature_passenger"] = temp
    sm.update("climate", **updates)
    return {"status": "ok", "zone": req.zone, "temperature": temp}


@router.post("/fan_speed")
def set_fan_speed(req: SetFanSpeedRequest):
    sm = get_state_manager()
    speed = max(0, min(7, req.speed))
    sm.update("climate", fan_speed=speed, current_screen="climate_home")
    return {"status": "ok", "fan_speed": speed}


@router.post("/mode")
def set_mode(req: SetModeRequest):
    sm = get_state_manager()
    sm.update("climate", mode=req.mode, current_screen="climate_home")
    return {"status": "ok", "mode": req.mode}


@router.post("/seat_heating")
def set_seat_heating(req: SetSeatHeatingRequest):
    sm = get_state_manager()
    level = max(0, min(3, req.level))
    key = f"seat_heating_{req.zone}"
    sm.update("climate", **{key: level, "current_screen": "climate_home"})
    return {"status": "ok", "zone": req.zone, "level": level}


@router.post("/circulation")
def toggle_circulation():
    sm = get_state_manager()
    climate = sm.get("climate")
    current = climate.get("air_circulation", "external")
    new = "internal" if current == "external" else "external"
    sm.update("climate", air_circulation=new)
    return {"status": "ok", "air_circulation": new}


@router.post("/rear_defrost")
def toggle_rear_defrost():
    sm = get_state_manager()
    climate = sm.get("climate")
    new_state = not climate.get("rear_defrost", False)
    sm.update("climate", rear_defrost=new_state)
    return {"status": "ok", "rear_defrost": new_state}
