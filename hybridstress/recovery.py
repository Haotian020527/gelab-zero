"""
CMV-Triggered Recovery Protocol
=================================

Fixed recovery protocol when CMV detects inconsistency:
1. Re-capture screenshot (resolves transient timing issues)
2. If still inconsistent: retry action via GUI
3. If still inconsistent: escalate to GUI-only fallback

This implements the recovery evaluation for Block 5 (C3, exploratory).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from .data_types import Predicate
from .validators import CompositeValidator

logger = logging.getLogger(__name__)


class RecoveryProtocol:
    """
    Fixed recovery protocol triggered by CMV inconsistency detection.

    Steps:
    1. Re-screenshot: captures fresh screenshot and re-evaluates
    2. GUI-retry: re-executes the action via GUI-only path
    3. GUI-fallback: switches entirely to GUI-only mode for remaining steps
    """

    def __init__(
        self,
        validator: CompositeValidator,
        cmv_threshold: float = 0.5,
        max_retries: int = 2,
    ):
        self.validator = validator
        self.cmv_threshold = cmv_threshold
        self.max_retries = max_retries
        self.recovery_log: list = []

    def attempt_recovery(
        self,
        cmv_score: float,
        postconditions: list,
        action: str,
        device_id: str,
        executor: Any = None,
    ) -> Dict[str, Any]:
        """
        Attempt recovery if CMV detects inconsistency.

        Returns dict with recovery outcome and actions taken.
        """
        if cmv_score < self.cmv_threshold:
            return {
                "recovery_triggered": False,
                "cmv_score": cmv_score,
                "outcome": "consistent",
            }

        logger.info(f"Recovery triggered: CMV score={cmv_score:.3f} > {self.cmv_threshold}")

        result = {
            "recovery_triggered": True,
            "cmv_score": cmv_score,
            "steps": [],
        }

        # Step 1: Re-screenshot
        step1 = self._step_rescreenshot(postconditions, device_id)
        result["steps"].append(step1)
        if step1["resolved"]:
            result["outcome"] = "resolved_by_rescreenshot"
            self.recovery_log.append(result)
            return result

        # Step 2: Retry via GUI
        step2 = self._step_gui_retry(action, postconditions, device_id, executor)
        result["steps"].append(step2)
        if step2["resolved"]:
            result["outcome"] = "resolved_by_gui_retry"
            self.recovery_log.append(result)
            return result

        # Step 3: GUI-only fallback
        step3 = self._step_gui_fallback(action, postconditions, device_id, executor)
        result["steps"].append(step3)
        result["outcome"] = "gui_fallback" if step3["resolved"] else "unresolved"

        self.recovery_log.append(result)
        return result

    def _step_rescreenshot(
        self,
        postconditions: list,
        device_id: str,
    ) -> Dict[str, Any]:
        """Step 1: Re-capture screenshot and re-validate."""
        from .gelab_integration import capture_screenshot_adb
        import tempfile
        import os

        start = time.time()

        # Wait briefly for state to settle
        time.sleep(0.5)

        # Capture fresh screenshot
        tmp_path = os.path.join(tempfile.gettempdir(), f"recovery_{int(time.time())}.png")
        capture_screenshot_adb(tmp_path, device_id)
        self.validator.set_screenshot(tmp_path)

        # Re-validate
        outcome, details = self.validator.validate_all(postconditions)
        resolved = outcome.value == "success"

        return {
            "step": "rescreenshot",
            "resolved": resolved,
            "duration_ms": int((time.time() - start) * 1000),
        }

    def _step_gui_retry(
        self,
        action: str,
        postconditions: list,
        device_id: str,
        executor: Any,
    ) -> Dict[str, Any]:
        """Step 2: Retry the action via GUI-only path."""
        start = time.time()

        if executor is None:
            return {
                "step": "gui_retry",
                "resolved": False,
                "duration_ms": 0,
                "error": "No executor provided",
            }

        try:
            executor.execute_task_gui_only(action, max_steps=5)
            time.sleep(1)

            # Re-validate
            outcome, details = self.validator.validate_all(postconditions)
            resolved = outcome.value == "success"
        except Exception as e:
            logger.warning(f"GUI retry failed: {e}")
            resolved = False

        return {
            "step": "gui_retry",
            "resolved": resolved,
            "duration_ms": int((time.time() - start) * 1000),
        }

    def _step_gui_fallback(
        self,
        action: str,
        postconditions: list,
        device_id: str,
        executor: Any,
    ) -> Dict[str, Any]:
        """Step 3: Full GUI-only fallback with extended steps."""
        start = time.time()

        if executor is None:
            return {
                "step": "gui_fallback",
                "resolved": False,
                "duration_ms": 0,
                "error": "No executor provided",
            }

        try:
            executor.execute_task_gui_only(action, max_steps=15)
            time.sleep(2)

            outcome, details = self.validator.validate_all(postconditions)
            resolved = outcome.value == "success"
        except Exception as e:
            logger.warning(f"GUI fallback failed: {e}")
            resolved = False

        return {
            "step": "gui_fallback",
            "resolved": resolved,
            "duration_ms": int((time.time() - start) * 1000),
        }

    def get_latency_overhead_ms(self) -> int:
        """Total latency overhead from all recovery attempts."""
        total = 0
        for entry in self.recovery_log:
            for step in entry.get("steps", []):
                total += step.get("duration_ms", 0)
        return total

    def get_stats(self) -> Dict:
        """Summary statistics of recovery attempts."""
        n = len(self.recovery_log)
        if n == 0:
            return {"total_attempts": 0}

        resolved_counts = {
            "resolved_by_rescreenshot": 0,
            "resolved_by_gui_retry": 0,
            "gui_fallback": 0,
            "unresolved": 0,
        }
        for entry in self.recovery_log:
            outcome = entry.get("outcome", "unresolved")
            if outcome in resolved_counts:
                resolved_counts[outcome] += 1

        return {
            "total_attempts": n,
            "outcomes": resolved_counts,
            "total_latency_ms": self.get_latency_overhead_ms(),
            "avg_latency_ms": self.get_latency_overhead_ms() // max(n, 1),
        }
