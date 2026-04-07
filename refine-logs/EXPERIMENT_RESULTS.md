# HybridStress Experiment Results

**Date**: 2026-04-07
**Backend**: Virtual Car Cockpit (IVI Simulator)

---

## Table 1: Benchmark Statistics

| Metric | Value |
|--------|-------|
| IVI subsystems | 7 (navigation, media, climate, phone, messages, settings, vehicle) |
| Benchmark tasks | 20 |
| Conditions per task | 10 (1 clean + 3 faults × 3 severities) |
| Total switch events | 200 |
| Replay runs per branch | 3 (majority vote) |
| Replay determinism | 100% |

## C1: Boundary Failure Prevalence ✅

**Claim**: >15% of modality-switching failures are boundary-specific (i.e., caused by the API↔GUI handoff itself, not by either modality alone).

| Label | Count | Percentage |
|-------|-------|-----------|
| consistent_pass | 98 | 49.0% |
| **boundary_specific** | **54** | **27.0%** |
| api_preferred | 48 | 24.0% |

**Failure breakdown** (102 total failures):
- Boundary-specific: 54 / 102 = **52.94%** of failures
- **C1 PASSED** ✅ (threshold: >15%, actual: 52.94%)

**Interpretation**: Over half of all failures in the HybridStress benchmark are boundary-specific — they occur only when the hybrid API+GUI execution path is used, while both pure-API and pure-GUI succeed individually. This confirms that modality-boundary failures are not just theoretically possible but empirically dominant.

## M2: Detector Training (In Progress)

**Status**: VLM judge inference started 2026-04-07 14:01

**Pipeline**:
1. **R007**: VLM judge (Qwen2-VL-7B) inference on all 200 events (~4 GPU-hrs)
2. **R008**: CMV training (SigLIP ViT-B/16 + MLP, 10M params, BCE 0.7 + KD 0.3) (~2 GPU-hrs)
3. **R009**: In-distribution evaluation (Table 3: AUPRC, AUROC, ECE, FAR)

**Monitor**: `ssh fce "tail -f /tmp/hs_ck_m2.log"`

---

## Next Steps

- [ ] M2 completes → extract Table 3 (detector comparison)
- [ ] M3: Natural trace collection on held-out tasks
- [ ] M4: Recovery utility study (exploratory)
- [ ] Paper writing pipeline
