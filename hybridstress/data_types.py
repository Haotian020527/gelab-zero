"""
HybridStress Data Structures
============================

Defines the core SwitchEvent, Predicate, and FaultConfig types
used throughout the HybridStress benchmark.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple


class FaultType(Enum):
    """3-type fault taxonomy for modality-boundary failures."""
    NONE = "none"
    STALE_OBSERVATION = "stale_observation"      # GUI perception lags behind API state
    PHANTOM_ACK = "phantom_ack"                  # API reports success before completion
    STATE_ROLLBACK = "state_rollback"            # Action partially reverts at one modality


class FaultSeverity(Enum):
    """Severity levels for fault injection."""
    NONE = "none"
    MILD = "mild"          # Subtle: 100-300ms delay, 1 field stale
    MODERATE = "moderate"  # Noticeable: 300ms-1s delay, key fields stale
    SEVERE = "severe"      # Critical: >1s delay, full page stale


class BranchOutcome(Enum):
    """Outcome of a single replay branch."""
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"        # Replay infrastructure failure (not app failure)


class SwitchLabel(Enum):
    """
    Exhaustive label derived from 3-branch counterfactual outcomes.
    See decision table in FINAL_PROPOSAL.md.
    """
    CONSISTENT_PASS = "consistent_pass"           # No failure
    BOUNDARY_SPECIFIC = "boundary_specific"       # Hybrid fails, both unimodals succeed
    GUI_PREFERRED = "gui_preferred"               # API+hybrid fail, GUI works
    API_PREFERRED = "api_preferred"               # GUI+hybrid fail, API works
    UNIVERSALLY_HARD = "universally_hard"         # All fail
    HYBRID_ADVANTAGE = "hybrid_advantage"         # Only hybrid succeeds
    PARTIAL_FAIL = "partial_fail"                 # Other combinations


@dataclass
class Predicate:
    """
    Structured postcondition predicate.
    Each predicate is a typed (subject, relation, object) tuple
    that can be verified by deterministic validators.
    """
    subject: str      # e.g., "cart", "notification_bar", "current_screen"
    relation: str     # e.g., "contains", "shows", "is", "value_is"
    object: str       # e.g., "Blue Widget x1", "Message sent", "order_page"

    def to_dict(self) -> dict:
        return {"subject": self.subject, "relation": self.relation, "object": self.object}

    @classmethod
    def from_dict(cls, d: dict) -> Predicate:
        return cls(subject=d["subject"], relation=d["relation"], object=d["object"])

    def __str__(self) -> str:
        return f"({self.subject} {self.relation} {self.object})"


@dataclass
class BranchResult:
    """Result of a single branch replay (3 runs with majority vote)."""
    mode: str                          # "hybrid", "api_only", "gui_only"
    run_outcomes: List[BranchOutcome]  # Outcomes of 3 independent runs
    majority_outcome: BranchOutcome    # Majority vote result
    run_durations_ms: List[int] = field(default_factory=list)

    @staticmethod
    def compute_majority(outcomes: List[BranchOutcome]) -> BranchOutcome:
        """Majority vote over 3 runs. Requires strict majority.

        - If >=2 runs ERROR: return ERROR
        - If >=2 runs SUCCESS (among non-ERROR): return SUCCESS
        - If >=2 runs FAILURE (among non-ERROR): return FAILURE
        - Otherwise (tie / no majority): return ERROR (unreliable)
        """
        error_count = sum(1 for o in outcomes if o == BranchOutcome.ERROR)
        if error_count >= 2:
            return BranchOutcome.ERROR
        valid = [o for o in outcomes if o != BranchOutcome.ERROR]
        if not valid:
            return BranchOutcome.ERROR
        success_count = sum(1 for o in valid if o == BranchOutcome.SUCCESS)
        failure_count = sum(1 for o in valid if o == BranchOutcome.FAILURE)
        if success_count >= 2:
            return BranchOutcome.SUCCESS
        elif failure_count >= 2:
            return BranchOutcome.FAILURE
        else:
            # No strict majority (e.g., [SUCCESS, FAILURE] after filtering errors)
            return BranchOutcome.ERROR


@dataclass
class SwitchEvent:
    """
    Core data structure for the HybridStress benchmark.
    Each SwitchEvent represents a single modality-boundary crossing.
    """
    # Identification
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: str = ""
    step_index: int = 0

    # Core observation
    pre_screenshot_path: str = ""   # Path to pre-switch screenshot
    post_screenshot_path: str = ""  # Path to post-switch screenshot
    action: str = ""                # Action description
    postconditions: List[Predicate] = field(default_factory=list)

    # Checkpoint
    emulator_snapshot_id: str = ""  # Android emulator snapshot ID

    # Counterfactual labels (from 3-branch replay)
    hybrid_result: Optional[BranchResult] = None
    api_only_result: Optional[BranchResult] = None
    gui_only_result: Optional[BranchResult] = None

    # Derived label
    label: SwitchLabel = SwitchLabel.CONSISTENT_PASS

    # Fault metadata
    fault_type: FaultType = FaultType.NONE
    fault_severity: FaultSeverity = FaultSeverity.NONE

    # Timestamps
    timestamp_pre: float = 0.0
    timestamp_post: float = 0.0

    def derive_label(self) -> SwitchLabel:
        """
        Apply the exhaustive decision table to derive the switch label.

        | Hybrid | API-only | GUI-only | Label               |
        |--------|----------|----------|---------------------|
        | ✓      | ✓        | ✓        | consistent_pass     |
        | ✓      | ✗        | ✓        | consistent_pass     |
        | ✓      | ✓        | ✗        | consistent_pass     |
        | ✗      | ✓        | ✓        | BOUNDARY_SPECIFIC   |
        | ✗      | ✗        | ✓        | gui_preferred       |
        | ✗      | ✓        | ✗        | api_preferred       |
        | ✗      | ✗        | ✗        | universally_hard    |
        | ✓      | ✗        | ✗        | hybrid_advantage    |
        """
        if not all([self.hybrid_result, self.api_only_result, self.gui_only_result]):
            return SwitchLabel.CONSISTENT_PASS

        # CRITICAL: If any branch had an ERROR (infrastructure failure),
        # the label is unreliable — mark as PARTIAL_FAIL and exclude
        # from C1/C2 training and evaluation.
        for branch in [self.hybrid_result, self.api_only_result, self.gui_only_result]:
            if branch.majority_outcome == BranchOutcome.ERROR:
                return SwitchLabel.PARTIAL_FAIL

        h = self.hybrid_result.majority_outcome == BranchOutcome.SUCCESS
        a = self.api_only_result.majority_outcome == BranchOutcome.SUCCESS
        g = self.gui_only_result.majority_outcome == BranchOutcome.SUCCESS

        if h and a and g:
            return SwitchLabel.CONSISTENT_PASS
        elif h and not a and g:
            return SwitchLabel.CONSISTENT_PASS  # API broken, hybrid OK via fallback
        elif h and a and not g:
            return SwitchLabel.CONSISTENT_PASS  # GUI broken, hybrid OK via API
        elif not h and a and g:
            return SwitchLabel.BOUNDARY_SPECIFIC
        elif not h and not a and g:
            return SwitchLabel.GUI_PREFERRED
        elif not h and a and not g:
            return SwitchLabel.API_PREFERRED
        elif not h and not a and not g:
            return SwitchLabel.UNIVERSALLY_HARD
        elif h and not a and not g:
            return SwitchLabel.HYBRID_ADVANTAGE
        else:
            return SwitchLabel.PARTIAL_FAIL

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        d = {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "step_index": self.step_index,
            "pre_screenshot_path": self.pre_screenshot_path,
            "post_screenshot_path": self.post_screenshot_path,
            "action": self.action,
            "postconditions": [p.to_dict() for p in self.postconditions],
            "emulator_snapshot_id": self.emulator_snapshot_id,
            "label": self.label.value,
            "fault_type": self.fault_type.value,
            "fault_severity": self.fault_severity.value,
            "timestamp_pre": self.timestamp_pre,
            "timestamp_post": self.timestamp_post,
        }
        for mode in ["hybrid", "api_only", "gui_only"]:
            result = getattr(self, f"{mode}_result")
            if result:
                d[f"{mode}_result"] = {
                    "mode": result.mode,
                    "run_outcomes": [o.value for o in result.run_outcomes],
                    "majority_outcome": result.majority_outcome.value,
                    "run_durations_ms": result.run_durations_ms,
                }
        return d

    def save(self, path: Path) -> None:
        """Save event to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> SwitchEvent:
        """Load event from JSON file, including branch results for provenance."""
        with open(path) as f:
            d = json.load(f)
        event = cls(
            event_id=d["event_id"],
            task_id=d["task_id"],
            step_index=d["step_index"],
            pre_screenshot_path=d["pre_screenshot_path"],
            post_screenshot_path=d["post_screenshot_path"],
            action=d["action"],
            postconditions=[Predicate.from_dict(p) for p in d["postconditions"]],
            emulator_snapshot_id=d["emulator_snapshot_id"],
            label=SwitchLabel(d["label"]),
            fault_type=FaultType(d["fault_type"]),
            fault_severity=FaultSeverity(d["fault_severity"]),
            timestamp_pre=d.get("timestamp_pre", 0.0),
            timestamp_post=d.get("timestamp_post", 0.0),
        )
        # Deserialize branch results for full provenance
        for mode in ["hybrid", "api_only", "gui_only"]:
            key = f"{mode}_result"
            if key in d:
                br = d[key]
                setattr(event, f"{mode}_result", BranchResult(
                    mode=br["mode"],
                    run_outcomes=[BranchOutcome(o) for o in br["run_outcomes"]],
                    majority_outcome=BranchOutcome(br["majority_outcome"]),
                    run_durations_ms=br.get("run_durations_ms", []),
                ))
        # Verify label consistency: recompute and warn if mismatch
        if event.hybrid_result and event.api_only_result and event.gui_only_result:
            recomputed = event.derive_label()
            if recomputed != event.label:
                import warnings
                warnings.warn(
                    f"Event {event.event_id}: stored label={event.label.value} "
                    f"differs from recomputed={recomputed.value}. Using recomputed."
                )
                event.label = recomputed
        return event


@dataclass
class FaultConfig:
    """Configuration for fault injection."""
    fault_type: FaultType
    fault_severity: FaultSeverity

    # Stale Observation parameters
    stale_delay_ms: int = 0       # How old the cached screenshot is

    # Phantom Ack parameters
    ack_intercept: bool = False   # Whether to intercept API response

    # State Rollback parameters
    rollback_after_ms: int = 0    # Delay before injecting rollback

    @classmethod
    def from_type_severity(cls, ft: FaultType, fs: FaultSeverity) -> FaultConfig:
        """Create config from type and severity."""
        config = cls(fault_type=ft, fault_severity=fs)

        if ft == FaultType.STALE_OBSERVATION:
            delays = {FaultSeverity.MILD: 200, FaultSeverity.MODERATE: 800, FaultSeverity.SEVERE: 2000}
            config.stale_delay_ms = delays.get(fs, 0)

        elif ft == FaultType.PHANTOM_ACK:
            config.ack_intercept = fs != FaultSeverity.NONE

        elif ft == FaultType.STATE_ROLLBACK:
            delays = {FaultSeverity.MILD: 500, FaultSeverity.MODERATE: 1000, FaultSeverity.SEVERE: 3000}
            config.rollback_after_ms = delays.get(fs, 0)

        return config


# Convenience: all conditions for a task
def generate_all_conditions(task_id: str) -> List[Tuple[FaultType, FaultSeverity]]:
    """
    Generate all (fault_type, severity) conditions for a single task.
    Returns: 1 clean + 3 faults × 3 severities = 10 conditions.
    """
    conditions = [(FaultType.NONE, FaultSeverity.NONE)]
    for ft in [FaultType.STALE_OBSERVATION, FaultType.PHANTOM_ACK, FaultType.STATE_ROLLBACK]:
        for fs in [FaultSeverity.MILD, FaultSeverity.MODERATE, FaultSeverity.SEVERE]:
            conditions.append((ft, fs))
    return conditions
