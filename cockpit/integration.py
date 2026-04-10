"""
Cockpit ↔ HybridStress Integration Layer
==========================================

Bridges the virtual cockpit with HybridStress benchmark infrastructure.
Replaces gelab_integration.py's GelabExecutor and ReplayEngine.

Key differences from GelabExecutor:
- No ADB / physical device — uses HTTP API to cockpit server
- Snapshots are in-memory state save/restore (via /snapshot/* endpoints)
- Screenshots via Playwright instead of ADB screencap
- Task execution via REST API (API-only) or Playwright clicks (GUI-only)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from hybridstress.data_types import (
    BranchOutcome, BranchResult, FaultConfig, FaultType, FaultSeverity,
    Predicate, SwitchEvent, SwitchLabel,
)
from hybridstress.fault_injector import FaultInjector

from .screenshot import capture_screenshot_cockpit, get_screenshotter, stop_screenshotter
from .validators import CockpitCompositeValidator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cockpit server interaction
# ---------------------------------------------------------------------------

class CockpitClient:
    """HTTP client for the cockpit server."""

    def __init__(self, base_url: str = "http://localhost:8420"):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.trust_env = False

    def get(self, path: str) -> Dict:
        resp = self._session.get(f"{self.base_url}{path}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, body: Optional[Dict] = None) -> Dict:
        resp = self._session.post(f"{self.base_url}{path}", json=body or {}, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_state(self) -> Dict:
        return self.get("/state")

    def save_snapshot(self, snapshot_id: str) -> bool:
        result = self.post("/snapshot/save", {"snapshot_id": snapshot_id})
        return result.get("status") == "ok"

    def restore_snapshot(self, snapshot_id: str) -> bool:
        try:
            result = self.post("/snapshot/restore", {"snapshot_id": snapshot_id})
            return result.get("status") == "ok"
        except requests.HTTPError:
            return False

    def reset(self):
        self.post("/reset")

    def switch_app(self, app: str):
        self.post("/switch_app", {"app": app})

    def is_alive(self) -> bool:
        try:
            self.get("/state")
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Cockpit Executor (replaces GelabExecutor)
# ---------------------------------------------------------------------------

class CockpitExecutor:
    """
    Executes tasks against the virtual cockpit in 3 modes:
    - hybrid: API-first with GUI verification
    - api_only: only REST API calls
    - gui_only: only Playwright GUI interactions
    """

    def __init__(
        self,
        cockpit_url: str = "http://localhost:8420",
        injector: Optional[FaultInjector] = None,
    ):
        self.client = CockpitClient(cockpit_url)
        self.cockpit_url = cockpit_url
        self.injector = injector or FaultInjector()

    def execute_task_hybrid(
        self,
        task: Dict,
        fault_config: Optional[FaultConfig] = None,
    ) -> Dict[str, Any]:
        """
        Hybrid mode: Execute via API, then verify via GUI screenshot.
        Fault injection intercepts API responses when active.
        """
        stale_screenshot = None
        if fault_config and fault_config.fault_type == FaultType.STALE_OBSERVATION:
            # Capture a STALE screenshot BEFORE the action executes,
            # so the post-action screenshot will be outdated.
            import tempfile, os
            stale_path = os.path.join(tempfile.gettempdir(), f"stale_{id(self)}.png")
            from .screenshot import capture_screenshot_cockpit
            capture_screenshot_cockpit(stale_path, self.cockpit_url)
            stale_screenshot = stale_path

        if fault_config:
            self.injector.activate(fault_config)

        # Step 1: API execution
        api_result = self._execute_api(task)

        # Step 2: Inject faults if configured
        if fault_config and self.injector.is_active():
            api_result = self._apply_fault(api_result, fault_config)

        if fault_config:
            self.injector.deactivate()

        result = {
            "status": api_result.get("status", "success"),
            "mode": "hybrid",
            "api_result": api_result,
        }
        if stale_screenshot:
            result["stale_screenshot"] = stale_screenshot

        return result

    def execute_task_api_only(self, task: Dict) -> Dict[str, Any]:
        """API-only mode: Execute task through REST endpoints only."""
        result = self._execute_api(task)
        return {
            "status": result.get("status", "success"),
            "mode": "api_only",
            "api_result": result,
        }

    def execute_task_gui_only(self, task: Dict) -> Dict[str, Any]:
        """GUI-only mode: Execute task through Playwright browser interactions."""
        result = self._execute_gui(task)
        return {
            "status": "success" if result else "error",
            "mode": "gui_only",
            "gui_result": result,
        }

    # ── Internal execution methods ─────────────────────────────────────

    def _execute_api(self, task: Dict) -> Dict:
        """Execute task's API action sequence."""
        api_actions = task.get("api_actions", [])
        results = []

        for action in api_actions:
            method = action.get("method", "POST").upper()
            path = action["path"]
            body = action.get("body", {})

            try:
                if method == "GET":
                    resp = self.client.get(path)
                else:
                    resp = self.client.post(path, body)
                results.append({"path": path, "response": resp, "status": "ok"})
            except Exception as e:
                logger.error(f"API action failed: {path}: {e}")
                results.append({"path": path, "error": str(e), "status": "error"})
                return {"status": "error", "results": results, "error": str(e)}

        return {"status": "success", "results": results}

    def _execute_gui(self, task: Dict) -> Dict:
        """
        Execute task via Playwright GUI interactions.
        Navigates to the correct app and performs clicks/inputs.
        """
        try:
            screenshotter = get_screenshotter(self.cockpit_url)
            page = screenshotter._page

            # Switch to the task's app via GUI nav click
            app = task.get("app", "navigation")
            page.click(f'[data-app="{app}"]', timeout=3000)
            time.sleep(0.5)

            # For GUI-only mode, we interact with the UI elements
            # Map API actions to GUI interactions
            api_actions = task.get("api_actions", [])
            for action in api_actions:
                path = action["path"]
                body = action.get("body", {})

                # Extract the action name from the path
                parts = path.strip("/").split("/")
                if len(parts) >= 3:
                    action_name = parts[-1]
                else:
                    continue

                # Try to click a button matching the action
                selectors = [
                    f'[data-action="{action_name}"]',
                    f'button:has-text("{action_name}")',
                ]

                clicked = False
                for sel in selectors:
                    try:
                        page.click(sel, timeout=2000)
                        clicked = True
                        time.sleep(0.3)
                        break
                    except Exception:
                        continue

                # If button click didn't work, fill input fields from body
                if not clicked and body:
                    for key, value in body.items():
                        try:
                            page.fill(f'[data-field="{key}"]', str(value), timeout=2000)
                        except Exception:
                            pass
                    # Try submit
                    try:
                        page.click('[data-action="submit"], button[type="submit"]', timeout=2000)
                    except Exception:
                        pass

                time.sleep(0.3)

            return {"status": "success"}

        except Exception as e:
            logger.error(f"GUI execution failed: {e}")
            return {"status": "error", "error": str(e)}

    def _apply_fault(self, api_result: Dict, fault_config: FaultConfig) -> Dict:
        """Apply fault injection to API results."""
        ft = fault_config.fault_type

        if ft == FaultType.STALE_OBSERVATION:
            # Delay: the API succeeds but the GUI screenshot is stale
            delay_s = fault_config.stale_delay_ms / 1000.0
            time.sleep(delay_s)

        elif ft == FaultType.PHANTOM_ACK:
            # API reports success but state didn't actually change
            # Simulate by reverting the last state change
            if fault_config.ack_intercept:
                logger.info("Phantom ack: API reports success but reverting state")
                # The API already modified state — to simulate phantom ack,
                # we need to restore a pre-action snapshot if available
                try:
                    self.client.restore_snapshot("_pre_action")
                except Exception:
                    pass

        elif ft == FaultType.STATE_ROLLBACK:
            # State partially reverts after delay
            delay_s = fault_config.rollback_after_ms / 1000.0
            time.sleep(delay_s)
            # Partial rollback: restore to pre-action state
            try:
                self.client.restore_snapshot("_pre_action")
            except Exception:
                pass

        return api_result


# ---------------------------------------------------------------------------
# Cockpit Replay Engine (replaces ReplayEngine)
# ---------------------------------------------------------------------------

class CockpitReplayEngine:
    """
    Implements the 3-branch counterfactual replay protocol
    using the virtual cockpit backend.

    Same protocol as hybridstress.gelab_integration.ReplayEngine:
    1. Save snapshot
    2. Replay hybrid (3 runs, majority vote)
    3. Replay API-only (3 runs, majority vote)
    4. Replay GUI-only (3 runs, majority vote)
    5. Derive label from decision table
    """

    RUNS_PER_BRANCH = 3

    def __init__(
        self,
        executor: CockpitExecutor,
        validator: CockpitCompositeValidator,
        output_dir: Path,
        cockpit_url: str = "http://localhost:8420",
    ):
        self.executor = executor
        self.validator = validator
        self.output_dir = output_dir
        self.client = CockpitClient(cockpit_url)
        self.cockpit_url = cockpit_url

    def replay_switch_event(
        self,
        task: Dict,
        snapshot_id: str,
        step_index: int,
        fault_config: Optional[FaultConfig] = None,
        screenshot_dir: Optional[Path] = None,
    ) -> SwitchEvent:
        """Execute full 3-branch replay for a single switch event."""
        if screenshot_dir is None:
            screenshot_dir = self.output_dir / "screenshots" / task["task_id"]
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Capture pre-switch screenshot from snapshot state
        self.client.restore_snapshot(snapshot_id)
        time.sleep(0.3)
        pre_path = str(screenshot_dir / f"pre_{step_index}.png")
        capture_screenshot_cockpit(pre_path, self.cockpit_url)

        event = SwitchEvent(
            task_id=task["task_id"],
            step_index=step_index,
            action=task["instruction"],
            postconditions=task["postconditions"],
            emulator_snapshot_id=snapshot_id,
            pre_screenshot_path=pre_path,
            timestamp_pre=time.time(),
            fault_type=fault_config.fault_type if fault_config else FaultType.NONE,
            fault_severity=fault_config.fault_severity if fault_config else FaultSeverity.NONE,
        )

        # Branch 1: Hybrid (with optional fault injection)
        event.hybrid_result = self._run_branch(
            "hybrid", task, snapshot_id, fault_config, screenshot_dir, step_index
        )

        # Branch 2: API-only (NO fault injection)
        event.api_only_result = self._run_branch(
            "api_only", task, snapshot_id, None, screenshot_dir, step_index
        )

        # Branch 3: GUI-only (NO fault injection)
        event.gui_only_result = self._run_branch(
            "gui_only", task, snapshot_id, None, screenshot_dir, step_index
        )

        # Post screenshot from hybrid run 0
        hybrid_post = screenshot_dir / f"hybrid_run0_post_{step_index}.png"
        if hybrid_post.exists():
            event.post_screenshot_path = str(hybrid_post)
        else:
            post_path = str(screenshot_dir / f"post_{step_index}.png")
            capture_screenshot_cockpit(post_path, self.cockpit_url)
            event.post_screenshot_path = post_path
        event.timestamp_post = time.time()

        # Derive label
        event.label = event.derive_label()

        # Save event
        event_path = self.output_dir / "events" / f"{event.event_id}.json"
        event.save(event_path)

        logger.info(
            f"Event {event.event_id}: {event.label.value} "
            f"(H={event.hybrid_result.majority_outcome.value}, "
            f"A={event.api_only_result.majority_outcome.value}, "
            f"G={event.gui_only_result.majority_outcome.value})"
        )

        return event

    def _run_branch(
        self,
        mode: str,
        task: Dict,
        snapshot_id: str,
        fault_config: Optional[FaultConfig],
        screenshot_dir: Path,
        step_index: int,
    ) -> BranchResult:
        """Run a single branch with 3 independent runs and majority vote."""
        outcomes: List[BranchOutcome] = []
        durations: List[int] = []

        for run_idx in range(self.RUNS_PER_BRANCH):
            # Restore snapshot for deterministic replay
            if not self.client.restore_snapshot(snapshot_id):
                logger.error(f"Branch {mode} run {run_idx}: snapshot restore failed")
                outcomes.append(BranchOutcome.ERROR)
                durations.append(0)
                continue

            time.sleep(0.2)

            # Save pre-action snapshot for fault injection
            if fault_config:
                self.client.save_snapshot("_pre_action")

            start_time = time.time()

            try:
                if mode == "hybrid":
                    exec_result = self.executor.execute_task_hybrid(task, fault_config)
                elif mode == "api_only":
                    exec_result = self.executor.execute_task_api_only(task)
                else:
                    exec_result = self.executor.execute_task_gui_only(task)

                if exec_result.get("status") == "error":
                    logger.warning(
                        f"Branch {mode} run {run_idx}: executor error: "
                        f"{exec_result.get('error', 'unknown')}"
                    )
                    outcomes.append(BranchOutcome.ERROR)
                    duration_ms = int((time.time() - start_time) * 1000)
                    durations.append(duration_ms)
                    continue

                # Capture post screenshot and validate.
                # For STALE_OBSERVATION faults, use the cached stale screenshot
                # (captured BEFORE the action) instead of a fresh one.
                post_screenshot = str(
                    screenshot_dir / f"{mode}_run{run_idx}_post_{step_index}.png"
                )
                if mode == "hybrid" and exec_result.get("stale_screenshot"):
                    import shutil
                    shutil.copy2(exec_result["stale_screenshot"], post_screenshot)
                else:
                    capture_screenshot_cockpit(post_screenshot, self.cockpit_url)
                self.validator.set_screenshot(post_screenshot)

                outcome, details = self.validator.validate_all(task["postconditions"])
                outcomes.append(outcome)

            except Exception as e:
                logger.error(f"Branch {mode} run {run_idx} failed: {e}")
                outcomes.append(BranchOutcome.ERROR)

            duration_ms = int((time.time() - start_time) * 1000)
            durations.append(duration_ms)

        majority = BranchResult.compute_majority(outcomes)
        return BranchResult(
            mode=mode,
            run_outcomes=outcomes,
            majority_outcome=majority,
            run_durations_ms=durations,
        )


# ---------------------------------------------------------------------------
# Convenience: start cockpit server in background
# ---------------------------------------------------------------------------

def start_cockpit_server(host: str = "0.0.0.0", port: int = 8420) -> None:
    """Start the cockpit FastAPI server in a background thread."""
    import threading
    import uvicorn
    from .app import app

    def _run():
        uvicorn.run(app, host=host, port=port, log_level="warning")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info(f"Cockpit server starting on {host}:{port}")

    # Wait for server to be ready
    client = CockpitClient(f"http://localhost:{port}")
    for _ in range(30):
        if client.is_alive():
            logger.info("Cockpit server is ready")
            return
        time.sleep(0.5)
    logger.warning("Cockpit server may not be ready (timeout)")
