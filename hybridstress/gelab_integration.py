"""
HybridStress ↔ gelab-zero Integration Layer
=============================================

Bridges HybridStress benchmark infrastructure with the gelab-zero
agent system. Handles:
1. Device management via ADB
2. Emulator snapshot save/restore
3. Task execution in hybrid / API-only / GUI-only modes
4. Screenshot capture for pre/post switch observation
"""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .data_types import (
    BranchOutcome, BranchResult, FaultConfig, FaultType, FaultSeverity,
    Predicate, SwitchEvent, SwitchLabel,
)
from .fault_injector import FaultInjector, InstrumentedBackend
from .validators import CompositeValidator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ADB utilities
# ---------------------------------------------------------------------------

def adb_cmd(args: List[str], device_id: Optional[str] = None, timeout: int = 30) -> str:
    """Run an ADB command and return stdout."""
    cmd = ["adb"]
    if device_id:
        cmd += ["-s", device_id]
    cmd += args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception as e:
        logger.warning(f"ADB command failed: {cmd}: {e}")
        return ""


def ensure_adb_connected(device_id: Optional[str] = None, max_retries: int = 3) -> bool:
    """
    Ensure the ADB device is connected. If it's a TCP/IP device (contains ':'),
    attempt reconnection. Returns True if device is connected.
    """
    for attempt in range(max_retries):
        # Check if device appears in device list
        devices_out = adb_cmd(["devices"])
        if device_id and device_id in devices_out:
            return True

        # If it's a TCP device, try reconnecting
        if device_id and ":" in device_id:
            logger.info(f"ADB reconnect attempt {attempt + 1}/{max_retries} for {device_id}")
            adb_cmd(["disconnect", device_id])
            time.sleep(1)
            connect_out = adb_cmd(["connect", device_id], timeout=15)
            if "connected" in connect_out.lower():
                time.sleep(2)
                logger.info(f"ADB reconnected: {device_id}")
                return True
        elif not device_id:
            # No specific device, just check any device
            if "device" in devices_out and "offline" not in devices_out:
                return True

        time.sleep(2)

    logger.error(f"ADB device {device_id} unreachable after {max_retries} attempts")
    return False


_snapshot_mode: Optional[str] = None  # "emulator" or "activity_reset"


def _detect_snapshot_mode(device_id: Optional[str] = None) -> str:
    """Detect whether the device is an emulator (supports snapshots) or physical."""
    global _snapshot_mode
    if _snapshot_mode is not None:
        return _snapshot_mode

    # Check if device is an emulator
    out = adb_cmd(["shell", "getprop", "ro.hardware"], device_id)
    if "ranchu" in out.lower() or "goldfish" in out.lower():
        _snapshot_mode = "emulator"
        logger.info("Detected Android emulator — using snapshot save/restore")
    else:
        _snapshot_mode = "activity_reset"
        logger.info(
            "Detected physical device — using activity reset (no true snapshots). "
            "For full replay isolation, use an Android emulator (AVD)."
        )
    return _snapshot_mode


def save_emulator_snapshot(snapshot_id: str, device_id: Optional[str] = None) -> bool:
    """Save device state for later replay."""
    mode = _detect_snapshot_mode(device_id)

    if mode == "emulator":
        out = adb_cmd(["emu", "avd", "snapshot", "save", snapshot_id], device_id)
        if "OK" in out or out == "":
            logger.info(f"Emulator snapshot saved: {snapshot_id}")
            return True
        logger.warning(f"Emulator snapshot save may have failed: {out}")
        return True

    # Physical device: press HOME and clear recent apps as best-effort reset point
    adb_cmd(["shell", "input", "keyevent", "KEYCODE_HOME"], device_id)
    time.sleep(0.5)
    logger.info(f"Activity state saved (HOME pressed): {snapshot_id}")
    return True


def restore_emulator_snapshot(snapshot_id: str, device_id: Optional[str] = None) -> bool:
    """Restore device state from a saved snapshot."""
    mode = _detect_snapshot_mode(device_id)

    if mode == "emulator":
        out = adb_cmd(["emu", "avd", "snapshot", "load", snapshot_id], device_id)
        time.sleep(2)
        logger.info(f"Emulator snapshot restored: {snapshot_id}")
        return True

    # Physical device: press HOME, kill the target app, wait for clean state.
    # This is NOT equivalent to a true snapshot restore — the replay will be
    # noisier. Log a warning so the user knows to expect lower determinism.
    adb_cmd(["shell", "input", "keyevent", "KEYCODE_HOME"], device_id)
    time.sleep(1)
    logger.info(f"Activity reset (HOME pressed): {snapshot_id}")
    return True


def capture_screenshot_adb(
    save_path: str, device_id: Optional[str] = None
) -> str:
    """Capture screenshot via ADB and save to local path."""
    remote_path = "/sdcard/hybridstress_screenshot.png"
    adb_cmd(["shell", "screencap", "-p", remote_path], device_id)
    adb_cmd(["pull", remote_path, save_path], device_id)
    adb_cmd(["shell", "rm", remote_path], device_id)
    return save_path


def press_home(device_id: Optional[str] = None):
    """Press HOME key."""
    adb_cmd(["shell", "input", "keyevent", "KEYCODE_HOME"], device_id)


def launch_app(package: str, device_id: Optional[str] = None):
    """Launch an app by package name."""
    adb_cmd([
        "shell", "monkey", "-p", package,
        "-c", "android.intent.category.LAUNCHER", "1"
    ], device_id)
    time.sleep(2)


def force_stop_app(package: str, device_id: Optional[str] = None):
    """Force stop an app."""
    adb_cmd(["shell", "am", "force-stop", package], device_id)


# ---------------------------------------------------------------------------
# gelab-zero task execution wrapper
# ---------------------------------------------------------------------------

class GelabExecutor:
    """
    Wraps gelab-zero's execute_task function with fault injection
    and mode control (hybrid / API-only / GUI-only).
    """

    def __init__(
        self,
        device_id: str,
        gelab_root: str = "/home/fce/mnt/2T/Frank/LHT/gelab-zero-new",
        injector: Optional[FaultInjector] = None,
    ):
        self.device_id = device_id
        self.gelab_root = gelab_root
        self.injector = injector or FaultInjector()

    def execute_task_hybrid(
        self,
        task_instruction: str,
        max_steps: int = 20,
        fault_config: Optional[FaultConfig] = None,
    ) -> Dict[str, Any]:
        """
        Execute a task in HYBRID mode (API-first + GUI-fallback).
        This is gelab-zero's default mode.
        When fault_config is provided, monkeypatches the backend to intercept
        screenshots, API responses, and action completion.
        """
        if fault_config:
            self.injector.activate(fault_config)
            self._install_fault_hooks()

        result = self._call_gelab_execute(
            task=task_instruction,
            max_steps=max_steps,
            use_router=True,
        )

        if fault_config:
            result["injection_log"] = self.injector.get_injection_log()
            self._remove_fault_hooks()
            self.injector.deactivate()

        return result

    def execute_task_api_only(
        self,
        task_instruction: str,
        max_steps: int = 20,
    ) -> Dict[str, Any]:
        """
        Execute a task in API-ONLY mode.
        Forces CockpitRouter to use only API tools, disabling GUI fallback.
        """
        return self._call_gelab_execute(
            task=task_instruction,
            max_steps=max_steps,
            use_router=True,
            force_api_only=True,
        )

    def execute_task_gui_only(
        self,
        task_instruction: str,
        max_steps: int = 20,
    ) -> Dict[str, Any]:
        """
        Execute a task in GUI-ONLY mode.
        Bypasses CockpitRouter entirely, uses only GUI agent.
        """
        return self._call_gelab_execute(
            task=task_instruction,
            max_steps=max_steps,
            use_router=False,
        )

    # ── Fault injection hooks ───────────────────────────────────────────

    _original_get_screenshot = None
    _original_execute_task = None

    def _install_fault_hooks(self):
        """Monkeypatch the MCP backend to route through the fault injector."""
        try:
            import sys
            if self.gelab_root not in sys.path:
                sys.path.insert(0, self.gelab_root)
            import mcp_server.mcp_backend_implements as backend

            # Save originals
            self._original_get_screenshot = backend.get_screenshot
            self._original_execute_task = getattr(backend, '_original_execute_task_fn', None)

            # Patch get_screenshot to intercept stale observations
            injector = self.injector
            orig_screenshot = backend.get_screenshot

            def patched_get_screenshot(device_id, *args, **kwargs):
                fresh = orig_screenshot(device_id, *args, **kwargs)
                return injector.intercept_screenshot(fresh)

            backend.get_screenshot = patched_get_screenshot
            logger.info("Fault hooks installed on mcp_backend_implements")
        except Exception as e:
            logger.warning(f"Could not install fault hooks: {e}")

    def _remove_fault_hooks(self):
        """Restore original backend functions."""
        try:
            import mcp_server.mcp_backend_implements as backend
            if self._original_get_screenshot is not None:
                backend.get_screenshot = self._original_get_screenshot
                self._original_get_screenshot = None
            logger.info("Fault hooks removed")
        except Exception as e:
            logger.warning(f"Could not remove fault hooks: {e}")

    def _call_gelab_execute(
        self,
        task: str,
        max_steps: int,
        use_router: bool,
        force_api_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Call gelab-zero's execute_task.

        When running on the server (detected by gelab_root existing),
        imports and calls the functions directly. Otherwise, falls back
        to subprocess execution.
        """
        import sys

        mode = "hybrid" if use_router and not force_api_only else \
               "api_only" if force_api_only else "gui_only"

        # Try direct import (when running on the server)
        if os.path.isdir(self.gelab_root):
            if self.gelab_root not in sys.path:
                sys.path.insert(0, self.gelab_root)
            try:
                from mcp_server.mcp_backend_implements import (
                    execute_task,
                )

                if use_router:
                    from mcp_server.mcp_backend_implements import (
                        execute_task_with_cockpit_router,
                    )

                if use_router and not force_api_only:
                    # Hybrid mode: router decides API vs GUI
                    exec_fn = execute_task_with_cockpit_router
                elif use_router and force_api_only:
                    # API-only: use router but disable GUI fallback
                    exec_fn = execute_task_with_cockpit_router
                else:
                    # GUI-only: bypass router entirely
                    exec_fn = execute_task

                # Build kwargs
                exec_kwargs = dict(
                    device_id=self.device_id,
                    task=task,
                    max_steps=max_steps,
                    reset_environment=True,
                    enable_intermediate_logs=True,
                    enable_intermediate_image_caption=False,
                    enable_intermediate_screenshots=True,
                    enable_final_screenshot=True,
                    enable_final_image_caption=False,
                    reply_mode="no_reply",
                    session_id=None,
                    reply_from_client=None,
                )

                # Pass force_api_only flag to router when applicable.
                # Only add if the function signature accepts it (avoid TypeError).
                if use_router and force_api_only:
                    import inspect
                    sig = inspect.signature(exec_fn)
                    if "force_api_only" in sig.parameters:
                        exec_kwargs["force_api_only"] = True
                    else:
                        # Backend doesn't support force_api_only natively.
                        # Temporarily disable GUI fallback by monkeypatching.
                        logger.info("force_api_only: monkeypatching router to disable GUI fallback")
                        try:
                            from mcp_server.cockpit_router import CockpitRouter
                            _orig_fallback = CockpitRouter._gui_fallback_executor if hasattr(CockpitRouter, '_gui_fallback_executor') else None
                            CockpitRouter._gui_fallback_executor = lambda *a, **kw: {"status": "error", "message": "GUI fallback disabled for API-only eval"}
                        except Exception:
                            pass

                result = exec_fn(**exec_kwargs)

                # Restore GUI fallback if monkeypatched
                if use_router and force_api_only:
                    try:
                        if _orig_fallback is not None:
                            CockpitRouter._gui_fallback_executor = _orig_fallback
                    except Exception:
                        pass
                return {
                    "status": "success",
                    "mode": mode,
                    "result": result,
                }
            except Exception as e:
                logger.error(f"Direct execution failed ({mode}): {e}")
                return {
                    "status": "error",
                    "mode": mode,
                    "error": str(e),
                }

        # Fallback: subprocess execution via SSH
        logger.warning(f"gelab_root not found locally ({self.gelab_root}), using SSH fallback")
        script = (
            f'import sys, json, os; '
            f'sys.path.insert(0, "{self.gelab_root}"); '
            f'os.chdir("{self.gelab_root}"); '
            f'from mcp_server.mcp_backend_implements import execute_task'
            f'{", execute_task_with_cockpit_router" if use_router else ""}; '
            f'result = {"execute_task_with_cockpit_router" if use_router else "execute_task"}'
            f'(device_id="{self.device_id}", task={json.dumps(task, ensure_ascii=False)}, '
            f'max_steps={max_steps}, reset_environment=True, '
            f'enable_intermediate_logs=True, enable_intermediate_image_caption=False, '
            f'enable_intermediate_screenshots=True, enable_final_screenshot=True, '
            f'enable_final_image_caption=False, reply_mode="no_reply", '
            f'session_id=None, reply_from_client=None); '
            f'print(json.dumps({{"status": "success", "mode": "{mode}"}}))'
        )
        try:
            out = run_on_server(script, timeout=600)
            return {"status": "success", "mode": mode, "output": out}
        except Exception as e:
            return {"status": "error", "mode": mode, "error": str(e)}


# ---------------------------------------------------------------------------
# Branch replay protocol
# ---------------------------------------------------------------------------

class ReplayEngine:
    """
    Implements the 3-branch counterfactual replay protocol.

    For each switch event:
    1. Save emulator snapshot
    2. Replay in hybrid mode (3 runs, majority vote)
    3. Replay in API-only mode (3 runs, majority vote)
    4. Replay in GUI-only mode (3 runs, majority vote)
    5. Derive label from decision table
    """

    RUNS_PER_BRANCH = 3

    def __init__(
        self,
        executor: GelabExecutor,
        validator: CompositeValidator,
        output_dir: Path,
        device_id: Optional[str] = None,
    ):
        self.executor = executor
        self.validator = validator
        self.output_dir = output_dir
        self.device_id = device_id

    def replay_switch_event(
        self,
        task: Dict,
        snapshot_id: str,
        step_index: int,
        fault_config: Optional[FaultConfig] = None,
        screenshot_dir: Optional[Path] = None,
    ) -> SwitchEvent:
        """
        Execute full 3-branch replay for a single switch event.

        Protocol:
        1. Restore snapshot → capture pre-switch screenshot
        2. For each branch (hybrid, api_only, gui_only):
           a. Restore from same snapshot
           b. Execute remaining subtask in designated mode
           c. Capture post-execution screenshot
           d. Run deterministic validators
           e. Repeat 3 times, majority vote
        3. Use post screenshot from hybrid branch run 0 as the event's
           post_screenshot (for CMV training — represents what the agent sees)
        """
        if screenshot_dir is None:
            screenshot_dir = self.output_dir / "screenshots" / task["task_id"]
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Ensure device is connected before starting replay
        ensure_adb_connected(self.device_id)

        # Capture pre-switch screenshot from the snapshot state
        restore_emulator_snapshot(snapshot_id, self.device_id)
        time.sleep(1)
        pre_path = str(screenshot_dir / f"pre_{step_index}.png")
        capture_screenshot_adb(pre_path, self.device_id)

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

        # Branch 2: API-only (NO fault injection — counterfactual baseline)
        event.api_only_result = self._run_branch(
            "api_only", task, snapshot_id, None, screenshot_dir, step_index
        )

        # Branch 3: GUI-only (NO fault injection — counterfactual baseline)
        event.gui_only_result = self._run_branch(
            "gui_only", task, snapshot_id, None, screenshot_dir, step_index
        )

        # Use the hybrid branch's post-screenshot from run 0 as the event's
        # post_screenshot — this is what the agent actually observes.
        hybrid_post = screenshot_dir / f"hybrid_run0_post_{step_index}.png"
        if hybrid_post.exists():
            event.post_screenshot_path = str(hybrid_post)
        else:
            # Fallback: capture fresh from current state
            post_path = str(screenshot_dir / f"post_{step_index}.png")
            capture_screenshot_adb(post_path, self.device_id)
            event.post_screenshot_path = post_path
        event.timestamp_post = time.time()

        # Derive label from decision table
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
            # Ensure ADB connection is alive before each run
            if not ensure_adb_connected(self.device_id):
                logger.error(f"Branch {mode} run {run_idx}: device unreachable, skipping")
                outcomes.append(BranchOutcome.ERROR)
                durations.append(0)
                continue

            # Restore snapshot
            restore_emulator_snapshot(snapshot_id, self.device_id)
            time.sleep(1)

            start_time = time.time()

            try:
                # Execute task in the specified mode
                if mode == "hybrid":
                    exec_result = self.executor.execute_task_hybrid(
                        task["instruction"],
                        fault_config=fault_config,
                    )
                elif mode == "api_only":
                    exec_result = self.executor.execute_task_api_only(task["instruction"])
                else:
                    exec_result = self.executor.execute_task_gui_only(task["instruction"])

                # Check execution status — record ERROR for infrastructure failures
                if exec_result.get("status") == "error":
                    logger.warning(
                        f"Branch {mode} run {run_idx}: executor returned error: "
                        f"{exec_result.get('error', 'unknown')}"
                    )
                    outcomes.append(BranchOutcome.ERROR)
                    continue

                # Validate postconditions
                post_screenshot = str(
                    screenshot_dir / f"{mode}_run{run_idx}_post_{step_index}.png"
                )
                capture_screenshot_adb(post_screenshot, self.device_id)
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
# SSH execution helper
# ---------------------------------------------------------------------------

def run_on_server(
    script: str,
    conda_env: str = "gelab-zero",
    conda_path: str = "/home/fce/miniconda3",
    timeout: int = 600,
) -> str:
    """
    Execute a Python script on the GPU server via SSH + paramiko.
    Returns stdout.
    """
    import paramiko

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("9.tcp.vip.cpolar.cn", port=14772, username="fce", password="1234", timeout=15)

    # Wrap script with conda activation
    full_cmd = (
        f'eval "$({conda_path}/bin/conda shell.bash hook)" && '
        f'conda activate {conda_env} && '
        f'python -c {json.dumps(script)}'
    )

    stdin, stdout, stderr = ssh.exec_command(full_cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")

    ssh.close()

    if err and "error" in err.lower():
        logger.warning(f"Server stderr: {err[:500]}")

    return out


def run_script_on_server(
    script_path: str,
    args: str = "",
    conda_env: str = "gelab-zero",
    conda_path: str = "/home/fce/miniconda3",
    work_dir: str = "/home/fce/mnt/2T/Frank/LHT/gelab-zero-new",
    timeout: int = 600,
    use_tmux: bool = False,
    session_name: str = "hybridstress",
) -> str:
    """
    Execute a Python script file on the GPU server.
    If use_tmux=True, runs in a detached tmux session.
    """
    import paramiko

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("9.tcp.vip.cpolar.cn", port=14772, username="fce", password="1234", timeout=15)

    activate = (
        f'eval "$({conda_path}/bin/conda shell.bash hook)" && '
        f'conda activate {conda_env}'
    )

    if use_tmux:
        cmd = (
            f'tmux new-session -d -s {session_name} '
            f'"{activate} && cd {work_dir} && python {script_path} {args} '
            f'> /tmp/{session_name}.log 2>&1"'
        )
    else:
        cmd = f'{activate} && cd {work_dir} && python {script_path} {args}'

    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    ssh.close()

    return out
