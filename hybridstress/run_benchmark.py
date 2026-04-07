"""
HybridStress Benchmark Runner
===============================

Entry point for all experiment stages:

M0 (sanity):   Run 3 pilot tasks to verify infrastructure
M1 (full):     Run all 20 tasks with fault injection + 3-branch replay
M2 (detector): Train VLM judge + CMV, evaluate in-distribution
M3 (transfer): Collect natural traces, evaluate transfer (C2)
M4 (utility):  Recovery evaluation (C3, exploratory)

Usage:
    python -m hybridstress.run_benchmark --stage sanity --output hybridstress_sanity/
    python -m hybridstress.run_benchmark --stage full --output benchmark_data/
    python -m hybridstress.run_benchmark --stage detector --data benchmark_data/ --output models/
    python -m hybridstress.run_benchmark --stage transfer --data benchmark_data/ --output transfer_data/
    python -m hybridstress.run_benchmark --stage utility --data benchmark_data/ --output utility_data/
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from .data_types import (
    FaultConfig, FaultType, FaultSeverity, SwitchEvent,
    SwitchLabel, Predicate, BranchResult, BranchOutcome,
    generate_all_conditions,
)
from .fault_injector import FaultInjector
from .validators import CompositeValidator
from .task_definitions import BENCHMARK_TASKS, PILOT_TASKS, TASK_BY_ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hybridstress")


# ============================================================================
# M0: Sanity Check
# ============================================================================

def run_sanity_check(output_dir: Path) -> Dict:
    """
    M0: Verify infrastructure on 3 pilot tasks (local-only checks).

    Checks:
    1. Data structure integrity
    2. Fault injector engine
    3. Condition generation
    4. Label decision table exhaustiveness
    """
    logger.info("=" * 60)
    logger.info("HybridStress Sanity Check (M0)")
    logger.info("=" * 60)

    results = {
        "stage": "sanity",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": {},
    }

    # Check 1: Data structure integrity
    logger.info("[1/4] Testing data structure integrity...")
    try:
        event = SwitchEvent(
            task_id="test",
            step_index=0,
            action="test_action",
            postconditions=[Predicate("cart", "contains", "item")],
        )
        event.hybrid_result = BranchResult(
            mode="hybrid",
            run_outcomes=[BranchOutcome.FAILURE] * 3,
            majority_outcome=BranchOutcome.FAILURE,
        )
        event.api_only_result = BranchResult(
            mode="api_only",
            run_outcomes=[BranchOutcome.SUCCESS] * 3,
            majority_outcome=BranchOutcome.SUCCESS,
        )
        event.gui_only_result = BranchResult(
            mode="gui_only",
            run_outcomes=[BranchOutcome.SUCCESS] * 3,
            majority_outcome=BranchOutcome.SUCCESS,
        )
        event.label = event.derive_label()
        assert event.label == SwitchLabel.BOUNDARY_SPECIFIC

        # Test serialization round-trip
        event_path = output_dir / "test_event.json"
        event.save(event_path)
        loaded = SwitchEvent.load(event_path)
        assert loaded.event_id == event.event_id
        assert loaded.label == SwitchLabel.BOUNDARY_SPECIFIC

        results["checks"]["data_structures"] = "PASS"
        logger.info("  PASS: Data structures OK")
    except Exception as e:
        results["checks"]["data_structures"] = f"FAIL: {e}"
        logger.error(f"  FAIL: Data structures: {e}")

    # Check 2: Fault injection engine
    logger.info("[2/4] Testing fault injection engine...")
    try:
        injector = FaultInjector()
        assert not injector.is_active()

        config = FaultConfig.from_type_severity(FaultType.STALE_OBSERVATION, FaultSeverity.MODERATE)
        injector.activate(config)
        assert injector.is_active()
        assert config.stale_delay_ms == 800

        config2 = FaultConfig.from_type_severity(FaultType.PHANTOM_ACK, FaultSeverity.SEVERE)
        assert config2.ack_intercept is True

        injector.intercept_screenshot("screenshot_1")
        time.sleep(0.1)
        injector.intercept_screenshot("screenshot_2")

        injector.deactivate()
        assert not injector.is_active()

        results["checks"]["fault_injector"] = "PASS"
        logger.info("  PASS: Fault injector OK")
    except Exception as e:
        results["checks"]["fault_injector"] = f"FAIL: {e}"
        logger.error(f"  FAIL: Fault injector: {e}")

    # Check 3: Condition generation
    logger.info("[3/4] Testing condition generation...")
    try:
        conditions = generate_all_conditions("test_task")
        assert len(conditions) == 10
        assert conditions[0] == (FaultType.NONE, FaultSeverity.NONE)
        results["checks"]["conditions"] = "PASS"
        logger.info(f"  PASS: Generated {len(conditions)} conditions per task")
    except Exception as e:
        results["checks"]["conditions"] = f"FAIL: {e}"
        logger.error(f"  FAIL: Condition generation: {e}")

    # Check 4: Label decision table exhaustiveness
    logger.info("[4/4] Testing label decision table...")
    try:
        test_cases = [
            (True, True, True, SwitchLabel.CONSISTENT_PASS),
            (True, False, True, SwitchLabel.CONSISTENT_PASS),
            (True, True, False, SwitchLabel.CONSISTENT_PASS),
            (False, True, True, SwitchLabel.BOUNDARY_SPECIFIC),
            (False, False, True, SwitchLabel.GUI_PREFERRED),
            (False, True, False, SwitchLabel.API_PREFERRED),
            (False, False, False, SwitchLabel.UNIVERSALLY_HARD),
            (True, False, False, SwitchLabel.HYBRID_ADVANTAGE),
        ]
        for h, a, g, expected in test_cases:
            event = SwitchEvent()
            event.hybrid_result = BranchResult(
                mode="hybrid",
                run_outcomes=[BranchOutcome.SUCCESS if h else BranchOutcome.FAILURE] * 3,
                majority_outcome=BranchOutcome.SUCCESS if h else BranchOutcome.FAILURE,
            )
            event.api_only_result = BranchResult(
                mode="api_only",
                run_outcomes=[BranchOutcome.SUCCESS if a else BranchOutcome.FAILURE] * 3,
                majority_outcome=BranchOutcome.SUCCESS if a else BranchOutcome.FAILURE,
            )
            event.gui_only_result = BranchResult(
                mode="gui_only",
                run_outcomes=[BranchOutcome.SUCCESS if g else BranchOutcome.FAILURE] * 3,
                majority_outcome=BranchOutcome.SUCCESS if g else BranchOutcome.FAILURE,
            )
            actual = event.derive_label()
            assert actual == expected, f"({h},{a},{g}): expected {expected}, got {actual}"

        results["checks"]["decision_table"] = "PASS"
        logger.info("  PASS: All 8 decision table entries verified")
    except Exception as e:
        results["checks"]["decision_table"] = f"FAIL: {e}"
        logger.error(f"  FAIL: Decision table: {e}")

    # Summary
    all_passed = all(v == "PASS" for v in results["checks"].values())
    results["overall"] = "PASS" if all_passed else "FAIL"

    results_path = output_dir / "sanity_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info("=" * 60)
    logger.info(f"SANITY CHECK {'PASSED' if all_passed else 'FAILED'}")
    logger.info(f"Results saved to: {results_path}")
    logger.info("=" * 60)

    return results


# ============================================================================
# M0-cockpit: Cockpit Sanity Check
# ============================================================================

def run_cockpit_sanity_check(output_dir: Path) -> Dict:
    """
    M0 for cockpit backend: Verify cockpit server, API, snapshots, validators.

    Checks:
    1. Data structure integrity (same as android)
    2. Fault injector engine (same as android)
    3. Cockpit server starts and responds
    4. API actions execute and modify state correctly
    5. Snapshot save/restore determinism
    6. Cockpit validators work against API state
    7. Task definitions are well-formed
    """
    logger.info("=" * 60)
    logger.info("HybridStress Cockpit Sanity Check (M0-cockpit)")
    logger.info("=" * 60)

    results = {
        "stage": "sanity_cockpit",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "checks": {},
    }

    # Check 1: Data structures (same as android sanity)
    logger.info("[1/7] Testing data structure integrity...")
    try:
        event = SwitchEvent(
            task_id="test",
            step_index=0,
            action="test_action",
            postconditions=[Predicate("cart", "contains", "item")],
        )
        event.hybrid_result = BranchResult(
            mode="hybrid",
            run_outcomes=[BranchOutcome.FAILURE] * 3,
            majority_outcome=BranchOutcome.FAILURE,
        )
        event.api_only_result = BranchResult(
            mode="api_only",
            run_outcomes=[BranchOutcome.SUCCESS] * 3,
            majority_outcome=BranchOutcome.SUCCESS,
        )
        event.gui_only_result = BranchResult(
            mode="gui_only",
            run_outcomes=[BranchOutcome.SUCCESS] * 3,
            majority_outcome=BranchOutcome.SUCCESS,
        )
        event.label = event.derive_label()
        assert event.label == SwitchLabel.BOUNDARY_SPECIFIC

        event_path = output_dir / "test_event.json"
        event.save(event_path)
        loaded = SwitchEvent.load(event_path)
        assert loaded.label == SwitchLabel.BOUNDARY_SPECIFIC

        results["checks"]["data_structures"] = "PASS"
        logger.info("  PASS: Data structures OK")
    except Exception as e:
        results["checks"]["data_structures"] = f"FAIL: {e}"
        logger.error(f"  FAIL: Data structures: {e}")

    # Check 2: Fault injector
    logger.info("[2/7] Testing fault injection engine...")
    try:
        injector = FaultInjector()
        assert not injector.is_active()
        config = FaultConfig.from_type_severity(FaultType.STALE_OBSERVATION, FaultSeverity.MODERATE)
        injector.activate(config)
        assert injector.is_active()
        assert config.stale_delay_ms == 800
        injector.deactivate()
        results["checks"]["fault_injector"] = "PASS"
        logger.info("  PASS: Fault injector OK")
    except Exception as e:
        results["checks"]["fault_injector"] = f"FAIL: {e}"
        logger.error(f"  FAIL: Fault injector: {e}")

    # Check 3: Cockpit server
    logger.info("[3/7] Starting cockpit server...")
    try:
        from cockpit.integration import start_cockpit_server, CockpitClient
        start_cockpit_server(port=8420)
        client = CockpitClient("http://localhost:8420")
        assert client.is_alive(), "Cockpit server not responding"
        state = client.get_state()
        assert "navigation" in state
        assert "media" in state
        assert "climate" in state
        assert "phone" in state
        assert "messages" in state
        assert "settings" in state
        assert "vehicle" in state
        results["checks"]["cockpit_server"] = "PASS"
        logger.info(f"  PASS: Cockpit server OK, {len(state)} subsystems")
    except Exception as e:
        results["checks"]["cockpit_server"] = f"FAIL: {e}"
        logger.error(f"  FAIL: Cockpit server: {e}")
        # Can't continue without server
        results["overall"] = "FAIL"
        _save_sanity(results, output_dir)
        return results

    # Check 4: API actions
    logger.info("[4/7] Testing API actions...")
    try:
        # Reset state first
        client.reset()

        # Test navigation
        resp = client.post("/api/navigation/set_destination",
                          {"name": "机场", "address": "北京首都国际机场"})
        assert resp.get("status") == "ok", f"Navigation API failed: {resp}"

        # Test media
        resp = client.post("/api/media/play")
        assert resp.get("status") == "ok", f"Media API failed: {resp}"

        # Test climate
        resp = client.post("/api/climate/temperature",
                          {"zone": "driver", "temperature": 22.0})
        assert resp.get("status") == "ok", f"Climate API failed: {resp}"

        # Test messages
        resp = client.post("/api/messages/send",
                          {"contact": "张三", "text": "测试消息"})
        assert resp.get("status") == "ok", f"Messages API failed: {resp}"

        # Verify state changed
        state = client.get_state()
        assert "机场" in json.dumps(state, ensure_ascii=False), "Navigation state not updated"
        assert state["media"]["playing"] is True, "Media state not updated"
        assert state["climate"]["temperature_driver"] == 22.0, "Climate state not updated"

        results["checks"]["api_actions"] = "PASS"
        logger.info("  PASS: API actions OK (4 subsystems verified)")
    except Exception as e:
        results["checks"]["api_actions"] = f"FAIL: {e}"
        logger.error(f"  FAIL: API actions: {e}")

    # Check 5: Snapshot save/restore
    logger.info("[5/7] Testing snapshot determinism...")
    try:
        # Save current state
        client.save_snapshot("sanity_test")

        # Modify state
        client.post("/api/climate/temperature",
                    {"zone": "driver", "temperature": 30.0})
        state_after = client.get_state()
        assert state_after["climate"]["temperature_driver"] == 30.0

        # Restore snapshot
        client.restore_snapshot("sanity_test")
        state_restored = client.get_state()
        assert state_restored["climate"]["temperature_driver"] == 22.0, \
            f"Snapshot restore failed: temp={state_restored['climate']['temperature_driver']}"

        results["checks"]["snapshot_determinism"] = "PASS"
        logger.info("  PASS: Snapshot save/restore is deterministic")
    except Exception as e:
        results["checks"]["snapshot_determinism"] = f"FAIL: {e}"
        logger.error(f"  FAIL: Snapshot determinism: {e}")

    # Check 6: Validators
    logger.info("[6/7] Testing cockpit validators...")
    try:
        from cockpit.validators import CockpitCompositeValidator

        client.reset()
        client.post("/api/media/play")

        validator = CockpitCompositeValidator(cockpit_url="http://localhost:8420")
        # Test positive predicate
        outcome_ok, details_ok = validator.validate_all([
            Predicate("playing", "value_is", "true"),
        ])
        assert outcome_ok == BranchOutcome.SUCCESS, f"Positive predicate failed: {details_ok}"

        # Test negative predicate
        outcome_neg, details_neg = validator.validate_all([
            Predicate("playing", "value_is", "false"),
        ])
        assert outcome_neg == BranchOutcome.FAILURE, f"Negative predicate should fail: {details_neg}"

        # Test contains
        outcome_c, _ = validator.validate_all([
            Predicate("current_track", "contains", "夜曲"),
        ])
        assert outcome_c == BranchOutcome.SUCCESS, "Contains predicate failed"

        # Test not_contains
        outcome_nc, _ = validator.validate_all([
            Predicate("current_track", "not_contains", "不存在的歌"),
        ])
        assert outcome_nc == BranchOutcome.SUCCESS, "Not_contains predicate failed"

        results["checks"]["validators"] = "PASS"
        logger.info("  PASS: Cockpit validators OK (4 relations tested)")
    except Exception as e:
        results["checks"]["validators"] = f"FAIL: {e}"
        logger.error(f"  FAIL: Validators: {e}")

    # Check 7: Task definitions
    logger.info("[7/7] Testing cockpit task definitions...")
    try:
        from cockpit.task_definitions import COCKPIT_TASKS, COCKPIT_PILOT_TASKS

        assert len(COCKPIT_TASKS) == 20, f"Expected 20 tasks, got {len(COCKPIT_TASKS)}"
        assert len(COCKPIT_PILOT_TASKS) == 3, f"Expected 3 pilot tasks, got {len(COCKPIT_PILOT_TASKS)}"

        for task in COCKPIT_TASKS:
            assert task["task_id"], f"Task missing task_id"
            assert task["postconditions"], f"Task {task['task_id']} has no postconditions"
            assert task["api_actions"], f"Task {task['task_id']} has no api_actions"

        # Run all 3 pilot tasks via API and validate
        client.reset()
        pilot_pass = 0
        for task in COCKPIT_PILOT_TASKS:
            client.reset()
            for action in task["api_actions"]:
                client.post(action["path"], action.get("body", {}))

            validator = CockpitCompositeValidator(cockpit_url="http://localhost:8420")
            outcome, details = validator.validate_all(task["postconditions"])
            status = "PASS" if outcome == BranchOutcome.SUCCESS else "FAIL"
            logger.info(f"    Pilot {task['task_id']}: {status}")
            if outcome == BranchOutcome.SUCCESS:
                pilot_pass += 1

        results["checks"]["task_definitions"] = f"PASS ({pilot_pass}/3 pilots pass)"
        logger.info(f"  PASS: {len(COCKPIT_TASKS)} tasks well-formed, {pilot_pass}/3 pilots pass")
    except Exception as e:
        results["checks"]["task_definitions"] = f"FAIL: {e}"
        logger.error(f"  FAIL: Task definitions: {e}")

    # Summary
    all_passed = all("PASS" in str(v) for v in results["checks"].values())
    results["overall"] = "PASS" if all_passed else "FAIL"
    _save_sanity(results, output_dir)

    logger.info("=" * 60)
    logger.info(f"COCKPIT SANITY CHECK {'PASSED' if all_passed else 'FAILED'}")
    for check, status in results["checks"].items():
        logger.info(f"  {check}: {status}")
    logger.info(f"Results saved to: {output_dir / 'sanity_results.json'}")
    logger.info("=" * 60)

    return results


def _save_sanity(results: Dict, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "sanity_results.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


# ============================================================================
# M1: Full Benchmark Construction
# ============================================================================

def run_full_benchmark(
    output_dir: Path,
    device_id: str = "192.168.50.174:5555",
    n_tasks: int = 20,
    seed: int = 42,
    backend: str = "android",
) -> Dict:
    """
    M1: Full benchmark construction.
    - Run 20 tasks × 10 conditions = 200 runs
    - Extract ~300 switch events
    - Execute 3-branch replay → derive labels
    - Run prevalence analysis (C1)

    backend: "android" (physical/emulator via ADB) or "cockpit" (virtual IVI)
    """
    logger.info("=" * 60)
    logger.info(f"HybridStress Full Benchmark (M1) — {n_tasks} tasks, backend={backend}")
    logger.info("=" * 60)

    # Reproducibility seeding
    import random
    import numpy as np
    random.seed(seed)
    np.random.seed(seed)

    output_dir.mkdir(parents=True, exist_ok=True)
    events_dir = output_dir / "events"
    events_dir.mkdir(exist_ok=True)

    # Initialize components based on backend
    injector = FaultInjector()

    if backend == "cockpit":
        from cockpit.integration import (
            CockpitExecutor, CockpitReplayEngine, start_cockpit_server, CockpitClient,
        )
        from cockpit.validators import CockpitCompositeValidator
        from cockpit.task_definitions import COCKPIT_TASKS

        cockpit_url = "http://localhost:8420"
        start_cockpit_server(port=8420)

        executor = CockpitExecutor(cockpit_url=cockpit_url, injector=injector)
        validator = CockpitCompositeValidator(cockpit_url=cockpit_url)
        replay = CockpitReplayEngine(
            executor=executor,
            validator=validator,
            output_dir=output_dir,
            cockpit_url=cockpit_url,
        )
        tasks = COCKPIT_TASKS[:n_tasks]

        # Save initial snapshot
        client = CockpitClient(cockpit_url)
        client.save_snapshot("initial")
    else:
        from .gelab_integration import (
            GelabExecutor, ReplayEngine,
            capture_screenshot_adb, save_emulator_snapshot,
        )
        executor = GelabExecutor(device_id=device_id, injector=injector)
        validator = CompositeValidator(adb_serial=device_id)
        replay = ReplayEngine(
            executor=executor,
            validator=validator,
            output_dir=output_dir,
            device_id=device_id,
        )
        tasks = BENCHMARK_TASKS[:n_tasks]
    all_events: List[SwitchEvent] = []
    run_log = {
        "stage": "full",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_tasks": len(tasks),
        "device_id": device_id,
        "events": [],
    }

    for task_idx, task in enumerate(tasks):
        task_id = task["task_id"]
        conditions = generate_all_conditions(task_id)

        logger.info(f"\n[Task {task_idx+1}/{len(tasks)}] {task_id}: {task['description']}")
        logger.info(f"  Conditions: {len(conditions)}")

        for cond_idx, (fault_type, fault_severity) in enumerate(conditions):
            fault_config = FaultConfig.from_type_severity(fault_type, fault_severity)
            condition_name = f"{fault_type.value}_{fault_severity.value}"

            logger.info(f"  [{cond_idx+1}/{len(conditions)}] Condition: {condition_name}")

            # CRITICAL: Restore clean initial state before each condition
            # to ensure independence (prevents toggle contamination).
            if backend == "cockpit":
                client.restore_snapshot("initial")
            # Save snapshot at this clean starting point
            snapshot_id = f"switchpoint_{task_id}_{cond_idx}"
            if backend == "cockpit":
                client.save_snapshot(snapshot_id)
            else:
                save_emulator_snapshot(snapshot_id, device_id)

            try:
                # Run 3-branch replay
                event = replay.replay_switch_event(
                    task=task,
                    snapshot_id=snapshot_id,
                    step_index=cond_idx,
                    fault_config=fault_config if fault_type != FaultType.NONE else None,
                )
                all_events.append(event)
                run_log["events"].append({
                    "event_id": event.event_id,
                    "task_id": task_id,
                    "condition": condition_name,
                    "label": event.label.value,
                })
            except Exception as e:
                logger.error(f"  FAILED: {task_id}/{condition_name}: {e}")
                run_log["events"].append({
                    "task_id": task_id,
                    "condition": condition_name,
                    "error": str(e),
                })

    # Save run log
    with open(output_dir / "run_log.json", "w") as f:
        json.dump(run_log, f, indent=2, ensure_ascii=False)

    # Run prevalence analysis (C1)
    from .evaluator import prevalence_analysis, benchmark_statistics
    prevalence = prevalence_analysis(all_events)
    stats = benchmark_statistics(all_events)

    with open(output_dir / "prevalence_results.json", "w") as f:
        json.dump(prevalence, f, indent=2)
    with open(output_dir / "benchmark_stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    logger.info("=" * 60)
    logger.info(f"M1 COMPLETE: {len(all_events)} events collected")
    logger.info(f"C1 prevalence: {prevalence['prevalence_pct']:.1f}%")
    logger.info("=" * 60)

    return {
        "n_events": len(all_events),
        "prevalence": prevalence,
        "stats": stats,
    }


# ============================================================================
# M2: Detector Training & Evaluation
# ============================================================================

def run_detector_stage(
    data_dir: Path,
    output_dir: Path,
    device: str = "cuda",
    epochs: int = 50,
    lr: float = 1e-4,
    seed: int = 42,
) -> Dict:
    """
    M2: Train CMV and evaluate in-distribution.
    1. Run VLM judge on all events (~4 GPU-hours)
    2. Train CMV with BCE + KD (~2 GPU-hours)
    3. Evaluate all detectors on validation split
    """
    from .cmv_model import CMVModel, SigLIPFeatureExtractor, PostconditionTokenizer
    from .cmv_trainer import (
        CMVTrainer, HybridStressDataset,
        load_events_from_dir, load_vlm_scores, stratified_split,
    )
    from .vlm_judge import VLMJudge
    from .evaluator import detector_comparison

    logger.info("=" * 60)
    logger.info("HybridStress Detector Stage (M2)")
    logger.info("=" * 60)

    # Reproducibility seeding
    import random
    import numpy as np
    random.seed(seed)
    np.random.seed(seed)
    import torch as _torch
    _torch.manual_seed(seed)
    if _torch.cuda.is_available():
        _torch.cuda.manual_seed_all(seed)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load events and exclude PARTIAL_FAIL (infrastructure errors — unreliable labels)
    events = load_events_from_dir(data_dir / "events")
    events = [e for e in events if e.label != SwitchLabel.PARTIAL_FAIL]
    logger.info(f"Loaded {len(events)} valid events (PARTIAL_FAIL excluded)")

    # Step 1: VLM judge inference
    vlm_scores_path = output_dir / "vlm_scores.json"
    if vlm_scores_path.exists():
        logger.info("VLM scores already exist, loading...")
        vlm_scores = load_vlm_scores(vlm_scores_path)
    else:
        logger.info("Running VLM judge inference...")
        judge = VLMJudge(device=device)
        vlm_scores = judge.batch_judge(events)
        with open(vlm_scores_path, "w") as f:
            json.dump(vlm_scores, f, indent=2)
        logger.info(f"VLM scores saved: {len(vlm_scores)} events")

    # Step 2: Train CMV
    train_events, val_events = stratified_split(events)
    logger.info(f"Train: {len(train_events)}, Val: {len(val_events)}")

    feature_extractor = SigLIPFeatureExtractor(device=device)

    # Build tokenizer vocab on training split ONLY, then freeze
    tokenizer = PostconditionTokenizer()
    all_train_preds = [p for e in train_events for p in e.postconditions]
    tokenizer.build_vocab(all_train_preds)
    tokenizer.freeze()
    logger.info(f"Tokenizer vocab size: {len(tokenizer.vocab)}")

    train_dataset = HybridStressDataset(
        train_events, feature_extractor, tokenizer, vlm_scores
    )
    val_dataset = HybridStressDataset(
        val_events, feature_extractor, tokenizer, vlm_scores
    )

    model = CMVModel()
    cmv_dir = output_dir / "cmv"
    trainer = CMVTrainer(
        model=model,
        train_dataset=train_dataset,
        val_dataset=val_dataset,
        output_dir=cmv_dir,
        lr=lr,
        epochs=epochs,
        device=device,
    )
    training_metrics = trainer.train()
    tokenizer.save(cmv_dir / "tokenizer.json")

    # Step 3: Evaluate all detectors — reload calibrated best checkpoint
    import torch
    best_ckpt = torch.load(cmv_dir / "best.pt", map_location=device, weights_only=False)
    model.load_state_dict(best_ckpt["model_state_dict"])
    model = model.to(device).eval()

    # Get CMV predictions on val set
    cmv_scores = {}
    with torch.no_grad():
        for i, event in enumerate(val_events):
            pre_feat = feature_extractor.extract(event.pre_screenshot_path).unsqueeze(0)
            post_feat = feature_extractor.extract(event.post_screenshot_path).unsqueeze(0)
            text_tok, text_mask = tokenizer.tokenize(event.postconditions)
            text_tok = text_tok.unsqueeze(0).to(device)
            text_mask = text_mask.unsqueeze(0).to(device)

            prob = model.predict_proba(
                pre_feat.to(device), post_feat.to(device), text_tok, text_mask
            )
            cmv_scores[event.event_id] = float(prob.item())

    # Get baseline predictions
    from .cmv_model import FixedDelayBaseline, APIStatusBaseline
    fixed_delay = FixedDelayBaseline()
    fixed_scores = {
        e.event_id: fixed_delay.predict(e.pre_screenshot_path, e.post_screenshot_path)
        for e in val_events
    }
    # NOTE: api_status baseline requires stored API responses from execution logs.
    # Until those are collected, this baseline is omitted from comparison.

    # Evaluate (3 detectors: VLM judge, CMV, fixed delay)
    detector_scores = {
        "vlm_judge": {eid: vlm_scores.get(eid, 0.5) for eid in cmv_scores},
        "cmv": cmv_scores,
        "fixed_delay": fixed_scores,
    }
    comparison = detector_comparison(val_events, detector_scores, "in_distribution")

    with open(output_dir / "detector_comparison.json", "w") as f:
        json.dump(comparison, f, indent=2)

    logger.info("=" * 60)
    logger.info("M2 COMPLETE")
    logger.info(f"CMV AUPRC: {comparison['detectors']['cmv']['auprc']:.4f}")
    logger.info("=" * 60)

    return {
        "training": training_metrics,
        "comparison": comparison,
    }


# ============================================================================
# M3: Transfer Evaluation
# ============================================================================

def run_transfer_stage(
    data_dir: Path,
    output_dir: Path,
    device_id: str = "192.168.50.174:5555",
    device: str = "cuda",
) -> Dict:
    """
    M3: Collect natural traces and evaluate transfer (C2).
    1. Collect 200+ natural switch events from 10 held-out apps
    2. Evaluate CMV, VLM, and baselines on natural traces
    """
    from .task_definitions import HELD_OUT_APPS
    from .evaluator import transfer_evaluation
    from .cmv_model import CMVModel, SigLIPFeatureExtractor, PostconditionTokenizer, FixedDelayBaseline
    from .cmv_trainer import load_events_from_dir, load_vlm_scores
    from .vlm_judge import VLMJudge
    from .gelab_integration import (
        GelabExecutor, capture_screenshot_adb,
    )
    import torch

    logger.info("=" * 60)
    logger.info("HybridStress Transfer Stage (M3)")
    logger.info("=" * 60)

    output_dir.mkdir(parents=True, exist_ok=True)
    events_dir = output_dir / "events"
    events_dir.mkdir(exist_ok=True)

    # ── Step 1: Collect natural traces (no fault injection) ─────────────
    natural_events_path = output_dir / "natural_events"
    if natural_events_path.exists() and list(natural_events_path.glob("*.json")):
        logger.info("Natural trace events already exist, loading...")
        natural_events = load_events_from_dir(natural_events_path)
    else:
        natural_events_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Collecting natural traces from {len(HELD_OUT_APPS)} held-out apps...")

        executor = GelabExecutor(device_id=device_id)
        validator = CompositeValidator(adb_serial=device_id)
        natural_events = []

        for app_pkg in HELD_OUT_APPS:
            logger.info(f"  Collecting traces for: {app_pkg}")
            try:
                # Run agent naturally on each app (no injection)
                result = executor.execute_task_hybrid(
                    f"Open {app_pkg} and perform common tasks",
                    max_steps=15,
                    fault_config=None,
                )

                # Extract switch events from execution log
                if "result" in result and isinstance(result["result"], dict):
                    switch_log = result["result"].get("switch_events", [])
                    for i, sw in enumerate(switch_log):
                        from .data_types import SwitchEvent, Predicate, FaultType, FaultSeverity
                        event = SwitchEvent(
                            task_id=f"natural_{app_pkg.split('.')[-1]}_{i}",
                            step_index=i,
                            action=sw.get("action", ""),
                            postconditions=[
                                Predicate.from_dict(p) for p in sw.get("postconditions", [])
                            ],
                            fault_type=FaultType.NONE,
                            fault_severity=FaultSeverity.NONE,
                        )
                        if "pre_screenshot" in sw:
                            event.pre_screenshot_path = sw["pre_screenshot"]
                        if "post_screenshot" in sw:
                            event.post_screenshot_path = sw["post_screenshot"]
                        natural_events.append(event)
                        event.save(natural_events_path / f"{event.event_id}.json")
            except Exception as e:
                logger.error(f"  Failed to collect from {app_pkg}: {e}")

        logger.info(f"Collected {len(natural_events)} natural switch events")

    if not natural_events:
        logger.warning("No natural events collected. M3 cannot proceed.")
        return {"status": "no_events", "n_events": 0}

    # ── Step 2: Load trained CMV model ──────────────────────────────────
    cmv_dir = data_dir / "detector" / "cmv"
    model_path = cmv_dir / "best.pt"
    tokenizer_path = cmv_dir / "tokenizer.json"

    if not model_path.exists():
        logger.error(f"CMV model not found at {model_path}. Run M2 first.")
        return {"status": "model_not_found"}

    model = CMVModel()
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(device).eval()

    tokenizer = PostconditionTokenizer.load(tokenizer_path)
    feature_extractor = SigLIPFeatureExtractor(device=device)

    # ── Step 3: Run detectors on natural traces ─────────────────────────
    # CMV predictions
    cmv_scores = {}
    with torch.no_grad():
        for event in natural_events:
            try:
                pre_feat = feature_extractor.extract(event.pre_screenshot_path).unsqueeze(0)
                post_feat = feature_extractor.extract(event.post_screenshot_path).unsqueeze(0)
                text_tok, text_mask = tokenizer.tokenize(event.postconditions)
                text_tok = text_tok.unsqueeze(0).to(device)
                text_mask = text_mask.unsqueeze(0).to(device)
                prob = model.predict_proba(
                    pre_feat.to(device), post_feat.to(device), text_tok, text_mask
                )
                cmv_scores[event.event_id] = float(prob.item())
            except Exception as e:
                logger.warning(f"CMV failed on {event.event_id}: {e}")
                cmv_scores[event.event_id] = 0.5

    # VLM judge predictions
    vlm_scores_path = output_dir / "vlm_natural_scores.json"
    if vlm_scores_path.exists():
        vlm_scores = load_vlm_scores(vlm_scores_path)
    else:
        judge = VLMJudge(device=device)
        vlm_scores = judge.batch_judge(natural_events)
        with open(vlm_scores_path, "w") as f:
            json.dump(vlm_scores, f, indent=2)

    # Fixed-delay baseline
    fixed_delay = FixedDelayBaseline()
    fixed_scores = {}
    for e in natural_events:
        try:
            fixed_scores[e.event_id] = fixed_delay.predict(
                e.pre_screenshot_path, e.post_screenshot_path
            )
        except Exception:
            fixed_scores[e.event_id] = 0.5

    # ── Step 4: Evaluate transfer (C2) ──────────────────────────────────
    detector_scores = {
        "vlm_judge": vlm_scores,
        "cmv": cmv_scores,
        "fixed_delay": fixed_scores,
    }

    # Load human annotations — REQUIRED for valid transfer evaluation.
    # Without ground truth labels, metrics are meaningless.
    human_path = output_dir / "human_annotations.json"
    human_annotations = None
    if human_path.exists():
        with open(human_path) as f:
            human_annotations = json.load(f)
        logger.info(f"Loaded {len(human_annotations)} human annotations")
    else:
        logger.warning(
            "human_annotations.json not found. Transfer evaluation will use "
            "replay-based labels where available, but results may be unreliable. "
            "Place human_annotations.json in the output directory for valid C2 evaluation."
        )

    # Check that we have SOME ground truth (either from replay or human annotation)
    events_with_labels = [
        e for e in natural_events
        if (human_annotations and e.event_id in human_annotations)
        or (e.hybrid_result and e.api_only_result and e.gui_only_result)
    ]
    if not events_with_labels:
        logger.error(
            "No ground truth available for transfer evaluation. "
            "Provide human_annotations.json or ensure replay-based labels exist."
        )
        return {"status": "no_ground_truth", "n_events": len(natural_events)}

    comparison = transfer_evaluation(events_with_labels, detector_scores, human_annotations)

    with open(output_dir / "transfer_results.json", "w") as f:
        json.dump(comparison, f, indent=2)

    c2 = comparison.get("c2_results", {})
    logger.info("=" * 60)
    logger.info("M3 COMPLETE")
    logger.info(
        f"C2: CMV AUPRC={c2.get('cmv_auprc', 0):.4f}, "
        f"gap={c2.get('gap_pct', 0):.1f}% — "
        f"{'PASSED' if c2.get('c2_overall_passed') else 'FAILED'}"
    )
    logger.info("=" * 60)

    return {
        "n_natural_events": len(natural_events),
        "transfer": comparison,
    }


# ============================================================================
# M4: Recovery Utility
# ============================================================================

def run_utility_stage(
    data_dir: Path,
    output_dir: Path,
    device_id: str = "192.168.50.174:5555",
    device: str = "cuda",
) -> Dict:
    """
    M4: Recovery evaluation (C3, exploratory).
    Compare baseline vs blind-retry vs CMV-triggered recovery on 20 tasks.
    """
    from .evaluator import recovery_evaluation
    from .cmv_model import CMVModel, SigLIPFeatureExtractor, PostconditionTokenizer
    from .recovery import RecoveryProtocol
    from .gelab_integration import GelabExecutor, capture_screenshot_adb
    import torch

    logger.info("=" * 60)
    logger.info("HybridStress Utility Stage (M4)")
    logger.info("=" * 60)

    output_dir.mkdir(parents=True, exist_ok=True)
    tasks = BENCHMARK_TASKS

    # Load trained CMV model
    cmv_dir = data_dir / "detector" / "cmv"
    model_path = cmv_dir / "best.pt"
    tokenizer_path = cmv_dir / "tokenizer.json"

    if not model_path.exists():
        logger.error(f"CMV model not found at {model_path}. Run M2 first.")
        return {"status": "model_not_found"}

    model = CMVModel()
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(device).eval()

    tokenizer = PostconditionTokenizer.load(tokenizer_path)
    feature_extractor = SigLIPFeatureExtractor(device=device)

    executor = GelabExecutor(device_id=device_id)
    validator = CompositeValidator(adb_serial=device_id)
    recovery = RecoveryProtocol(validator=validator)

    baseline_results: Dict[str, bool] = {}
    blind_retry_results: Dict[str, bool] = {}
    cmv_recovery_results: Dict[str, bool] = {}

    for task_idx, task in enumerate(tasks):
        task_id = task["task_id"]
        logger.info(f"[{task_idx+1}/{len(tasks)}] {task_id}")

        # ── Run 1: Baseline (no verification) ───────────────────────
        try:
            result = executor.execute_task_hybrid(task["instruction"])
            validator.set_screenshot("")  # force fresh screenshot
            post_path = str(output_dir / f"baseline_{task_id}.png")
            capture_screenshot_adb(post_path, device_id)
            validator.set_screenshot(post_path)
            outcome, _ = validator.validate_all(task["postconditions"])
            baseline_results[task_id] = outcome.value == "success"
        except Exception as e:
            logger.error(f"  Baseline failed: {e}")
            baseline_results[task_id] = False

        # ── Run 2: Blind retry at every switch ──────────────────────
        try:
            result = executor.execute_task_hybrid(task["instruction"])
            # Blind retry: always retry via GUI after hybrid
            executor.execute_task_gui_only(task["instruction"], max_steps=5)
            post_path = str(output_dir / f"blind_{task_id}.png")
            capture_screenshot_adb(post_path, device_id)
            validator.set_screenshot(post_path)
            outcome, _ = validator.validate_all(task["postconditions"])
            blind_retry_results[task_id] = outcome.value == "success"
        except Exception as e:
            logger.error(f"  Blind retry failed: {e}")
            blind_retry_results[task_id] = False

        # ── Run 3: CMV-triggered recovery ───────────────────────────
        try:
            # Capture pre-switch screenshot BEFORE execution
            pre_path = str(output_dir / f"cmv_pre_{task_id}.png")
            capture_screenshot_adb(pre_path, device_id)

            result = executor.execute_task_hybrid(task["instruction"])

            # Capture post-switch screenshot AFTER execution
            post_path = str(output_dir / f"cmv_{task_id}.png")
            capture_screenshot_adb(post_path, device_id)
            validator.set_screenshot(post_path)

            # CMV scoring
            with torch.no_grad():
                pre_feat = feature_extractor.extract(pre_path).unsqueeze(0).to(device)
                post_feat = feature_extractor.extract(post_path).unsqueeze(0).to(device)
                text_tok, text_mask = tokenizer.tokenize(task["postconditions"])
                text_tok = text_tok.unsqueeze(0).to(device)
                text_mask = text_mask.unsqueeze(0).to(device)
                cmv_score = float(model.predict_proba(
                    pre_feat, post_feat, text_tok, text_mask
                ).item())

            # Recovery protocol
            rec_result = recovery.attempt_recovery(
                cmv_score=cmv_score,
                postconditions=task["postconditions"],
                action=task["instruction"],
                device_id=device_id,
                executor=executor,
            )

            # Final validation
            final_path = str(output_dir / f"cmv_final_{task_id}.png")
            capture_screenshot_adb(final_path, device_id)
            validator.set_screenshot(final_path)
            outcome, _ = validator.validate_all(task["postconditions"])
            cmv_recovery_results[task_id] = outcome.value == "success"
        except Exception as e:
            logger.error(f"  CMV recovery failed: {e}")
            cmv_recovery_results[task_id] = False

    # ── Evaluate recovery utility ───────────────────────────────────
    eval_result = recovery_evaluation(
        baseline_results, blind_retry_results, cmv_recovery_results
    )

    # Save results
    with open(output_dir / "utility_results.json", "w") as f:
        json.dump(eval_result, f, indent=2)
    with open(output_dir / "raw_results.json", "w") as f:
        json.dump({
            "baseline": baseline_results,
            "blind_retry": blind_retry_results,
            "cmv_recovery": cmv_recovery_results,
            "recovery_stats": recovery.get_stats(),
        }, f, indent=2)

    logger.info("=" * 60)
    logger.info("M4 COMPLETE")
    rates = eval_result["success_rates"]
    delta = eval_result["cmv_vs_baseline"]
    logger.info(
        f"C3: baseline={rates['baseline']:.2%}, cmv={rates['cmv_recovery']:.2%}, "
        f"delta={delta['mean_delta']:.2%} [{delta['ci_lower']:.2%}, {delta['ci_upper']:.2%}]"
    )
    logger.info("=" * 60)

    return eval_result


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="HybridStress Benchmark Runner")
    parser.add_argument(
        "--stage",
        choices=["sanity", "full", "detector", "transfer", "utility"],
        default="sanity",
        help="Which milestone to run",
    )
    parser.add_argument("--output", type=str, default="hybridstress_output",
                        help="Output directory")
    parser.add_argument("--data", type=str, default=None,
                        help="Input data directory (for detector/transfer/utility)")
    parser.add_argument("--tasks", type=int, default=20,
                        help="Number of tasks (3 for pilot, 20 for full)")
    parser.add_argument("--device_id", type=str, default="192.168.50.174:5555",
                        help="Android device ID")
    parser.add_argument("--gpu_device", type=str, default="cuda",
                        help="PyTorch device for model training")
    parser.add_argument("--epochs", type=int, default=50,
                        help="CMV training epochs")
    parser.add_argument("--lr", type=float, default=1e-4,
                        help="CMV learning rate")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--backend", choices=["android", "cockpit"], default="android",
                        help="Execution backend: android (ADB device) or cockpit (virtual IVI)")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.stage == "sanity":
        if args.backend == "cockpit":
            run_cockpit_sanity_check(output_dir)
        else:
            run_sanity_check(output_dir)

    elif args.stage == "full":
        run_full_benchmark(
            output_dir=output_dir,
            device_id=args.device_id,
            n_tasks=args.tasks,
            seed=args.seed,
            backend=args.backend,
        )

    elif args.stage == "detector":
        data_dir = Path(args.data) if args.data else output_dir
        run_detector_stage(
            data_dir=data_dir,
            output_dir=output_dir / "detector",
            device=args.gpu_device,
            epochs=args.epochs,
            lr=args.lr,
            seed=args.seed,
        )

    elif args.stage == "transfer":
        data_dir = Path(args.data) if args.data else output_dir
        run_transfer_stage(
            data_dir=data_dir,
            output_dir=output_dir / "transfer",
            device_id=args.device_id,
            device=args.gpu_device,
        )

    elif args.stage == "utility":
        data_dir = Path(args.data) if args.data else output_dir
        run_utility_stage(
            data_dir=data_dir,
            output_dir=output_dir / "utility",
            device_id=args.device_id,
            device=args.gpu_device,
        )


if __name__ == "__main__":
    main()
