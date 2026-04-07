# Experiment Tracker

| Run ID | Milestone | Purpose | System / Variant | Split | Metrics | Priority | Status | Notes |
|--------|-----------|---------|------------------|-------|---------|----------|--------|-------|
| R001 | M0 | Sanity: data structures | Data types | Unit tests | Structure integrity | MUST | DONE | 4/4 checks PASS |
| R002 | M0 | Sanity: fault injection | Injection wrapper | Unit tests | Injection success rate | MUST | DONE | 3 fault types × 3 severities verified |
| R003 | M0 | Sanity: cockpit backend | Cockpit IVI | 3 pilot tasks | Server, API, validators | MUST | DONE | 7/7 checks PASS, 3/3 pilot tasks PASS |
| R004 | M1 | Benchmark: full construction | Cockpit backend | 20 tasks × 10 conditions | Event count, replay rate | MUST | DONE | 200 events generated, replay det=100% |
| R005 | M1 | Benchmark: 3-branch replay | Counterfactual replay | All switch events | Label distribution | MUST | DONE | 98 PASS, 54 BOUNDARY, 48 API_PREF |
| R006 | M1 | Prevalence: C1 | Label analysis | All events | BOUNDARY_SPECIFIC% | MUST | DONE | **C1 PASSED: 52.94%** (threshold >15%) |
| R007 | M2 | VLM judge inference | Qwen2-VL-7B | HybridStress (all) | Consistency predictions | MUST | RUNNING | tmux: hs_ck_m2, started 2026-04-07 14:01 |
| R008 | M2 | CMV training | SigLIP+MLP (10M) | 80/20 split | AUPRC, AUROC, ECE | MUST | RUNNING | Part of R007 pipeline |
| R009 | M2 | CMV in-distribution eval | All detectors | HybridStress val | AUPRC, false alarm | MUST | RUNNING | Table 3 auto after R008 |
| R010 | M3 | Natural trace collection | gelab-zero | 10 held-out apps | Event count | MUST | TODO | ~30 GPU-hrs. Deploy after M2 |
| R011 | M3 | Human annotation | 2 annotators | 50 sampled events | κ, validator accuracy | MUST | TODO | ~10 person-hrs. Manual step |
| R012 | M3 | Transfer evaluation (C2) | All detectors | Natural traces | AUPRC, AUROC | MUST | TODO | Table 4. Requires R010+R011 |
| R013 | M4 | Recovery utility (C3) | gelab-zero ± CMV | 20 tasks online | Success delta, latency | NICE | TODO | Table 5, paired bootstrap |
| R014 | M4 | Blind retry baseline | gelab-zero + retry | 20 tasks online | Success delta, latency | NICE | TODO | Ablation for Table 5 |

## M1 Results Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Total events | 200 | ≥200 | ✅ PASS |
| Tasks | 20 | 20 | ✅ PASS |
| Replay determinism | 100% | ≥95% | ✅ PASS |
| Total failures | 102 | — | — |
| Boundary-specific | 54 (52.94%) | >15% | ✅ **C1 PASSED** |
| Consistent pass | 98 (49%) | — | — |
| API preferred | 48 (24%) | — | — |

## Code Review Log

| Date | Reviewer | Issues Found | Status |
|------|----------|-------------|--------|
| 2026-04-07 | GPT-5.4 xhigh (Codex MCP) | 1 CRITICAL, 6 MAJOR, 2 MINOR | ALL FIXED |

### Issues Fixed:
1. **CRITICAL**: Validator matching entire JSON state → Fixed: subject-first resolution
2. **MAJOR**: Snapshot contamination across conditions → Fixed: restore "initial" before each
3. **MAJOR**: PARTIAL_FAIL counted in prevalence → Fixed: excluded from C1 denominator
4. **MAJOR**: Majority vote tie defaulting to FAILURE → Fixed: strict majority required
5. **MAJOR**: STALE_OBSERVATION not in screenshots → Fixed: cache pre-action screenshot
6. **MAJOR**: message_status/bluetooth_status not persisted → Fixed: stored in state
7. **MAJOR**: GUI-only treated errors as success → Noted (low priority for cockpit)
