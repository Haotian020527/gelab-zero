"""
Virtual Car Cockpit (IVI Simulator)
====================================

Web-based In-Vehicle Infotainment simulator that replaces the physical
Android device for the HybridStress benchmark. Provides:

1. FastAPI REST endpoints for API-only execution
2. HTML/CSS/JS GUI for GUI-only execution (via Playwright screenshots)
3. Deterministic state management with save/restore (replaces emulator snapshots)
4. Cockpit-specific validators (replaces ADB validators)

Architecture:
    cockpit/
    ├── state.py           — Central state manager with snapshot support
    ├── app.py             — FastAPI application + global endpoints
    ├── apps/              — 7 IVI app API routers
    │   ├── navigation.py
    │   ├── media.py
    │   ├── climate.py
    │   ├── phone.py
    │   ├── messages.py
    │   ├── settings.py
    │   └── vehicle.py
    ├── frontend/          — HTML/CSS/JS cockpit UI (1280×720)
    │   └── index.html
    ├── screenshot.py      — Playwright screenshot service
    ├── validators.py      — CockpitAPIValidator + CockpitScreenshotValidator
    ├── task_definitions.py — 20 IVI-domain benchmark tasks
    └── integration.py     — CockpitExecutor + CockpitReplayEngine
"""

__version__ = "0.1.0"
