# Round 1 Refinement

## Problem Anchor
- **Bottom-line problem**: Hybrid API/GUI agents silently fail at modality boundaries — inconsistent state at switch points causes cascading failures.
- **Must-solve bottleneck**: No benchmark or method measures modality-boundary failures.
- **Non-goals**: Better GUI agent, single-modality improvement, routing, RL.
- **Constraints**: 1x RTX 4090; AndroidWorld; 4-5 weeks; NeurIPS 2025 D&B track.
- **Success condition**: (1) >15% boundary-specific failures. (2) VLM-distilled verifier transfers to natural traces. (3) Recovery helps.

## Anchor Check
- **Original bottleneck**: Silent desynchronization at modality boundaries.
- **Why the revised method still addresses it**: Tightened counterfactual labeling + event-centric benchmark + VLM-backed verifier.
- **Reviewer suggestions rejected as drift**: None — all accepted.

## Simplicity Check
- **Dominant contribution**: HybridStress benchmark (event-centric, counterfactual-labeled).
- **Components removed**: Bespoke cross-attention head replaced by VLM distillation.
- **Reviewer suggestions rejected as complexity**: None.
- **Why still smallest adequate route**: One benchmark + one reference detector + one utility study.

## Changes Made

### 1. Event-Centric Dataset Unit
- **Reviewer said**: Make dataset unit a switch event with pre-switch checkpoint and 3-branch replay.
- **Action**: Adopted fully. Each data point is now a `SwitchEvent` with checkpoint, 3-branch counterfactual replay, and deterministic boundary-specific labeling.
- **Impact**: Much cleaner ground truth; removes annotator subjectivity for boundary-specific label.

### 2. VLM Judge + Distillation
- **Reviewer said**: Pretrained VLM judge is the natural FM-era formulation; distill into CMV.
- **Action**: Adopted. Primary verifier is VLM judge (Qwen2-VL-7B or InternVL2-8B). Distilled lightweight CMV (~10M params) as the deployable detector. VLM judge also serves as the teacher for training data quality and as an upper bound.
- **Impact**: Stronger baseline, natural frontier leverage, cleaner training signal.

### 3. Reduced Task Scope
- **Reviewer said**: 15-20 audited replayable tasks > 50 loosely controlled.
- **Action**: Reduced to 20 audited tasks with verified checkpoint/replay fidelity. Each task has 4 fault types × 3 severities = 12 injected + 1 clean = 260 total switch events.
- **Impact**: Higher quality data, more trustworthy counterfactual labels.

### 4. Venue Commitment
- **Reviewer said**: Commit to NeurIPS D&B; HybridStress as main, CMV as reference detector.
- **Action**: Adopted. Paper structure: benchmark-first, reference detector, recovery utility.

### 5. Postcondition Canonicalization
- **Reviewer said**: Replace raw API blobs with expected visible postcondition.
- **Action**: Use LLM to canonicalize API response into expected postcondition description (e.g., "cart now contains item X"). Verifier input: (pre_screenshot, post_screenshot, expected_postcondition_text).
- **Impact**: Cleaner input for both VLM judge and distilled CMV.

## Revised Proposal

# Research Proposal: HybridStress — An Event-Centric Benchmark for Modality-Boundary Failures in Hybrid API/GUI Agents

## Problem Anchor
[Same as above — unchanged]

## Technical Gap
Hybrid API/GUI agents fail silently at modality boundaries. Existing benchmarks measure end-to-end success but cannot isolate where failures originate. No benchmark provides counterfactual-labeled data for boundary-specific failures.

## Method Thesis
Modality-boundary failures are a distinct, common, and measurable phenomenon. An event-centric benchmark with counterfactual labeling can diagnose them, and a VLM-distilled lightweight verifier can detect and mitigate them at runtime.

## Contribution Focus
- **Dominant (benchmark)**: HybridStress — 20 audited tasks, 260+ switch events, 4 fault types, counterfactual 3-branch labeling
- **Supporting (reference detector)**: CMV — VLM judge distilled to 10M-param lightweight detector
- **Utility study**: Fixed recovery protocol (re-screenshot → retry → GUI-only fallback)
- **Non-contributions**: No routing, no RL, no architecture changes

## Proposed Method

### HybridStress Benchmark

**Unit of analysis**: SwitchEvent — a single modality-boundary crossing in a task execution.

**Data structure per event**:
```
SwitchEvent {
  task_id: str
  step_index: int
  pre_screenshot: Image        # GUI state before switch
  action: str                  # action that crosses modality boundary
  api_response: JSON           # raw API response (if API→GUI)
  postcondition: str           # LLM-canonicalized expected visible state
  post_screenshot: Image       # GUI state after switch
  checkpoint: StateSnapshot    # full emulator state for replay
  
  # Counterfactual labels (from replay)
  hybrid_outcome: {success|failure}
  api_only_outcome: {success|failure}
  gui_only_outcome: {success|failure}
  
  # Derived label
  is_boundary_specific: bool   # True iff hybrid=fail AND api_only=success AND gui_only=success
  
  # Fault injection (for injected events)
  fault_type: {none|stale_screenshot|phantom_ack|partial_rollback|temporal_mismatch}
  fault_severity: {none|mild|moderate|severe}
}
```

**Task selection**: 20 AndroidWorld tasks selected for:
- High switch frequency (≥3 switches per episode)
- Deterministic replay capability (verified)
- Coverage of diverse app categories (messaging, shopping, navigation, settings)

**Fault injection**: Wrapper in mcp_backend_implements.py.
**Counterfactual replay**: From each checkpoint, 3 deterministic branches.
**Total**: 20 tasks × 13 conditions = 260 injected events + clean baselines ≈ 300 switch events.

### Cross-Modal Verifier (CMV)

**Two-tier architecture**:

1. **VLM Judge (teacher/upper bound)**: Qwen2-VL-7B prompted with:
   - Input: (pre_screenshot, post_screenshot, postcondition_text)
   - Prompt: "Given the expected postcondition '{postcondition}', does the post-switch screenshot show a state consistent with the pre-switch screenshot plus the expected state change? Answer: consistent or inconsistent."
   - Output: {consistent, inconsistent} with logit-based confidence

2. **Distilled CMV (deployable detector, ~10M params)**:
   - Pre/post screenshots: frozen SigLIP ViT-B/16 → visual features
   - Postcondition text: frozen text encoder → text features
   - Lightweight MLP scorer on concatenated features
   - Trained on VLM judge labels + HybridStress ground truth
   - Temperature-calibrated output

**Training**:
- Phase 1: VLM judge generates labels for HybridStress events
- Phase 2: Distill VLM judge → lightweight CMV using KD loss + ground truth BCE
- Total training: ~4 GPU-hours on 1x 4090

### Recovery Protocol (fixed, not learned)
When CMV detects inconsistency:
1. Re-capture screenshot (resolves Temporal Mismatch if transient)
2. If still inconsistent: retry action via GUI
3. If still inconsistent: escalate to GUI-only fallback for remainder of subtask

### Real-Trace Validation
- 200+ natural switch events from 10 held-out apps
- VLM judge annotations (no human annotation for boundary-specific label — use 3-branch replay where possible, VLM judgment elsewhere)
- Compare distilled CMV against: (a) no verification, (b) fixed-delay+re-screenshot, (c) API-status heuristic, (d) VLM judge (oracle upper bound)

## Claim-Driven Validation

### Claim 1 (Primary): Boundary failures are distinct, common (>15%), and measurable.
- **Experiment**: Run gelab-zero on 20 audited tasks, counterfactual-label all switch events, report prevalence.
- **Metric**: Boundary-specific failure prevalence per event and per episode.
- **Success**: >15% of switch-event failures are boundary-specific.

### Claim 2 (Supporting): Distilled CMV detects boundary inconsistencies on natural traces.
- **Experiment**: Train CMV on HybridStress, evaluate on natural traces.
- **Baselines**: Fixed-delay, API-status heuristic, VLM judge (upper bound).
- **Metrics**: AUPRC, AUROC, ECE/Brier, false alarm rate.
- **Success**: CMV AUPRC > 0.7 on held-out traces; gap to VLM judge < 10%.

### Claim 3 (Utility): Recovery improves task success with bounded latency.
- **Experiment**: Online evaluation with CMV-triggered recovery.
- **Baselines**: No verification, blind retry.
- **Metrics**: Task success delta, latency overhead, false alarm rate.
- **Success**: +3% success, <15% latency increase, <10% false alarm rate.

## Compute & Timeline
- HybridStress construction: ~50 GPU-hours (emulator replay)
- VLM judge inference: ~8 GPU-hours
- CMV training: ~4 GPU-hours
- Natural trace collection: ~30 GPU-hours
- Evaluation: ~10 GPU-hours
- Total: ~102 GPU-hours ≈ 4.5 days on 1x 4090
- Timeline: 4 weeks (benchmark: 1.5w, VLM+CMV: 0.5w, evaluation: 1w, writing: 1w)
