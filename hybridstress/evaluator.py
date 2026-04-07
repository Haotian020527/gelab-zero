"""
HybridStress Evaluation Pipeline
==================================

Implements evaluation for all milestones:
- M1/B2: Prevalence analysis (C1)
- M2/B3: In-distribution detector comparison
- M3/B4: Transfer evaluation on natural traces (C2)
- M4/B5: Recovery utility study (C3, exploratory)

All evaluations use dataset ground truth from deterministic validators.
VLM is evaluated as a separate BASELINE, never as ground truth.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .data_types import SwitchEvent, SwitchLabel, FaultType, FaultSeverity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# B2: Prevalence Analysis (C1)
# ---------------------------------------------------------------------------

def prevalence_analysis(events: List[SwitchEvent]) -> Dict:
    """
    Analyze prevalence of boundary-specific failures.

    Success criterion: >15% of failures are BOUNDARY_SPECIFIC.

    Returns detailed breakdown by:
    - Label distribution (full decision table)
    - Fault type
    - App category
    """
    # Exclude PARTIAL_FAIL — unreliable labels from infrastructure errors
    valid_events = [e for e in events if e.label != SwitchLabel.PARTIAL_FAIL]
    total = len(valid_events)
    if total == 0:
        return {"error": "No valid events to analyze (all PARTIAL_FAIL)"}

    # Label distribution (valid events only)
    label_counts = Counter(e.label.value for e in valid_events)
    label_pcts = {k: v / total * 100 for k, v in label_counts.items()}

    # Failure events only (exclude consistent_pass and hybrid_advantage)
    failure_events = [
        e for e in valid_events
        if e.label not in (SwitchLabel.CONSISTENT_PASS, SwitchLabel.HYBRID_ADVANTAGE)
    ]
    n_failures = len(failure_events)
    n_boundary = sum(1 for e in valid_events if e.label == SwitchLabel.BOUNDARY_SPECIFIC)

    prevalence = n_boundary / n_failures * 100 if n_failures > 0 else 0.0

    # Breakdown by fault type
    by_fault_type = defaultdict(lambda: Counter())
    for e in events:
        by_fault_type[e.fault_type.value][e.label.value] += 1

    # Breakdown by app/task category
    by_task = defaultdict(lambda: Counter())
    for e in events:
        by_task[e.task_id.split("_")[0]][e.label.value] += 1

    result = {
        "total_events": total,
        "total_failures": n_failures,
        "boundary_specific_count": n_boundary,
        "prevalence_pct": round(prevalence, 2),
        "c1_passed": prevalence > 15.0,
        "label_distribution": dict(label_counts),
        "label_percentages": {k: round(v, 2) for k, v in label_pcts.items()},
        "by_fault_type": {k: dict(v) for k, v in by_fault_type.items()},
        "by_task_prefix": {k: dict(v) for k, v in by_task.items()},
    }

    logger.info(
        f"C1 Prevalence: {prevalence:.1f}% boundary-specific "
        f"({n_boundary}/{n_failures} failures) — "
        f"{'PASSED' if result['c1_passed'] else 'FAILED'}"
    )

    return result


# ---------------------------------------------------------------------------
# B3/B4: Detector Comparison
# ---------------------------------------------------------------------------

def detector_comparison(
    events: List[SwitchEvent],
    detector_scores: Dict[str, Dict[str, float]],
    split_name: str = "in_distribution",
) -> Dict:
    """
    Compare detector performance on switch events.

    Args:
        events: List of SwitchEvent with deterministic labels
        detector_scores: {detector_name: {event_id: score}}
            Detectors: "vlm_judge", "cmv", "fixed_delay", "api_status"
        split_name: "in_distribution" or "transfer"

    Returns:
        Comparison table with AUPRC, AUROC, ECE, Brier, false alarm rate
    """
    from .cmv_trainer import compute_binary_metrics

    # Ground truth: 1 = boundary-specific failure, 0 = not boundary-specific.
    # Aligns with proposal's CMV detection target. Excludes PARTIAL_FAIL events.
    gt = {}
    for e in events:
        if e.label == SwitchLabel.PARTIAL_FAIL:
            continue  # Skip events with infrastructure errors
        gt[e.event_id] = 1.0 if e.label == SwitchLabel.BOUNDARY_SPECIFIC else 0.0

    results = {"split": split_name, "n_events": len(events), "detectors": {}}

    for det_name, scores in detector_scores.items():
        # Align scores with ground truth
        event_ids = [eid for eid in gt if eid in scores]
        if not event_ids:
            results["detectors"][det_name] = {"error": "No matching events"}
            continue

        labels = np.array([gt[eid] for eid in event_ids])
        preds = np.array([scores[eid] for eid in event_ids])

        metrics = compute_binary_metrics(preds, labels)
        metrics["n_evaluated"] = len(event_ids)
        results["detectors"][det_name] = metrics

        logger.info(
            f"[{split_name}] {det_name}: AUPRC={metrics['auprc']:.4f}, "
            f"AUROC={metrics['auroc']:.4f}, FAR={metrics['false_alarm_rate']:.4f}"
        )

    return results


# ---------------------------------------------------------------------------
# B4: Transfer Evaluation (C2)
# ---------------------------------------------------------------------------

def transfer_evaluation(
    natural_events: List[SwitchEvent],
    detector_scores: Dict[str, Dict[str, float]],
    human_annotations: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Evaluate CMV transfer to natural traces (C2).

    Success criterion:
    - CMV AUPRC > 0.7
    - Gap to VLM judge < 10%

    Args:
        natural_events: Events from held-out apps (no fault injection)
        detector_scores: {detector_name: {event_id: score}}
        human_annotations: {event_id: label} from human annotators
    """
    # Override deterministic labels with human annotations where available.
    # Human annotations are the gold standard for natural traces.
    if human_annotations:
        for e in natural_events:
            if e.event_id in human_annotations:
                human_label = human_annotations[e.event_id]
                # human_label: 1.0 = boundary_specific, 0.0 = not
                if human_label >= 0.5:
                    e.label = SwitchLabel.BOUNDARY_SPECIFIC
                else:
                    # Keep existing label if it's not boundary_specific,
                    # or set to consistent_pass if no other info
                    if e.label == SwitchLabel.BOUNDARY_SPECIFIC:
                        e.label = SwitchLabel.CONSISTENT_PASS

    comparison = detector_comparison(
        natural_events, detector_scores, split_name="transfer"
    )

    # Check C2 criteria
    cmv_metrics = comparison["detectors"].get("cmv", {})
    vlm_metrics = comparison["detectors"].get("vlm_judge", {})

    cmv_auprc = cmv_metrics.get("auprc", 0.0)
    vlm_auprc = vlm_metrics.get("auprc", 0.0)
    gap = abs(vlm_auprc - cmv_auprc) * 100

    comparison["c2_results"] = {
        "cmv_auprc": cmv_auprc,
        "vlm_auprc": vlm_auprc,
        "gap_pct": round(gap, 2),
        "c2_auprc_passed": cmv_auprc > 0.7,
        "c2_gap_passed": gap < 10.0,
        "c2_overall_passed": cmv_auprc > 0.7 and gap < 10.0,
    }

    logger.info(
        f"C2 Transfer: CMV AUPRC={cmv_auprc:.4f}, VLM AUPRC={vlm_auprc:.4f}, "
        f"gap={gap:.1f}% — {'PASSED' if comparison['c2_results']['c2_overall_passed'] else 'FAILED'}"
    )

    return comparison


# ---------------------------------------------------------------------------
# B5: Recovery Utility (C3)
# ---------------------------------------------------------------------------

def recovery_evaluation(
    baseline_results: Dict[str, bool],
    blind_retry_results: Dict[str, bool],
    cmv_recovery_results: Dict[str, bool],
    n_bootstrap: int = 10000,
    seed: int = 42,
) -> Dict:
    """
    Evaluate recovery utility (C3, exploratory).

    Compares:
    1. gelab-zero baseline (no verification)
    2. gelab-zero + blind retry at every switch
    3. gelab-zero + CMV-triggered recovery

    Returns paired bootstrap confidence intervals.
    """
    rng = np.random.RandomState(seed)

    # Task success rates
    tasks = sorted(baseline_results.keys())
    n_tasks = len(tasks)

    baseline = np.array([float(baseline_results[t]) for t in tasks])
    blind = np.array([float(blind_retry_results[t]) for t in tasks])
    cmv = np.array([float(cmv_recovery_results[t]) for t in tasks])

    # Point estimates
    base_rate = baseline.mean()
    blind_rate = blind.mean()
    cmv_rate = cmv.mean()

    # Paired bootstrap CIs
    def bootstrap_delta(a, b, n_boot=n_bootstrap):
        deltas = []
        for _ in range(n_boot):
            idx = rng.choice(len(a), size=len(a), replace=True)
            deltas.append(b[idx].mean() - a[idx].mean())
        deltas = np.array(deltas)
        return {
            "mean_delta": float(np.mean(deltas)),
            "ci_lower": float(np.percentile(deltas, 2.5)),
            "ci_upper": float(np.percentile(deltas, 97.5)),
            "p_positive": float((deltas > 0).mean()),
        }

    cmv_vs_base = bootstrap_delta(baseline, cmv)
    blind_vs_base = bootstrap_delta(baseline, blind)
    cmv_vs_blind = bootstrap_delta(blind, cmv)

    result = {
        "n_tasks": n_tasks,
        "success_rates": {
            "baseline": round(base_rate, 4),
            "blind_retry": round(blind_rate, 4),
            "cmv_recovery": round(cmv_rate, 4),
        },
        "cmv_vs_baseline": cmv_vs_base,
        "blind_vs_baseline": blind_vs_base,
        "cmv_vs_blind": cmv_vs_blind,
        "c3_positive": cmv_vs_base["ci_lower"] > 0,
    }

    logger.info(
        f"C3 Recovery: baseline={base_rate:.2%}, cmv={cmv_rate:.2%}, "
        f"delta={cmv_vs_base['mean_delta']:.2%} "
        f"[{cmv_vs_base['ci_lower']:.2%}, {cmv_vs_base['ci_upper']:.2%}]"
    )

    return result


# ---------------------------------------------------------------------------
# B6: Human Calibration Study
# ---------------------------------------------------------------------------

def human_calibration(
    events: List[SwitchEvent],
    annotator_1: Dict[str, int],
    annotator_2: Dict[str, int],
) -> Dict:
    """
    Compute validator accuracy and inter-annotator agreement.

    Args:
        events: 50 sampled switch events with deterministic labels
        annotator_1: {event_id: 0/1} — human judgment
        annotator_2: {event_id: 0/1} — human judgment
    """
    common_ids = sorted(
        set(annotator_1.keys()) & set(annotator_2.keys()) &
        {e.event_id for e in events}
    )
    n = len(common_ids)

    if n == 0:
        return {"error": "No common annotations"}

    event_map = {e.event_id: e for e in events}

    # Validator accuracy (against human consensus)
    human_consensus = {}
    for eid in common_ids:
        a1 = annotator_1[eid]
        a2 = annotator_2[eid]
        human_consensus[eid] = 1 if (a1 + a2) >= 1 else 0  # OR consensus

    validator_labels = {}
    for eid in common_ids:
        e = event_map[eid]
        validator_labels[eid] = 1 if e.label == SwitchLabel.BOUNDARY_SPECIFIC else 0

    # Accuracy
    correct = sum(
        1 for eid in common_ids
        if validator_labels[eid] == human_consensus[eid]
    )
    accuracy = correct / n

    # FP/FN rates
    fp = sum(
        1 for eid in common_ids
        if validator_labels[eid] == 1 and human_consensus[eid] == 0
    )
    fn = sum(
        1 for eid in common_ids
        if validator_labels[eid] == 0 and human_consensus[eid] == 1
    )
    n_positive = sum(human_consensus.values())
    n_negative = n - n_positive

    # Cohen's kappa (inter-annotator)
    a1_vals = [annotator_1[eid] for eid in common_ids]
    a2_vals = [annotator_2[eid] for eid in common_ids]
    kappa = _cohens_kappa(a1_vals, a2_vals)

    result = {
        "n_events": n,
        "validator_accuracy": round(accuracy, 4),
        "fp_rate": round(fp / n_negative, 4) if n_negative > 0 else 0.0,
        "fn_rate": round(fn / n_positive, 4) if n_positive > 0 else 0.0,
        "inter_annotator_kappa": round(kappa, 4),
        "kappa_passed": kappa > 0.7,
        "accuracy_passed": accuracy > 0.9,
    }

    logger.info(
        f"Human calibration: accuracy={accuracy:.2%}, kappa={kappa:.4f} — "
        f"{'PASSED' if result['kappa_passed'] and result['accuracy_passed'] else 'NEEDS REVIEW'}"
    )

    return result


def _cohens_kappa(a: List[int], b: List[int]) -> float:
    """Compute Cohen's kappa between two raters."""
    n = len(a)
    if n == 0:
        return 0.0

    # Observed agreement
    agree = sum(1 for i in range(n) if a[i] == b[i])
    po = agree / n

    # Expected agreement
    a_pos = sum(a) / n
    b_pos = sum(b) / n
    pe = a_pos * b_pos + (1 - a_pos) * (1 - b_pos)

    if pe == 1.0:
        return 1.0

    return (po - pe) / (1 - pe)


# ---------------------------------------------------------------------------
# Benchmark Statistics (Table 1)
# ---------------------------------------------------------------------------

def benchmark_statistics(events: List[SwitchEvent]) -> Dict:
    """Generate Table 1: benchmark statistics."""
    n_events = len(events)
    n_tasks = len(set(e.task_id for e in events))

    fault_dist = Counter(e.fault_type.value for e in events)
    severity_dist = Counter(e.fault_severity.value for e in events)
    label_dist = Counter(e.label.value for e in events)

    # Replay determinism: check agreement across 3 runs per branch
    determinism_rates = []
    for e in events:
        for branch in [e.hybrid_result, e.api_only_result, e.gui_only_result]:
            if branch and len(branch.run_outcomes) == 3:
                outcomes = [o.value for o in branch.run_outcomes]
                determinism_rates.append(len(set(outcomes)) == 1)

    replay_det = np.mean(determinism_rates) if determinism_rates else 0.0

    return {
        "n_tasks": n_tasks,
        "n_events": n_events,
        "n_conditions": n_events,  # approx
        "fault_distribution": dict(fault_dist),
        "severity_distribution": dict(severity_dist),
        "label_distribution": dict(label_dist),
        "replay_determinism_rate": round(replay_det, 4),
    }


# ---------------------------------------------------------------------------
# Results Summary
# ---------------------------------------------------------------------------

def generate_results_summary(
    prevalence: Dict,
    detector_indist: Dict,
    detector_transfer: Optional[Dict] = None,
    recovery: Optional[Dict] = None,
    calibration: Optional[Dict] = None,
    benchmark_stats: Optional[Dict] = None,
) -> str:
    """Generate a Markdown results summary."""
    lines = [
        "# HybridStress Experiment Results",
        "",
        f"**Date**: {__import__('time').strftime('%Y-%m-%d')}",
        "",
    ]

    # Benchmark stats
    if benchmark_stats:
        lines += [
            "## Table 1: Benchmark Statistics",
            f"- Tasks: {benchmark_stats['n_tasks']}",
            f"- Switch events: {benchmark_stats['n_events']}",
            f"- Replay determinism: {benchmark_stats['replay_determinism_rate']:.1%}",
            "",
        ]

    # C1: Prevalence
    lines += [
        "## C1: Boundary Failure Prevalence",
        f"- Total events: {prevalence['total_events']}",
        f"- Total failures: {prevalence['total_failures']}",
        f"- Boundary-specific: {prevalence['boundary_specific_count']} "
        f"({prevalence['prevalence_pct']:.1f}%)",
        f"- **C1 {'PASSED' if prevalence['c1_passed'] else 'FAILED'}** "
        f"(threshold: >15%)",
        "",
    ]

    # C2: Detector comparison
    lines += ["## Detector Comparison (In-Distribution)", ""]
    if "detectors" in detector_indist:
        lines.append(
            "| Detector | AUPRC | AUROC | ECE | Brier | FAR |"
        )
        lines.append("|----------|-------|-------|-----|-------|-----|")
        for name, m in detector_indist["detectors"].items():
            if "error" not in m:
                lines.append(
                    f"| {name} | {m['auprc']:.4f} | {m['auroc']:.4f} | "
                    f"{m['ece']:.4f} | {m['brier']:.4f} | {m['false_alarm_rate']:.4f} |"
                )
        lines.append("")

    # Transfer
    if detector_transfer and "c2_results" in detector_transfer:
        c2 = detector_transfer["c2_results"]
        lines += [
            "## C2: Transfer to Natural Traces",
            f"- CMV AUPRC: {c2['cmv_auprc']:.4f}",
            f"- VLM AUPRC: {c2['vlm_auprc']:.4f}",
            f"- Gap: {c2['gap_pct']:.1f}%",
            f"- **C2 {'PASSED' if c2['c2_overall_passed'] else 'FAILED'}**",
            "",
        ]

    # Recovery
    if recovery:
        rates = recovery["success_rates"]
        delta = recovery["cmv_vs_baseline"]
        lines += [
            "## C3: Recovery Utility (Exploratory)",
            f"- Baseline: {rates['baseline']:.2%}",
            f"- Blind retry: {rates['blind_retry']:.2%}",
            f"- CMV recovery: {rates['cmv_recovery']:.2%}",
            f"- Delta: {delta['mean_delta']:.2%} "
            f"[{delta['ci_lower']:.2%}, {delta['ci_upper']:.2%}]",
            "",
        ]

    # Calibration
    if calibration and "error" not in calibration:
        lines += [
            "## Human Calibration",
            f"- Validator accuracy: {calibration['validator_accuracy']:.2%}",
            f"- Inter-annotator κ: {calibration['inter_annotator_kappa']:.4f}",
            f"- FP rate: {calibration['fp_rate']:.2%}",
            f"- FN rate: {calibration['fn_rate']:.2%}",
            "",
        ]

    return "\n".join(lines)
