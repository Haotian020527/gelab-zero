# Pipeline Summary

**Problem**: Smart-cockpit agents need low latency, bounded memory, and hard safety boundaries, but pure GUI control and learned safety judges do not provide all three at once.
**Final Method Thesis**: A typed action-contract layer plus deterministic signal and 2FA gating enables API-first cockpit control with bounded GUI fallback, producing safer and more practical edge-local execution than screenshot-native baselines.
**Current Stage**: Bridge-stage experiments complete; ready for claim judgment and review-driven polish.
**Date**: 2026-04-09

## Final Deliverables

- Proposal: `refine-logs/FINAL_PROPOSAL.md`
- Review summary: `refine-logs/REVIEW_SUMMARY.md`
- Experiment plan: `refine-logs/EXPERIMENT_PLAN.md`
- Experiment tracker: `refine-logs/EXPERIMENT_TRACKER.md`
- Experiment results: `refine-logs/EXPERIMENT_RESULTS.md`
- Project narrative: `NARRATIVE_REPORT.md`
- Idea report: `IDEA_REPORT.md`

## Selected Idea

**SafeRoute-Cockpit**

- **Dominant contribution**: contract-routed hybrid cockpit architecture with deterministic safety gates.
- **Supporting contribution**: compact action-contract IR.
- **Supporting contribution**: compact red/yellow/green safety evaluation suite.
- **Supporting contribution**: contract-scoped GUI fallback.

## Claim Status

- **C1: SUPPORT**. SafeRoute is consistently low-latency and screenshot-free on API-covered routine and held-out tasks.
- **C2: SUPPORT (SCOPED)**. SafeRoute has zero unsafe red-zone executions and 100% decision accuracy in the expanded 34-case suite; prompt-only and no-gate baselines fail unsafely, while semantic/text guardrails remain over-restrictive on state-conditioned allow cases.
- **C3: SUPPORT**. Contract-scoped fallback preserves success in API-gap tasks, reduces estimated visual area by 92.6%, reduces Qwen2-VL processor effective image tokens by 93.05% on matched probes, and reduces dynamic fallback screenshot image tokens by 84.36%.
- **C4: SUPPORT**. The real VLM+STT+TTS+gateway stack fits on one RTX 4090 with 17,701 MB peak VRAM and 0 OOM.

## Canonical Evidence

- `results/safe_route/remote_sanity/sanity_results.json`
- `results/safe_route/remote_routine/routine_results.json`
- `results/safe_route/remote_safety_expanded/safety_results.json`
- `results/safe_route/remote_fallback/fallback_results.json`
- `results/safe_route/remote_stack/stack_results.json`
- `results/safe_route/remote_generalization/generalization_results.json`
- `results/safe_route/remote_token_accounting/token_accounting_results.json`
- `results/safe_route/remote_dynamic_token_trace/dynamic_token_trace_results.json`

## Main Risks

- The safety claim must remain scoped to the tested commands, states, and attacks.
- The current C2 evidence includes Naive Bayes and semantic guardrail baselines, but not a true DeBERTa/NLI model.
- Dynamic token tracing uses deterministic ROI crops, not a learned ROI locator.
- The remaining HybridStress-era results are legacy context and should not be cited as current SafeRoute evidence.

## Next Action

Proceed with `result-to-claim` or paper planning. If review requests more evidence, prioritize a true DeBERTa/NLI safety baseline or human-written adversarial prompts.
