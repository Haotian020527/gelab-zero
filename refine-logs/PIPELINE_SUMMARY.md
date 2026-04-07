# Pipeline Summary

**Problem**: Silent modality-boundary failures in hybrid API/GUI agents are unmeasured, causing cascading failures.
**Final Method Thesis**: Modality-boundary failures are a distinct, common, and precisely measurable phenomenon. An event-centric benchmark with deterministic counterfactual labeling diagnoses them; a VLM-distilled lightweight verifier detects them at runtime.
**Final Verdict**: READY (9.3/10 after 4 rounds of GPT-5.4 review)
**Date**: 2026-04-04

## Final Deliverables
- Proposal: `refine-logs/FINAL_PROPOSAL.md`
- Review summary: `refine-logs/REVIEW_SUMMARY.md`
- Experiment plan: `refine-logs/EXPERIMENT_PLAN.md`
- Experiment tracker: `refine-logs/EXPERIMENT_TRACKER.md`

## Contribution Snapshot
- **Dominant contribution**: HybridStress benchmark — 20 tasks, 3 fault types, ~300 switch events, deterministic counterfactual 3-branch labeling
- **Supporting contribution**: Cross-Modal Verifier (CMV) — VLM-distilled 10M-param reference detector
- **Explicitly rejected complexity**: Learned routing policy, world model, RL training, hierarchical planning, architecture changes

## Must-Prove Claims
- **C1 (Primary)**: >15% of hybrid agent failures are boundary-specific (proved by counterfactual labeling)
- **C2 (Supporting)**: CMV AUPRC > 0.7 on natural traces (proved by synthetic→real transfer evaluation)
- **C3 (Exploratory)**: Recovery improves success (reported with paired bootstrap CIs, not headline)

## First Runs to Launch
1. **R001-R003**: Sanity stage — set up emulator, fault injection, validators on 3 pilot tasks
2. **R004-R005**: Full benchmark construction — 20 tasks, 2700 replay rollouts
3. **R006**: Prevalence study — primary claim C1

## Main Risks
- **Boundary failures may be rare (<15%)**:
  - Mitigation: reposition as "rare but dangerous" diagnostic study
- **Synthetic→real transfer may fail**:
  - Mitigation: revise injection methods, augment with labeled real data
- **Replay non-determinism**:
  - Mitigation: majority vote over 3 runs, restrict to deterministic apps

## Next Action
- Proceed to `/run-experiment` with R001-R003 (sanity stage)
