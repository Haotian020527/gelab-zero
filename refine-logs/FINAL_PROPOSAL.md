# Research Proposal: HybridStress — An Event-Centric Benchmark for Modality-Boundary Failures in Hybrid API/GUI Agents

## Problem Anchor
- **Bottom-line problem**: Hybrid API/GUI agents (e.g., gelab-zero) fail silently at modality boundaries — when execution switches between API and GUI paths, application state can become inconsistent without any error signal, causing cascading failures.
- **Must-solve bottleneck**: No existing benchmark or method specifically detects, measures, or isolates modality-boundary failures from within-modality failures.
- **Non-goals**: (1) Building a better general GUI agent. (2) Improving single-modality performance. (3) Replacing MCP protocol. (4) End-to-end agent training. (5) New routing algorithms.
- **Constraints**: 1x RTX 4090; AndroidWorld; 4 weeks; NeurIPS 2025 Datasets & Benchmarks track.
- **Success condition**: (1) >15% of hybrid failures are boundary-specific. (2) VLM-distilled verifier transfers to natural traces (AUPRC > 0.7). (3) Recovery improves success (exploratory).

## Technical Gap

Hybrid API/GUI architectures assume that API calls and GUI actions produce equivalent, consistent application states. This assumption is systematically violated due to temporal skew, phantom acknowledgments, and state divergence at modality-switching boundaries.

Existing benchmarks (AndroidWorld, OSWorld, WebArena) measure end-to-end task success but cannot isolate where in the modality pipeline failures originate. MAS-FIRE injects faults into multi-agent systems but ignores cross-modal boundaries. GTArena tests GUI defects without cross-modal considerations. No benchmark provides counterfactual labeling that distinguishes boundary-specific failures from within-modality failures.

## Method Thesis

Modality-boundary failures are a distinct, common, and precisely measurable phenomenon. An event-centric benchmark with deterministic counterfactual 3-branch replay can diagnose them without model-in-the-loop labels. A VLM-distilled lightweight verifier can detect them at runtime with bounded latency overhead.

## Contribution Focus
- **Dominant (benchmark)**: HybridStress — 20 audited tasks, 3 fault types, ~300 switch events, deterministic counterfactual 3-branch labeling with exhaustive decision table
- **Reference detector**: CMV — Qwen2-VL-7B judge distilled to 10M-param detector with structured postcondition input
- **Exploratory utility study**: Fixed recovery protocol (re-screenshot → retry → GUI-only fallback)
- **Explicit non-contributions**: No routing algorithm, no architecture change, no RL training

## HybridStress Benchmark

### Unit of Analysis: SwitchEvent

```
SwitchEvent {
  // Core observation
  pre_screenshot: Image          # GUI state before modality switch
  post_screenshot: Image         # GUI state after modality switch
  action: str                    # action that crosses boundary
  postconditions: List[Predicate]  # structured (subject, relation, object) tuples
  
  // Checkpoint
  emulator_snapshot_id: str      # full Android emulator snapshot
  
  // Counterfactual labels (3-branch replay, majority of 3 runs per branch)
  hybrid_outcome: {success|failure}
  api_only_outcome: {success|failure}
  gui_only_outcome: {success|failure}
  
  // Derived label (from exhaustive decision table)
  label: {consistent_pass | BOUNDARY_SPECIFIC | gui_preferred | api_preferred |
          universally_hard | hybrid_advantage}
  
  // Fault metadata
  fault_type: {none | stale_observation | phantom_ack | state_rollback}
  fault_severity: {none | mild | moderate | severe}
}
```

### Postcondition Format

```
Predicate = (subject: str, relation: str, object: str)

Examples:
- ("cart", "contains", "Blue Widget x1")
- ("notification_bar", "shows", "Message sent successfully")
- ("current_screen", "is", "order_confirmation_page")
```

All predicates are chosen to be externally observable by at least one deterministic channel (ADB, UI XML, OCR).

### Label Decision Table

| Hybrid | API-only | GUI-only | Label | Interpretation |
|--------|----------|----------|-------|----------------|
| ✓ | ✓ | ✓ | consistent_pass | No failure |
| ✓ | ✗ | ✓ | consistent_pass | API broken, hybrid succeeded via fallback |
| ✓ | ✓ | ✗ | consistent_pass | GUI broken, hybrid succeeded via API |
| ✗ | ✓ | ✓ | **BOUNDARY_SPECIFIC** | **Hybrid failed where both unimodals succeed** |
| ✗ | ✗ | ✓ | gui_preferred | API+hybrid fail; GUI works |
| ✗ | ✓ | ✗ | api_preferred | GUI+hybrid fail; API works |
| ✗ | ✗ | ✗ | universally_hard | No modality succeeds |
| ✓ | ✗ | ✗ | hybrid_advantage | Hybrid uniquely succeeds |

Only **BOUNDARY_SPECIFIC** counts toward primary claim C1.

### Deterministic Branch Validators

Branch success/failure is determined by fully deterministic validators:

1. **ADB State Query**: `adb shell am stack list`, `adb shell content query`, `adb shell dumpsys activity`
2. **UI Hierarchy Check**: Parse UI XML dump for element existence/value
3. **Screenshot OCR**: Extract text from post-action screenshot, match against expected object

```
SUCCESS iff ALL postcondition predicates satisfied by ≥1 validator
FAILURE iff ANY postcondition predicate fails all three validators
```

No VLM or LLM is involved in benchmark label generation. Labels are deterministic and reproducible.

### Replay Isolation Protocol

1. Save full emulator snapshot at switch point: `emulator -snapshot save switchpoint_{task}_{step}`
2. For each branch (hybrid, API-only, GUI-only):
   a. Restore emulator from snapshot
   b. Reset MCP connection (deterministic reconnect)
   c. Execute remaining subtask in designated mode
   d. Run deterministic validators on result
   e. Repeat 3 times; majority vote determines outcome
3. All 3 branches start from identical emulator state.

### Fault Taxonomy (3 types)

| Fault Type | Description | Injection Method |
|------------|-------------|------------------|
| **Stale Observation** | Screenshot doesn't reflect actual state (timing-based) | Serve cached screenshot from t-k |
| **Phantom Acknowledgment** | API reports success before app completes | Intercept API response, inject success code |
| **State Rollback** | Action partially reverts at one modality but not other | Inject rollback at API without GUI refresh |

Injection: wrapper around `mcp_backend_implements.py`.

### Benchmark Scale
- 20 tasks × (1 clean + 3 faults × 3 severities) = 200 conditions
- ~1.5 switch events per condition → ~300 switch events
- Each event: 3 branches × 3 runs = 9 rollouts
- Total: ~2700 rollouts

### Human-Audited Calibration Study
- 50 randomly sampled switch events verified by 2 annotators
- Report validator accuracy, false positive/negative rates
- Report inter-annotator agreement (κ)
- Stratified by success/failure, app, task mix

## Cross-Modal Verifier (CMV) — Reference Detector

### Two-Tier Architecture

**Teacher (Qwen2-VL-7B)**: Prompted with (pre_screenshot, post_screenshot, postcondition predicates). Output: consistent/inconsistent with logit confidence.

**Student (CMV, 10M params)**: Frozen SigLIP ViT-B/16 encoders + postcondition text encoder → lightweight MLP scorer → binary output with temperature-scaled calibration.

### CMV Training Protocol (Exact)

1. **Benchmark labels**: Generated SOLELY by deterministic branch validators. No VLM/LLM involved.
2. **CMV training data**: HybridStress benchmark labels. Target = deterministic validator outcome.
3. **VLM teacher role**: ONLY for:
   - Auxiliary KD loss (weight 0.3) between CMV logits and VLM soft predictions
   - As a separate BASELINE in evaluation
4. **Primary loss**: Ground-truth BCE (weight 0.7) on deterministic labels
5. **The VLM NEVER generates benchmark labels or ground truth for any evaluation.**

## Recovery Protocol (Fixed)

When CMV detects inconsistency:
1. Re-capture screenshot (resolves transient timing issues)
2. If still inconsistent: retry action via GUI
3. If still inconsistent: escalate to GUI-only fallback

## Real-Trace Validation

- 200+ natural switch events from 10 held-out apps
- Ground truth: replay-based where checkpoints available; 2 human annotators with structured rubric where not
- VLM judge reported as separate baseline (NOT ground truth)
- Metrics: AUPRC, AUROC, ECE/Brier, false alarm rate
- Inter-annotator κ reported on all human-labeled events

## Claims & Evidence

| Claim | Type | Experiment | Metric | Success Criterion |
|-------|------|-----------|--------|-------------------|
| C1: Boundary failures are distinct and common | PRIMARY | HybridStress prevalence study | BOUNDARY_SPECIFIC rate | >15% of switch failures |
| C2: CMV detects them on natural traces | SUPPORTING | Transfer evaluation | AUPRC | >0.7, gap to VLM <10% |
| C3: Recovery helps | EXPLORATORY | Online utility study | Task success delta | Reported with paired bootstrap CIs |

## Failure Modes and Diagnostics
- **Validator false positive**: ADB/UI/OCR may incorrectly report success → mitigated by human calibration study
- **Replay non-determinism**: App behavior may vary between runs → mitigated by majority vote over 3 runs
- **Postcondition incompleteness**: Some state changes may not be externally observable → mitigated by selecting tasks with fully observable postconditions
- **CMV shortcut learning**: Detects injector artifacts → mitigated by held-out fault types in evaluation, real-trace transfer test

## Novelty and Elegance Argument
- **Closest work**: MAS-FIRE (multi-agent faults, not modality-boundary), GTArena (GUI defects, not cross-modal), VLM success detectors (single-modality)
- **Exact difference**: First event-centric benchmark with deterministic counterfactual labeling for modality-boundary failures in hybrid API/GUI agents
- **Why focused**: One benchmark + one reference detector. No routing, no RL, no architecture changes.

## Compute & Timeline
- HybridStress construction (emulator replay): ~80 GPU-hours
- VLM inference + CMV training: ~8 GPU-hours
- Natural trace collection: ~30 GPU-hours
- Evaluation: ~10 GPU-hours
- Total: ~128 GPU-hours ≈ 5.3 days on 1x RTX 4090
- Human annotation: 2 annotators × 250 events × 5 min = 42 person-hours
- Timeline: 4 weeks (benchmark: 1.5w, CMV: 0.5w, evaluation: 1w, writing: 1w)
