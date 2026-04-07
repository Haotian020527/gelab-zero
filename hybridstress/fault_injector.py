"""
HybridStress Fault Injection Engine
====================================

Wraps gelab-zero's mcp_backend_implements.py to inject controlled
modality-boundary faults at switch points.

Three fault types:
1. Stale Observation — serve cached screenshot instead of fresh one
2. Phantom Acknowledgment — intercept API response, inject false success
3. State Rollback — trigger API-level rollback without GUI refresh
"""

from __future__ import annotations

import logging
import time
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .data_types import FaultConfig, FaultType, FaultSeverity

logger = logging.getLogger(__name__)


class FaultInjector:
    """
    Core fault injection engine. Wraps around gelab-zero's backend to intercept
    and modify behavior at modality switch points.
    """

    def __init__(self):
        self.active_config: Optional[FaultConfig] = None
        self._screenshot_cache: Dict[str, Any] = {}  # timestamp -> screenshot
        self._last_screenshot: Optional[Any] = None
        self._last_screenshot_time: float = 0.0
        self._injection_log: list = []

    def activate(self, config: FaultConfig):
        """Activate fault injection with the given configuration."""
        self.active_config = config
        self._injection_log = []
        logger.info(
            f"Fault injection ACTIVATED: {config.fault_type.value} "
            f"(severity: {config.fault_severity.value})"
        )

    def deactivate(self):
        """Deactivate fault injection."""
        if self.active_config:
            logger.info(f"Fault injection DEACTIVATED. Events logged: {len(self._injection_log)}")
        self.active_config = None

    def is_active(self) -> bool:
        return self.active_config is not None and self.active_config.fault_type != FaultType.NONE

    # =========================================================================
    # Interception Points — called by the instrumented mcp_backend_implements
    # =========================================================================

    def intercept_screenshot(self, fresh_screenshot: Any) -> Any:
        """
        Intercept a screenshot capture. For Stale Observation faults,
        return a cached (stale) screenshot instead of the fresh one.
        """
        # Always cache the fresh screenshot
        now = time.time()
        self._screenshot_cache[now] = fresh_screenshot
        self._last_screenshot = fresh_screenshot
        self._last_screenshot_time = now

        if not self.is_active():
            return fresh_screenshot

        if self.active_config.fault_type == FaultType.STALE_OBSERVATION:
            delay_sec = self.active_config.stale_delay_ms / 1000.0

            # Find the oldest screenshot within the delay window
            stale_time = now - delay_sec
            stale_candidates = [
                (t, s) for t, s in self._screenshot_cache.items()
                if t <= stale_time
            ]

            if stale_candidates:
                # Return the most recent stale screenshot
                _, stale_shot = max(stale_candidates, key=lambda x: x[0])
                self._injection_log.append({
                    "type": "stale_observation",
                    "time": now,
                    "stale_age_ms": int((now - max(t for t, _ in stale_candidates)) * 1000),
                })
                logger.debug(f"Injected STALE OBSERVATION (age: {delay_sec*1000:.0f}ms)")
                return stale_shot

        return fresh_screenshot

    def intercept_api_response(self, actual_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Intercept an API response. For Phantom Ack faults,
        inject a false success response before the app actually completes.
        """
        if not self.is_active():
            return actual_response

        if self.active_config.fault_type == FaultType.PHANTOM_ACK and self.active_config.ack_intercept:
            # Create a fake success response
            fake_response = deepcopy(actual_response)
            fake_response["status"] = "success"
            fake_response["completed"] = True
            if "error" in fake_response:
                del fake_response["error"]

            self._injection_log.append({
                "type": "phantom_ack",
                "time": time.time(),
                "original_status": actual_response.get("status", "unknown"),
            })
            logger.debug(
                f"Injected PHANTOM ACK "
                f"(original: {actual_response.get('status', 'unknown')} → success)"
            )
            return fake_response

        return actual_response

    def intercept_action_completion(
        self,
        action: str,
        post_action_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Intercept action completion. For State Rollback faults,
        trigger a rollback after the action appears to complete.
        """
        if not self.is_active():
            return True

        if self.active_config.fault_type == FaultType.STATE_ROLLBACK:
            delay_ms = self.active_config.rollback_after_ms

            def _delayed_rollback():
                time.sleep(delay_ms / 1000.0)
                if post_action_callback:
                    post_action_callback()  # This would trigger the rollback
                self._injection_log.append({
                    "type": "state_rollback",
                    "time": time.time(),
                    "delay_ms": delay_ms,
                    "action": action,
                })
                logger.debug(f"Injected STATE ROLLBACK after {delay_ms}ms for: {action}")

            # Start rollback in background thread
            thread = threading.Thread(target=_delayed_rollback, daemon=True)
            thread.start()

        return True

    def get_injection_log(self) -> list:
        """Return the log of all fault injections during this session."""
        return deepcopy(self._injection_log)

    def clear_cache(self):
        """Clear screenshot cache (call between tasks)."""
        self._screenshot_cache.clear()
        self._last_screenshot = None
        self._last_screenshot_time = 0.0


class InstrumentedBackend:
    """
    Wrapper around gelab-zero's mcp_backend_implements that adds
    fault injection interception at key points.

    This is a proxy pattern — it wraps the real backend and intercepts
    screenshot captures and API responses.
    """

    def __init__(self, real_backend: Any, injector: FaultInjector):
        self.real_backend = real_backend
        self.injector = injector
        self._switch_events_log: list = []

    def take_screenshot(self, *args, **kwargs) -> Any:
        """Intercepted screenshot capture."""
        fresh = self.real_backend.take_screenshot(*args, **kwargs)
        return self.injector.intercept_screenshot(fresh)

    def execute_api_action(self, action: str, *args, **kwargs) -> Dict[str, Any]:
        """Intercepted API action execution."""
        response = self.real_backend.execute_api_action(action, *args, **kwargs)
        return self.injector.intercept_api_response(response)

    def is_modality_switch(self, prev_mode: str, curr_mode: str) -> bool:
        """Detect when a modality switch occurs."""
        return prev_mode != curr_mode and prev_mode in ("api", "gui") and curr_mode in ("api", "gui")

    def log_switch_event(self, event_data: dict):
        """Record a modality switch event for later analysis."""
        self._switch_events_log.append(event_data)

    def __getattr__(self, name: str):
        """Proxy all other methods to the real backend."""
        return getattr(self.real_backend, name)
