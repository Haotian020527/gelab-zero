# Round 2 Refinement

## Problem Anchor (unchanged)
[Same as Round 0/1]

## Anchor Check
- Original bottleneck: silent desynchronization at modality boundaries.
- Why revised method still addresses it: tighter labeling protocol directly measures boundary failures.
- Reviewer suggestions rejected as drift: none.

## Simplicity Check
- Dominant contribution: HybridStress benchmark with counterfactual event-level labeling.
- Components removed: collapsed Temporal Mismatch into Stale Screenshot (both are timing-related).
- Reviewer suggestions rejected as complexity: none.
- Why smallest adequate: one benchmark + one reference detector + one utility study.

## Changes Made

### 1. Explicit Label Derivation Table
**Reviewer said**: Need explicit decision table for branch outcomes → labels.
**Action**: Added complete decision table.

```
| Hybrid | API-only | GUI-only | Label             | Interpretation                              |
|--------|----------|----------|-------------------|---------------------------------------------|
| ✓      | ✓        | ✓        | consistent_pass   | No failure at all                           |
| ✓      | ✗        | ✓        | consistent_pass   | API broken but hybrid succeeded via fallback |
| ✓      | ✓        | ✗        | consistent_pass   | GUI broken but hybrid succeeded via API     |
| ✗      | ✓        | ✓        | BOUNDARY_SPECIFIC | Hybrid failed WHERE BOTH unimodals succeed  |
| ✗      | ✗        | ✓        | gui_preferred     | API+hybrid fail; GUI alone works            |
| ✗      | ✓        | ✗        | api_preferred     | GUI+hybrid fail; API alone works            |
| ✗      | ✗        | ✗        | universally_hard  | No modality succeeds                        |
| ✓      | ✗        | ✗        | hybrid_advantage  | Hybrid succeeds where unimodals fail        |
```

Only `BOUNDARY_SPECIFIC` row counts toward our primary claim. The table is exhaustive over all 2³ branch combinations.

### 2. Replay Isolation Protocol
**Reviewer said**: Define checkpoint, state reset, branch comparability.
**Action**: Added strict protocol.

**Checkpoint captures**: Full Android emulator snapshot via `emulator -snapshot save switchpoint_{task}_{step}`. This includes:
- Emulator RAM state + disk image
- App process state
- MCP server connection state (reconnected deterministically)

**Branch replay protocol**:
1. Restore emulator from snapshot
2. Reset MCP connection (deterministic reconnect)
3. Execute remaining subtask in designated mode (hybrid/API-only/GUI-only)
4. Record success/failure at subtask completion
5. Each branch runs 3 times; majority vote determines outcome

**Comparability guarantee**: All 3 branches start from identical emulator state. The only variable is the execution modality.

### 3. Structured Postcondition Format
**Reviewer said**: Use structured propositions, not free-form text.
**Action**: Postconditions are now typed predicate tuples.

```
Postcondition = List[Predicate]
Predicate = (subject: str, relation: str, object: str)

Examples:
- ("cart", "contains", "Blue Widget x1")
- ("notification_bar", "shows", "Message sent successfully")
- ("current_screen", "is", "order_confirmation_page")
- ("text_field_email", "value_is", "user@example.com")
```

LLM canonicalizes API response → predicate list. VLM verifier checks each predicate against post-switch screenshot.

### 4. Separate Ground Truth for Natural Traces
**Reviewer said**: VLM judge can't be both teacher and evaluator.
**Action**: Three-layer validation.

For HybridStress (synthetic): ground truth = counterfactual 3-branch replay (deterministic).
For CMV training: labels = HybridStress ground truth, NOT VLM judge.
For natural trace evaluation:
- Where replay is possible (saved checkpoints): use replay-based counterfactual labels
- Where replay is not possible: use 2 human annotators with structured rubric
- VLM judge is reported as a separate baseline, NOT as ground truth
- Inter-annotator agreement reported on ALL human-labeled events

### 5. Taxonomy Simplification
**Reviewer said**: Temporal Mismatch may need multi-snapshot; consider collapsing.
**Action**: Collapsed to 3 fault types.

| Fault Type | Description | Captures |
|------------|-------------|----------|
| **Stale Observation** | Pre/post screenshot does not reflect actual state | Stale Screenshot + Temporal Mismatch (both are timing-based) |
| **Phantom Acknowledgment** | API reports success before app completes | False success signals |
| **State Rollback** | Action partially or fully reverts at one modality but not the other | Partial rollback, undo asymmetry |

This is a cleaner 3-type taxonomy. Each type is distinguishable from a single (pre, post, postcondition) tuple without needing temporal sequences.

## Revised Proposal (Final)

# HybridStress: An Event-Centric Benchmark for Modality-Boundary Failures in Hybrid API/GUI Agents

## Problem Anchor
[Unchanged — boundary failures in hybrid agents are unmeasured]

## Method Thesis
Modality-boundary failures are a distinct, common, and precisely measurable phenomenon. An event-centric benchmark with counterfactual 3-branch replay can diagnose them deterministically. A VLM-distilled lightweight verifier can detect them at runtime with bounded latency.

## Contributions
- **Primary**: HybridStress — 20 audited tasks, 3 fault types, ~240 injected + ~60 clean switch events, counterfactual 3-branch labeling with exhaustive decision table
- **Reference detector**: CMV — VLM (Qwen2-VL-7B) distilled to 10M-param detector with structured postcondition input
- **Utility study**: Fixed recovery protocol, evaluated as downstream benefit measurement

## System Design

### SwitchEvent (refined)
```
SwitchEvent {
  // Core observation
  pre_screenshot: Image
  post_screenshot: Image
  action: str
  postconditions: List[Predicate]  # structured (subject, relation, object)
  
  // Checkpoint
  emulator_snapshot_id: str
  
  // Counterfactual labels (3-branch replay, majority of 3 runs each)
  hybrid_outcome: {success|failure}
  api_only_outcome: {success|failure}
  gui_only_outcome: {success|failure}
  
  // Derived (from decision table)
  label: {consistent_pass|BOUNDARY_SPECIFIC|gui_preferred|api_preferred|
          universally_hard|hybrid_advantage}
  
  // Fault metadata
  fault_type: {none|stale_observation|phantom_ack|state_rollback}
  fault_severity: {none|mild|moderate|severe}
}
```

### Benchmark Structure
- 20 tasks × (1 clean + 3 faults × 3 severities) = 20 × 10 = 200 conditions
- ~1.5 switch events per condition average → ~300 switch events
- Each event: 3 branches × 3 runs = 9 replay rollouts → ~2700 total rollouts

### CMV (Reference Detector)
- **Teacher**: Qwen2-VL-7B with structured prompt using predicate postconditions
- **Student**: Frozen SigLIP + postcondition encoder → MLP → binary (10M params)
- **Training**: HybridStress ground truth labels (NOT VLM labels)
- **Calibration**: Temperature scaling on held-out validation fold

### Natural Trace Validation
- 200+ events from 10 held-out apps
- Ground truth: replay-based where possible, 2 human annotators with rubric where not
- VLM judge as separate baseline (not ground truth)
- Report: AUPRC, AUROC, ECE, false alarm rate, plus inter-annotator κ

## Claims & Evidence
| Claim | Experiment | Metric | Success Criterion |
|-------|-----------|--------|-------------------|
| C1: Boundary failures are distinct and common | HybridStress prevalence study | BOUNDARY_SPECIFIC rate | >15% of switch-event failures |
| C2: CMV detects them on natural traces | Transfer evaluation | AUPRC | >0.7, gap to VLM <10% |
| C3: Recovery helps | Online evaluation | Task success delta | >3%, latency <15% |

## Compute: ~120 GPU-hours on 1x 4090, 4 weeks
