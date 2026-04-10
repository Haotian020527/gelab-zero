# Experiment Plan

**Problem**: Silent modality-boundary failures in hybrid API/GUI agents
**Method Thesis**: Modality-boundary failures are distinct, common, and precisely measurable via event-centric counterfactual benchmarking.
**Date**: 2026-04-04

## Claim Map

| Claim | Why It Matters | Minimum Convincing Evidence | Linked Blocks |
|-------|----------------|-----------------------------|---------------|
| C1: Boundary failures are distinct and common (>15%) | Justifies the entire benchmark's existence | Prevalence study on 20 tasks with deterministic labeling | B1, B2 |
| C2: CMV detects them on natural traces (AUPRC >0.7) | Shows the benchmark has practical mitigation utility | Transfer evaluation on held-out apps | B3, B4 |
| C3: Recovery helps (exploratory) | Downstream benefit | Online evaluation with CIs | B5 |

## Paper Storyline
- **Main paper must prove**: C1 (boundary failures exist and are common), C2 (CMV detects them)
- **Appendix can support**: Fault-type breakdown, validator calibration study, per-app analysis
- **Experiments intentionally cut**: Routing optimization, RL training, world model, full agent retraining

## Experiment Blocks

### Block 1: HybridStress Construction + Sanity Check
- **Claim tested**: Benchmark is valid and reproducible
- **Why this block exists**: Foundation for all subsequent experiments
- **Dataset / split / task**: 20 AndroidWorld tasks, selected for switch frequency ≥ 3 and replay determinism
- **Setup details**: 
  - Install AndroidWorld emulator environment
  - Implement fault injection wrapper for mcp_backend_implements.py
  - Implement 3 deterministic validators (ADB, UI XML, OCR)
  - Implement SwitchEvent data structure and logging
  - Run 200 conditions (20 tasks × 10), extract ~300 switch events
  - Run 3-branch replay (3 runs each) → ~2700 rollouts
- **Metrics**: Replay determinism rate, validator agreement rate
- **Success criterion**: >95% replay determinism (same outcome across 3 runs of same branch); >90% validator agreement across the 3 validators where applicable
- **Failure interpretation**: If replay is non-deterministic → need to restrict to more controlled apps or increase runs
- **Table / figure target**: Table 1 (benchmark statistics), Figure 1 (architecture diagram)
- **Priority**: MUST-RUN

### Block 2: Boundary Failure Prevalence Study (C1)
- **Claim tested**: C1 — boundary-specific failures account for >15% of all switch-event failures
- **Why this block exists**: Core empirical finding that justifies the paper
- **Dataset**: HybridStress (all 300 switch events)
- **Compared systems**: gelab-zero (heuristic router), API-only, GUI-only
- **Metrics**: 
  - BOUNDARY_SPECIFIC count / total failure count (prevalence)
  - Distribution across label categories (full decision table)
  - Breakdown by fault type and severity
  - Breakdown by app category
- **Success criterion**: >15% of failures in the BOUNDARY_SPECIFIC category
- **Failure interpretation**: If <15%, boundary failures may be rare → reposition paper as diagnostic study showing they're uncommon but dangerous when they occur
- **Table / figure target**: Table 2 (prevalence by fault type), Figure 2 (heatmap of label distribution)
- **Priority**: MUST-RUN

### Block 3: CMV Training + In-Distribution Evaluation
- **Claim tested**: CMV can detect boundary inconsistencies on HybridStress data
- **Why this block exists**: Validates the reference detector design
- **Dataset**: HybridStress, 80/20 train/val split (stratified by task and fault type)
- **Compared systems**: 
  - VLM judge (Qwen2-VL-7B) — upper bound
  - Fixed-delay + re-screenshot — simple baseline
  - API-status heuristic — naive baseline
  - Distilled CMV (ours)
- **Metrics**: AUPRC, AUROC, ECE/Brier, false alarm rate
- **Setup**: 
  - VLM judge: Qwen2-VL-7B, prompted with structured postconditions, ~4 GPU-hours inference
  - CMV: SigLIP ViT-B/16 (frozen) + MLP, BCE (0.7) + KD (0.3), lr=1e-4, 50 epochs, ~2 GPU-hours
  - Temperature calibration on validation fold
- **Success criterion**: CMV AUPRC > 0.8 in-distribution
- **Failure interpretation**: If CMV < 0.8 → architecture needs upgrade (try cross-attention), or data augmentation needed
- **Table / figure target**: Table 3 (detector comparison)
- **Priority**: MUST-RUN

### Block 4: Natural Trace Transfer Evaluation (C2)
- **Claim tested**: C2 — CMV trained on HybridStress transfers to natural traces
- **Why this block exists**: External validity — the most important experiment
- **Dataset**: 200+ natural switch events from 10 held-out apps (no fault injection)
- **Ground truth**: Replay-based where checkpoints available; 2 human annotators with rubric where not
- **Compared systems**: Same as Block 3 (VLM, fixed-delay, API-status, CMV)
- **Metrics**: AUPRC, AUROC, ECE, false alarm rate, inter-annotator κ
- **Success criterion**: CMV AUPRC > 0.7; gap to VLM judge < 10%
- **Failure interpretation**: If transfer fails → synthetic faults don't match real distribution, need to revise injection methods or augment with real failure data
- **Table / figure target**: Table 4 (transfer results), Figure 3 (calibration plot)
- **Priority**: MUST-RUN

### Block 5: Recovery Utility Study (C3 — Exploratory)
- **Claim tested**: C3 — CMV-triggered recovery improves task success
- **Why this block exists**: Demonstrates practical downstream value
- **Dataset**: AndroidWorld standard evaluation set (20 tasks)
- **Compared systems**: 
  - gelab-zero (no verification)
  - gelab-zero + blind retry at every switch
  - gelab-zero + CMV-triggered recovery
- **Metrics**: Task success rate (delta), latency overhead (%), false alarm rate
- **Statistical test**: Paired bootstrap confidence intervals (10000 samples)
- **Success criterion**: Positive delta reported with CIs; NOT a headline number
- **Failure interpretation**: If no improvement → detection works but recovery protocol is insufficient, or boundary failures aren't the bottleneck
- **Table / figure target**: Table 5 (utility study, with CIs)
- **Priority**: NICE-TO-HAVE (but important for completeness)

### Block 6: Human Calibration Study
- **Claim tested**: Deterministic validators are accurate
- **Why this block exists**: Validates the label generation pipeline
- **Setup**: 50 randomly sampled switch events, 2 annotators, structured rubric
- **Metrics**: Validator accuracy, FP/FN rates, inter-annotator κ
- **Success criterion**: κ > 0.7, validator accuracy > 90%
- **Table / figure target**: Table 6 (appendix)
- **Priority**: MUST-RUN

## Run Order and Milestones

| Milestone | Goal | Runs | Decision Gate | Cost | Risk |
|-----------|------|------|---------------|------|------|
| M0: Sanity | Set up emulator, fault injection, validators | Block 1 (partial: 3 tasks) | Replay works, validators agree | 10 GPU-hrs | Medium: emulator instability |
| M1: Benchmark | Full HybridStress construction | Block 1 (full: 20 tasks) + Block 2 | >15% boundary failures | 60 GPU-hrs | High: if boundary failures are rare, paper pivots |
| M2: Detector | CMV training + in-distribution eval | Block 3 | AUPRC > 0.8 | 8 GPU-hrs | Low: straightforward classification |
| M3: Transfer | Natural trace collection + transfer eval | Block 4 + Block 6 | AUPRC > 0.7, κ > 0.7 | 40 GPU-hrs | High: synthetic→real transfer gap |
| M4: Utility | Recovery evaluation (exploratory) | Block 5 | Report with CIs | 10 GPU-hrs | Low: exploratory, no hard threshold |

## Compute and Data Budget
- **Total GPU-hours**: ~128 hours on 1x RTX 4090 (≈ 5.3 days continuous)
- **Data preparation**: Task selection and postcondition annotation (1 researcher × 2 days)
- **Human evaluation**: 2 annotators × 250 events × 5 min = 42 person-hours
- **Biggest bottleneck**: Emulator replay (2700 rollouts, ~80 GPU-hours)

## Risks and Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Boundary failures < 15% | Medium | Paper repositions | Show they're rare but dangerous; focus on fault injection results |
| Replay non-determinism | Medium | Label noise | Majority vote over 3 runs; restrict to deterministic apps |
| CMV doesn't transfer to natural traces | Medium | C2 fails | Revise injection methods; augment with labeled real data |
| Emulator instability | Low | Delays | Pre-screen tasks for stability; checkpointing |
| Postcondition incompleteness | Low | Validator misses | Select tasks with fully observable postconditions |

## Final Checklist
- [x] Main paper tables are covered (Tables 1-5)
- [x] Novelty is isolated (benchmark + counterfactual labeling)
- [x] Simplicity is defended (one benchmark + one detector, no routing/RL)
- [x] Frontier contribution is justified (VLM as teacher, not decoration)
- [x] Nice-to-have runs separated from must-runs (Block 5 = nice-to-have)
