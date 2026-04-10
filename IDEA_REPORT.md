# Research Idea Report

**Direction**: GUI Agent Hybrid API/GUI Architecture Optimization (gelab-zero)
**Generated**: 2026-04-04
**Ideas evaluated**: 10 generated → 4 survived filtering → 1 (merged composite) selected → READY after 4 review rounds

## Landscape Summary

The GUI Agent field has undergone a fundamental transformation from monolithic agents toward hybrid API/GUI architectures. Systems like gelab-zero implement an "API-first, GUI-fallback" design that combines structured API calls (for speed/reliability) with visual GUI interaction (for coverage/flexibility). The Model Context Protocol (MCP) has become the standard integration layer, evolving from experimental tooling to enterprise-grade infrastructure.

Key research advances include RL-based GUI reasoning (InfiGUI-R1, MobileGUI-RL), active perception (GUI-Eyes), self-evolving agents (GUI-Bee), and error recovery (BEAP-Agent). Benchmarks like AndroidWorld are approaching saturation (>90% success), driving the community toward more challenging evaluation settings (A3, MobileWorld).

However, a critical blind spot remains: no existing work systematically studies or measures **modality-boundary failures** — the cascading errors that occur when hybrid agents switch between API and GUI execution paths. This represents both an underexplored research direction and a practical reliability concern as MCP-based hybrid architectures become production-standard.

## Recommended Idea (Selected)

### HybridStress: Event-Centric Benchmark for Modality-Boundary Failures
- **Hypothesis**: Hybrid agents silently fail at modality boundaries (>15% of failures are boundary-specific), and these failures are distinct from within-modality failures.
- **Minimum experiment**: Build fault-injection benchmark on AndroidWorld with counterfactual 3-branch labeling, measure prevalence.
- **Expected outcome**: >15% of hybrid switch-event failures are boundary-specific; a VLM-distilled verifier detects them with AUPRC > 0.7 on natural traces.
- **Novelty**: 7/10 — closest: MAS-FIRE (not modality-boundary), GTArena (not cross-modal)
- **Feasibility**: ~128 GPU-hours on 1x RTX 4090, 4 weeks
- **Risk**: MEDIUM (main risk: boundary failures may be rare; mitigated by repositioning)
- **Contribution type**: Benchmark + diagnostic + reference method
- **Pilot result**: SKIPPED (needs AndroidWorld emulator setup)
- **Reviewer's likely objection**: "Synthetic faults may not match real failure distributions"
- **Why we should do this**: As hybrid architectures become standard, understanding and measuring their unique failure modes is essential — this is the "crash testing" paper for MCP-based hybrid agents.

## Eliminated Ideas (for reference)

| Idea | Reason Eliminated |
|------|-------------------|
| Forward GUI World Model | Requires months + large training data |
| Self-Evolving API Schema Repair | HIGH risk, months of effort |
| Hybrid Difficulty Estimator | Minor contribution alone |
| Hierarchical Option Library | Months, complex RL |
| Learned Routing Policy (C3) | 4/10 novelty — UFO2 + OSWorld-MCP cover this |

## Suggested Execution Order
1. Start with M0: Sanity stage (emulator, validators, 3 pilot tasks)
2. If replay works: M1 benchmark construction + prevalence study (C1)
3. If C1 passes: M2-M3 detector training + transfer evaluation (C2)
4. If C2 passes: M4 utility study (C3, exploratory)
5. If all pass: invoke `/paper-writing` for submission to NeurIPS 2025 D&B

## Next Steps
- [ ] Set up AndroidWorld emulator on GPU server
- [ ] Implement fault injection wrapper in mcp_backend_implements.py
- [ ] Implement deterministic validators (ADB, UI XML, OCR)
- [ ] Run 3 pilot tasks to validate replay determinism
- [ ] Scale to full 20-task benchmark
