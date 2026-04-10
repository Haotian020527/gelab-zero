# Refinement Report

**Problem**: Silent modality-boundary failures in hybrid API/GUI agents
**Initial Approach**: RouteGuard — calibrated routing + boundary verification + causal benchmark
**Date**: 2026-04-04
**Rounds**: 4 / 5
**Final Score**: 9.3 / 10
**Final Verdict**: READY

## Problem Anchor
Hybrid API/GUI agents silently fail at modality boundaries — when execution switches between API and GUI paths, application state can become inconsistent without any error signal, causing cascading downstream failures. No existing benchmark or method specifically detects or measures these failures.

## Output Files
- Review summary: `refine-logs/REVIEW_SUMMARY.md`
- Final proposal: `refine-logs/FINAL_PROPOSAL.md`
- Experiment plan: `refine-logs/EXPERIMENT_PLAN.md`
- Experiment tracker: `refine-logs/EXPERIMENT_TRACKER.md`
- Pipeline summary: `refine-logs/PIPELINE_SUMMARY.md`

## Score Evolution

| Round | Anchor | Focus | Modernity | Label Rigor | Ground Truth | Claim-Eval | Feasibility | Overall | Verdict |
|-------|--------|-------|-----------|-------------|-------------|------------|-------------|---------|---------|
| 1     | 8      | 7     | 6         | —           | —           | 8          | 6           | 6.7     | REVISE  |
| 2     | 9.5    | 9.1   | 9.1       | 8.8         | 7.8         | 8.2        | 8.6         | 8.7     | REVISE  |
| 3     | 9.4    | 9.0   | 9.1       | 9.0         | 8.1         | 8.7        | 8.5         | 8.8     | REVISE  |
| 4     | 9.4    | 9.3   | 9.1       | 9.0         | 9.4         | 9.5        | 8.5         | 9.3     | READY   |

## Round-by-Round Review Record

| Round | Main Reviewer Concerns | What Was Changed | Result |
|-------|------------------------|------------------|--------|
| 1 | Event unit undefined, VLM not used, scope too broad, venue unclear | Event-centric SwitchEvent, VLM distillation, 20 tasks, NeurIPS D&B | Resolved |
| 2 | Label derivation opaque, supervision circular, replay undefined, taxonomy noisy | Decision table, separated GT, structured postconditions, 3-type taxonomy | Resolved |
| 3 | GT uses models, C3 too strong, supervision ambiguity | Deterministic validators, C3→exploratory, exact training protocol | Resolved |
| 4 | None (all blockers cleared) | — | READY |

## Final Proposal Snapshot
- First event-centric benchmark for modality-boundary failures in hybrid API/GUI agents
- Deterministic counterfactual 3-branch labeling with exhaustive 8-row decision table
- 3-type fault taxonomy: Stale Observation, Phantom Acknowledgment, State Rollback
- VLM-distilled cross-modal verifier (10M params) as reference detector
- Fixed recovery protocol as utility study
- ~128 GPU-hours on 1x RTX 4090, 4-week timeline

## Method Evolution Highlights
1. **Most important focusing move**: Dropped learned router (C3 original) entirely — router is NOT the contribution
2. **Most important mechanism upgrade**: Deterministic validators (ADB + UI XML + OCR) replaced model-in-the-loop labels
3. **Most important modernization**: VLM as distillation teacher + baseline, not as primary method

## Pushback / Drift Log
| Round | Reviewer Said | Author Response | Outcome |
|-------|---------------|-----------------|---------|
| 1 | "Use VLM judge as main method" | Adopted VLM as teacher for distillation, not primary | Accepted |
| 1 | "50 tasks too many, uncontrolled" | Reduced to 20 audited, replayable tasks | Accepted |
| 2 | "Taxonomy should collapse temporal" | Merged Temporal Mismatch into Stale Observation | Accepted |
| 3 | "C3 fragile at this scale" | Downgraded to exploratory with paired bootstrap CIs | Accepted |
| (None rejected as drift) | | | |

## Remaining Weaknesses
- Replay non-determinism across Android emulator runs (mitigated by 3-run majority vote)
- Postcondition completeness dependent on task selection (mitigated by choosing fully observable tasks)
- Ecological validity of synthetic faults (mitigated by real-trace validation)
- Scale limited to AndroidWorld apps (future work: OSWorld, WebArena)

## Next Steps
- READY → proceed to `/run-experiment` with R001-R003 (sanity stage)
- After sanity: full benchmark construction (R004-R006)
- After prevalence confirmed: detector training + transfer evaluation (R007-R012)
- If all claims pass: draft paper via `/paper-writing`
