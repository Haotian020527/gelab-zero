"""Navigation app API — route planning, destination search, turn-by-turn."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from ..state import get_state_manager

router = APIRouter(prefix="/api/navigation", tags=["navigation"])


class SetDestinationRequest(BaseModel):
    name: str
    address: str = ""


class RouteInfo(BaseModel):
    distance_km: float = 0.0
    eta_min: int = 0


# ---------------------------------------------------------------------------

@router.get("/status")
def get_navigation_status():
    sm = get_state_manager()
    return sm.get("navigation")


@router.post("/set_destination")
def set_destination(req: SetDestinationRequest):
    sm = get_state_manager()
    # Simulate route calculation
    import random
    dist = round(random.uniform(5, 80), 1)
    eta = int(dist * 1.5)

    sm.update("navigation",
              destination=req.name,
              destination_address=req.address or f"{req.name}路100号",
              route_distance_km=dist,
              route_eta_min=eta,
              active=True,
              current_screen="navigation_route_preview")

    # Add to recent destinations
    nav = sm.get("navigation")
    recents = nav.get("recent_destinations", [])
    new_entry = {"name": req.name, "address": req.address}
    recents = [r for r in recents if r["name"] != req.name]
    recents.insert(0, new_entry)
    sm.update("navigation", recent_destinations=recents[:10])

    return {"status": "ok", "destination": req.name, "distance_km": dist, "eta_min": eta}


@router.post("/start")
def start_navigation():
    sm = get_state_manager()
    nav = sm.get("navigation")
    if not nav.get("destination"):
        return {"status": "error", "message": "请先设置目的地"}
    sm.update("navigation", is_navigating=True, current_screen="navigation_active")
    sm.set_active_app("navigation")
    return {"status": "ok", "message": f"开始导航到 {nav['destination']}"}


@router.post("/stop")
def stop_navigation():
    sm = get_state_manager()
    sm.update("navigation",
              is_navigating=False,
              destination="",
              destination_address="",
              route_distance_km=0.0,
              route_eta_min=0,
              active=False,
              current_screen="navigation_home")
    return {"status": "ok", "message": "导航已停止"}


@router.get("/recent")
def get_recent_destinations():
    sm = get_state_manager()
    return sm.get("navigation").get("recent_destinations", [])
