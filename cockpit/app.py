"""
Virtual Car Cockpit — FastAPI Application
==========================================

Main server providing:
- REST API endpoints for 7 IVI subsystems
- Static file serving for the cockpit frontend
- Global endpoints: /state, /snapshot/*, /reset, /screenshot
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .state import get_state_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    app = FastAPI(title="Virtual Car Cockpit (IVI Simulator)", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register app routers
    from .apps.navigation import router as nav_router
    from .apps.media import router as media_router
    from .apps.climate import router as climate_router
    from .apps.phone import router as phone_router
    from .apps.messages import router as messages_router
    from .apps.settings import router as settings_router
    from .apps.vehicle import router as vehicle_router
    from .apps.auth import router as auth_router

    for r in [nav_router, media_router, climate_router, phone_router,
              messages_router, settings_router, vehicle_router, auth_router]:
        app.include_router(r)

    # Global endpoints
    _register_global_endpoints(app)

    # Static frontend
    frontend_dir = Path(__file__).parent / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    return app


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SnapshotRequest(BaseModel):
    snapshot_id: str


class SwitchAppRequest(BaseModel):
    app: str


# ---------------------------------------------------------------------------
# Global endpoints
# ---------------------------------------------------------------------------

def _register_global_endpoints(app: FastAPI):

    @app.get("/")
    def index():
        """Serve the cockpit frontend."""
        frontend = Path(__file__).parent / "frontend" / "index.html"
        if frontend.exists():
            return FileResponse(str(frontend))
        return JSONResponse({"error": "Frontend not found"}, status_code=404)

    @app.get("/state")
    def get_full_state():
        """Return the complete cockpit state (used by validators)."""
        sm = get_state_manager()
        return sm.state

    @app.get("/state/{app}")
    def get_app_state(app: str):
        """Return state for a specific subsystem."""
        sm = get_state_manager()
        data = sm.get(app)
        if not data:
            return JSONResponse({"error": f"Unknown app: {app}"}, status_code=404)
        return data

    @app.post("/snapshot/save")
    def save_snapshot(req: SnapshotRequest):
        """Save current state as a named snapshot."""
        sm = get_state_manager()
        ok = sm.save_snapshot(req.snapshot_id)
        return {"status": "ok" if ok else "error", "snapshot_id": req.snapshot_id}

    @app.post("/snapshot/restore")
    def restore_snapshot(req: SnapshotRequest):
        """Restore state from a named snapshot."""
        sm = get_state_manager()
        ok = sm.restore_snapshot(req.snapshot_id)
        if not ok:
            return JSONResponse(
                {"status": "error", "message": f"Snapshot not found: {req.snapshot_id}"},
                status_code=404,
            )
        return {"status": "ok", "snapshot_id": req.snapshot_id}

    @app.post("/snapshot/delete")
    def delete_snapshot(req: SnapshotRequest):
        sm = get_state_manager()
        ok = sm.delete_snapshot(req.snapshot_id)
        return {"status": "ok" if ok else "not_found"}

    @app.get("/snapshot/list")
    def list_snapshots():
        sm = get_state_manager()
        return {"snapshots": sm.list_snapshots()}

    @app.post("/reset")
    def reset_state():
        """Reset cockpit to initial state."""
        sm = get_state_manager()
        sm.reset()
        return {"status": "ok", "message": "Cockpit reset to initial state"}

    @app.post("/switch_app")
    def switch_app(req: SwitchAppRequest):
        """Switch the active app displayed on the cockpit."""
        sm = get_state_manager()
        sm.set_active_app(req.app)
        return {"status": "ok", "active_app": req.app}

    @app.get("/active_app")
    def get_active_app():
        sm = get_state_manager()
        return {"active_app": sm.state.get("active_app", "navigation")}

    @app.get("/action_log")
    def get_action_log():
        sm = get_state_manager()
        return {"log": sm.get_action_log()}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("cockpit.app:app", host="0.0.0.0", port=8420, reload=True)
