"""
Cockpit State Manager
======================

Central in-memory state for the virtual IVI system.
Supports deterministic save/restore for counterfactual replay.
"""

from __future__ import annotations

import copy
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initial cockpit state — all 7 subsystems
# ---------------------------------------------------------------------------

INITIAL_STATE: Dict[str, Any] = {
    "navigation": {
        "active": False,
        "destination": "",
        "destination_address": "",
        "current_location": "公司停车场",
        "route_distance_km": 0.0,
        "route_eta_min": 0,
        "is_navigating": False,
        "recent_destinations": [
            {"name": "家", "address": "北京市朝阳区建国路88号"},
            {"name": "公司", "address": "北京市海淀区中关村大街1号"},
            {"name": "机场", "address": "北京首都国际机场T3航站楼"},
        ],
        "current_screen": "navigation_home",
    },
    "media": {
        "source": "bluetooth",      # bluetooth, usb, radio, online
        "playing": False,
        "current_track": "未播放",
        "artist": "",
        "album": "",
        "progress_sec": 0,
        "duration_sec": 0,
        "volume": 50,               # 0-100
        "playlist": [
            {"title": "夜曲", "artist": "周杰伦", "duration": 225},
            {"title": "晴天", "artist": "周杰伦", "duration": 269},
            {"title": "稻香", "artist": "周杰伦", "duration": 223},
            {"title": "七里香", "artist": "周杰伦", "duration": 296},
            {"title": "青花瓷", "artist": "周杰伦", "duration": 239},
        ],
        "playlist_index": -1,
        "radio_frequency": 99.6,
        "current_screen": "media_home",
    },
    "climate": {
        "ac_on": True,
        "temperature_driver": 24.0,  # Celsius
        "temperature_passenger": 24.0,
        "fan_speed": 3,              # 0-7
        "mode": "auto",              # auto, face, feet, face_feet, defrost
        "air_circulation": "external",  # external, internal
        "seat_heating_driver": 0,    # 0=off, 1=low, 2=mid, 3=high
        "seat_heating_passenger": 0,
        "rear_defrost": False,
        "current_screen": "climate_home",
    },
    "phone": {
        "connected": True,
        "paired_device": "iPhone 15 Pro",
        "bluetooth_on": True,
        "in_call": False,
        "call_number": "",
        "call_contact": "",
        "call_duration_sec": 0,
        "call_log": [
            {"name": "张三", "number": "13800138001", "type": "incoming", "time": "10:30"},
            {"name": "李四", "number": "13800138002", "type": "outgoing", "time": "09:15"},
            {"name": "王五", "number": "13800138003", "type": "missed", "time": "昨天"},
        ],
        "contacts": [
            {"name": "张三", "number": "13800138001"},
            {"name": "李四", "number": "13800138002"},
            {"name": "王五", "number": "13800138003"},
            {"name": "TestUser", "number": "13800138000"},
        ],
        "current_screen": "phone_home",
    },
    "messages": {
        "conversations": [
            {
                "contact": "张三",
                "last_message": "明天开会时间改了",
                "time": "10:35",
                "unread": True,
                "messages": [
                    {"from": "张三", "text": "明天开会时间改了", "time": "10:35"},
                    {"from": "me", "text": "好的，收到", "time": "10:36"},
                ],
            },
            {
                "contact": "李四",
                "last_message": "到了告诉我一声",
                "time": "09:20",
                "unread": False,
                "messages": [
                    {"from": "李四", "text": "到了告诉我一声", "time": "09:20"},
                ],
            },
            {
                "contact": "Test",
                "last_message": "HybridStress测试消息",
                "time": "08:00",
                "unread": True,
                "messages": [
                    {"from": "me", "text": "HybridStress测试消息", "time": "08:00"},
                ],
            },
        ],
        "current_screen": "messages_home",
    },
    "settings": {
        "brightness": 70,            # 0-100
        "theme": "dark",             # dark, light
        "language": "zh-CN",
        "wifi_on": True,
        "wifi_ssid": "CarWiFi-5G",
        "bluetooth_on": True,
        "bluetooth_name": "MyCarIVI",
        "sound_volume": 60,          # 0-100
        "notification_sound": True,
        "auto_lock": True,
        "speed_lock": True,          # Lock touchscreen above speed threshold
        "display_mode": "standard",  # standard, night, vivid
        "current_screen": "settings_home",
    },
    "vehicle": {
        "speed_kmh": 0,
        "rpm": 800,
        "fuel_percent": 72,
        "battery_percent": 85,       # For hybrid/EV
        "odometer_km": 15234,
        "trip_km": 45.2,
        "tire_pressure": {"fl": 2.3, "fr": 2.3, "rl": 2.2, "rr": 2.2},
        "drive_mode": "comfort",     # eco, comfort, sport, snow
        "headlights": "auto",        # off, auto, low, high
        "doors_locked": True,
        "trunk_open": False,
        "windows": {"fl": 0, "fr": 0, "rl": 0, "rr": 0},  # 0=closed, 100=full open
        "engine_temp_c": 90,
        "oil_life_percent": 68,
        "current_screen": "vehicle_home",
    },
    # Global UI state
    "active_app": "navigation",
    "status_bar": {
        "time": "14:30",
        "signal_strength": 4,        # 0-5
        "wifi_connected": True,
        "bluetooth_connected": True,
        "temperature_outside": 26,
    },
}


# ---------------------------------------------------------------------------
# State Manager
# ---------------------------------------------------------------------------

class CockpitStateManager:
    """
    Thread-safe, in-memory state manager for the virtual cockpit.
    Supports deterministic save/restore for counterfactual replay.
    """

    def __init__(self):
        self._state: Dict[str, Any] = copy.deepcopy(INITIAL_STATE)
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._action_log: list = []

    # ── Read ───────────────────────────────────────────────────────────────

    @property
    def state(self) -> Dict[str, Any]:
        return self._state

    def get(self, app: str) -> Dict[str, Any]:
        """Get state for a specific app subsystem."""
        return self._state.get(app, {})

    def get_nested(self, *keys: str) -> Any:
        """Get a deeply nested value. E.g., get_nested('climate', 'temperature_driver')"""
        obj = self._state
        for k in keys:
            if isinstance(obj, dict):
                obj = obj.get(k)
            else:
                return None
        return obj

    # ── Write ──────────────────────────────────────────────────────────────

    def update(self, app: str, **kwargs) -> Dict[str, Any]:
        """Update fields of an app subsystem. Returns the updated subsystem state."""
        if app not in self._state:
            self._state[app] = {}
        for k, v in kwargs.items():
            self._state[app][k] = v
        self._action_log.append({
            "time": time.time(),
            "app": app,
            "updates": kwargs,
        })
        return self._state[app]

    def set_active_app(self, app: str):
        """Switch the active app (visible on cockpit display)."""
        self._state["active_app"] = app

    # ── Snapshot save/restore (replaces emulator snapshots) ────────────────

    def save_snapshot(self, snapshot_id: str) -> bool:
        """Save a deep copy of the current state."""
        self._snapshots[snapshot_id] = copy.deepcopy(self._state)
        logger.info(f"Snapshot saved: {snapshot_id} ({len(self._snapshots)} total)")
        return True

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore state from a saved snapshot."""
        if snapshot_id not in self._snapshots:
            logger.warning(f"Snapshot not found: {snapshot_id}")
            return False
        self._state = copy.deepcopy(self._snapshots[snapshot_id])
        logger.info(f"Snapshot restored: {snapshot_id}")
        return True

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a saved snapshot."""
        if snapshot_id in self._snapshots:
            del self._snapshots[snapshot_id]
            return True
        return False

    def list_snapshots(self) -> list:
        """List all saved snapshot IDs."""
        return list(self._snapshots.keys())

    # ── Reset ──────────────────────────────────────────────────────────────

    def reset(self):
        """Reset state to initial values."""
        self._state = copy.deepcopy(INITIAL_STATE)
        self._action_log.clear()
        logger.info("Cockpit state reset to initial values")

    # ── Serialization ─────────────────────────────────────────────────────

    def to_json(self) -> str:
        return json.dumps(self._state, ensure_ascii=False, indent=2)

    def save_to_file(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    def get_action_log(self) -> list:
        return list(self._action_log)


# Singleton instance
_manager: Optional[CockpitStateManager] = None


def get_state_manager() -> CockpitStateManager:
    """Get or create the global state manager singleton."""
    global _manager
    if _manager is None:
        _manager = CockpitStateManager()
    return _manager


def reset_state_manager():
    """Reset the global singleton."""
    global _manager
    _manager = CockpitStateManager()
