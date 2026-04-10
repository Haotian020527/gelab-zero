# Experiment Results

Last updated: 2026-04-09
Status: M0, M1, M2, M3, M4, M5, M6, M7, and expanded C2 safety polish collected

## Initial Experiment Results

**Date**: 2026-04-09
**Plan**: `refine-logs/EXPERIMENT_PLAN.md`

## Completed Milestones

### M0: Contract Baseline - PASSED

- Artifacts:
  - `results/safe_route/remote_sanity/sanity_results.json`
  - `results/safe_route/remote_sanity/gateway_unit_results.json`
- Contract schema frozen at `version=1.0`
  - Required fields: `intent`, `risk_zone`, `required_signals`, `required_2fa`, `allowed_api_paths`, `gui_fallback_policy`, `postconditions`
  - Risk zones: `green`, `yellow`, `red`
  - Fallback policies: `allow`, `challenge`, `deny`
- Gateway seed checks: PASS
  - Green task allowed
  - Red task blocked when gear is not `P`
  - Red task challenged until biometric 2FA is present
  - Yellow task challenged until confirmation is present

### M0: 3-Task Pilot - PASSED

Source: `results/safe_route/remote_sanity/sanity_results.json`

| System | Success Rate | Median TTFA / Latency | Mean TTFA / Latency | Mean Screenshots | Mean Vision Pixels | Peak VRAM (measured) |
|---|---|---:|---:|---:|---:|---:|
| API-only | 100% | 0 ms | 0.33 ms | 0 | 0 | 116 MB |
| Hybrid | 100% | 0 ms | 0.11 ms | 0 | 0 | 116 MB |
| GUI-only | 33.3% | 1136 ms | 1192.78 ms | 1.0 | 2,073,600 | 116 MB |
| SafeRoute | 100% | 1 ms | 1.00 ms | 0 | 0 | 116 MB |

### M1: 20-Task Routine Benchmark - PASSED

Source: `results/safe_route/remote_routine/routine_results.json`

| System | Success Rate | Median TTFA / Latency | Mean TTFA / Latency | Mean Screenshots | Mean Vision Pixels | Peak VRAM (measured) |
|---|---|---:|---:|---:|---:|---:|
| API-only | 100% | 0 ms | 0.45 ms | 0 | 0 | 116 MB |
| Hybrid | 100% | 0 ms | 0.25 ms | 0 | 0 | 116 MB |
| GUI-only | 60% | 1178.5 ms | 3209.85 ms | 1.0 | 2,073,600 | 116 MB |
| SafeRoute | 100% | 1 ms | 1.20 ms | 0 | 0 | 116 MB |

Additional observations:

- `SafeRoute` routed all 20 routine tasks through `api_first`.
- The current 20-task suite contains 18 green tasks and 2 yellow tasks; all 20 succeeded under `SafeRoute`.
- No GUI fallback was needed in the current routine run because every tested task had an API path.
- `GUI-only` failed 8 of 20 tasks:
  - `nav_set_dest_001`
  - `nav_start_002`
  - `climate_temp_007`
  - `climate_seat_heat_009`
  - `phone_dial_010`
  - `phone_add_contact_012`
  - `msg_send_013`
  - `veh_sport_mode_019`

### M2: Expanded Safety Attack Suite - PASSED

Sources:

- `results/safe_route/remote_safety/safety_results.json`
- `results/safe_route/remote_safety/safe_bench_cases.json`
- `results/safe_route/remote_safety_expanded/safety_results.json`
- `results/safe_route/remote_safety_expanded/safe_bench_cases.json`

Benchmark scope:

- Current canonical `CockpitSafeBench` contains 34 explicit-label cases.
- The earlier 18-case result is preserved in `results/safe_route/remote_safety/`; the expanded result is the current C2 source of truth.
- Zones: green, yellow, red.
- Prompt styles: clean, paraphrase, attack, confirmed, and hard-negative.
- State factors: gear, speed, battery, confirmation, biometric 2FA.
- Compared systems:
  - `prompt_only`: prompt-only guardrail surrogate
  - `learned_only`: lightweight text-only Naive Bayes guardrail
  - `semantic_guard`: high-recall semantic keyword guardrail baseline
  - `hybrid_no_gate`: API-first execution without deterministic safety gate
  - `safe_route`: full deterministic gateway

| System | Unsafe Execution | Unsafe Red-Zone Execution | False Block Green | False Non-Allow Yellow-Allow | Challenge Accuracy | Decision Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Prompt-only | 55.6% | 54.5% | 14.3% | 25.0% | 18.2% | 50.0% |
| Learned-only | 0.0% | 0.0% | 57.1% | 100.0% | 63.6% | 41.2% |
| Semantic-guard | 0.0% | 0.0% | 0.0% | 100.0% | 36.4% | 44.1% |
| Hybrid-no-gate | 100.0% | 100.0% | 0.0% | 0.0% | 0.0% | 47.1% |
| SafeRoute | 0.0% | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% |

Interpretation:

- `SafeRoute` matched all 34 expected decisions and produced zero unsafe red-zone executions.
- The expanded suite adds hard-negative green prompts, social-engineering yellow prompts, and synonym attacks for OTA, ADAS calibration, and trip-reset operations.
- `Hybrid-no-gate` executed every restricted red/yellow command, so its unsafe and unsafe-red execution rates were 100%.
- `Prompt-only` became more vulnerable under expanded attack phrasing, with 54.5% unsafe red-zone execution.
- `Learned-only` and `semantic_guard` both avoided unsafe red-zone execution, but they failed the state-conditioned authorization objective: both produced 100% false non-allow on yellow allow-cases.
- This strengthens C2 by showing that even a high-recall semantic text guardrail cannot reproduce deterministic signal/confirmation/2FA behavior. It is still not a DeBERTa/NLI baseline or certification claim.

### M3: API-Disabled Fallback Ablation - PASSED

Sources:

- `results/safe_route/remote_fallback/fallback_results.json`
- `results/safe_route/remote_fallback/fallback_cases.json`

Benchmark scope:

- 7 tasks, one per category: navigation, media, climate, phone, messages, settings, vehicle.
- APIs were treated as unavailable for the benchmark comparison.
- Compared systems:
  - `no_fallback`
  - `full_screen_fallback`
  - `contract_scoped_fallback`

| System | Success Rate | Median TTFA / Latency | Mean TTFA / Latency | Mean Vision Pixels | Fallback Invocation |
|---|---:|---:|---:|---:|---:|
| No fallback | 0.0% | 0 ms | 0.0 ms | 0 | 0.0 |
| Full-screen fallback | 100.0% | 1138 ms | 2306.29 ms | 2,073,600 | 1.0 |
| Contract-scoped fallback | 100.0% | 1147 ms | 1492.29 ms | 153,600 | 1.0 |

Key comparison:

- Success gap between contract-scoped and full-screen fallback: `0.0` points.
- Estimated vision-area reduction versus full-screen fallback: `92.6%`.

Interpretation:

- On the current API-disabled subset, contract-scoped fallback preserved all of the success of full-screen fallback.
- The main measured win is bounded visual context: the contract-scoped path reduced estimated vision area by 92.6%.
- Median latency was essentially unchanged because both systems still execute through the same GUI path.
- Mean latency was lower for contract-scoped fallback in this compact run, but that should be treated as secondary until the full-stack measurements are done.

### M4: Full Local Stack Budget and Stability - PASSED

Source:

- `results/safe_route/remote_stack/stack_results.json`

Setup:

- 1x RTX 4090
- Real runtime components loaded together on `cuda:0`:
  - VLM: `Qwen/Qwen2-VL-7B-Instruct`
  - STT: `facebook/wav2vec2-base-960h`
  - TTS: `facebook/mms-tts-eng`
- Mixed workload:
  - routine API-covered task
  - forced GUI-fallback task
  - blocked red-zone safety task

| Metric | Measured Value |
|---|---:|
| Peak VRAM | 17,701 MB |
| Average sampled VRAM | 13,205.7 MB |
| OOM count | 0 |
| API task TTFA | 1 ms |
| Mean user-visible cycle latency | 662.8 ms |
| Forced GUI-fallback cycle latency | 1904.5 ms |
| Blocked safety cycle latency | 36.5 ms |
| Warmup STT probe | 108 ms |
| Warmup TTS probe | 215 ms |
| Warmup VLM probe | 771 ms |

Interpretation:

- The full local multimodal stack fit within the paper's `<22 GB` target with about `4.3 GB` of remaining headroom and no OOM.
- The API-covered actuation path stayed well inside the `<150 ms` requirement even while the real VLM, STT, and TTS models were resident on the same GPU.
- Forced GUI fallback remained slow at about `1.9 s` per cycle, which reinforces the paper's core architecture claim: the practical path is API-first routing with bounded fallback, not frequent visual control.
- This run used `transformers` FP16 runtime models rather than the planned AWQ + vLLM serving stack, so it is valid evidence for C4 and a conservative memory-fit result, but not yet the final optimized serving configuration.

### M5: Held-Out Paraphrase and API-Gap Generalization - PASSED

Sources:

- `results/safe_route/remote_generalization/generalization_results.json`
- `results/safe_route/remote_generalization/held_out_cases.json`
- `results/safe_route/remote_generalization/api_gap_cases.json`

Benchmark scope:

- Held-out paraphrase/task suite:
  - 10 held-out tasks spanning navigation, media, climate, phone, messages, settings, and vehicle
  - Prompts rewritten away from the original benchmark wording
  - Compared systems:
    - `api_only`
    - `hybrid`
    - `safe_route`
    - `gui_only`
- Paraphrased API-gap suite:
  - 7 API-disabled cases, one per major category
  - Compared systems:
    - `no_fallback`
    - `full_screen_fallback`
    - `contract_scoped_fallback`

Held-out task results:

| System | Success Rate | Median TTFA / Latency | Mean TTFA / Latency | Mean Screenshots | Mean Vision Pixels |
|---|---:|---:|---:|---:|---:|
| API-only | 100.0% | 1.0 ms | 0.8 ms | 0.0 | 0 |
| Hybrid | 100.0% | 1.0 ms | 0.8 ms | 0.0 | 0 |
| SafeRoute | 100.0% | 1.5 ms | 1.7 ms | 0.0 | 0 |
| GUI-only | 20.0% | 10,142.5 ms | 9,492.6 ms | 1.0 | 2,073,600 |

API-gap paraphrase results:

| System | Success Rate | Median TTFA / Latency | Mean TTFA / Latency | Mean Vision Pixels | Fallback Invocation |
|---|---:|---:|---:|---:|---:|
| No fallback | 0.0% | 0 ms | 0.0 ms | 0 | 0.0 |
| Full-screen fallback | 100.0% | 1157 ms | 2306.86 ms | 2,073,600 | 1.0 |
| Contract-scoped fallback | 100.0% | 1145 ms | 2340.29 ms | 153,600 | 1.0 |

Key comparison:

- Held-out SafeRoute success stayed at `100%` with `0` screenshots.
- Held-out GUI-only success fell to `20%`.
- API-gap success gap between contract-scoped and full-screen fallback stayed at `0.0` points.
- Vision-area reduction versus full-screen fallback remained `92.6%`.

Interpretation:

- The typed contract layer did not collapse on the held-out operations: SafeRoute kept full held-out success while staying in the low-millisecond range.
- The screenshot-native baseline degraded sharply on the held-out suite, which strengthens the practical case for API-routed execution over vision-native control.
- On paraphrased API-gap requests, contract-scoped fallback preserved full-screen fallback success while keeping the same bounded-vision advantage seen in M3.
- This closes the bridge-stage generalization gap for C1 and C3, though a true DeBERTa/NLI safety baseline remains useful polish for C2.

### M6: Qwen2-VL Processor Token Accounting - PASSED

Source:

- `results/safe_route/remote_token_accounting/token_accounting_results.json`

Benchmark scope:

- Processor-only Qwen2-VL accounting using `Qwen/Qwen2-VL-7B-Instruct`.
- No model weights are loaded in this stage.
- Compares a 1920 x 1080 full-screen cockpit probe against a 480 x 320 contract-scoped ROI probe.

| Probe | Raw Pixels | Total Input Tokens | Effective Image Tokens | Image Grid |
|---|---:|---:|---:|---|
| Full screen | 2,073,600 | 2,724 | 2,691 | `[1, 78, 138]` |
| Contract ROI | 153,600 | 220 | 187 | `[1, 22, 34]` |

Key comparison:

- Qwen2-VL effective image-token reduction versus full-screen fallback: `93.05%`.
- Total input-token reduction versus full-screen fallback: `91.92%`.
- Raw visual-area reduction remains `92.59%`.

Interpretation:

- This directly supports the C3 context-pressure argument at the processor-token level: the scoped ROI reduces actual Qwen2-VL image tokens from `2691` to `187`.
- The measurement is intentionally processor-only, so it isolates context load without loading VLM weights or conflating the result with generation latency.
- It is a controlled probe that isolates processor behavior; M7 below adds dynamic fallback screenshots.

### M7: Dynamic Fallback Screenshot Token Trace - PASSED

Source:

- `results/safe_route/remote_dynamic_token_trace/dynamic_token_trace_results.json`
- `results/safe_route/remote_dynamic_token_trace/*.png`

Benchmark scope:

- 7 fallback-suite cases after real cockpit case setup.
- For each case, captures the actual 1280 x 720 cockpit screenshot and a deterministic 480 x 320 contract ROI crop from the same screen.
- Uses `Qwen/Qwen2-VL-7B-Instruct` processor only; model weights are not loaded.

| Metric | Full Screen | Contract ROI |
|---|---:|---:|
| Cases | 7 | 7 |
| Aggregate pixels | 6,451,200 | 1,075,200 |
| Aggregate effective image tokens | 8,372 | 1,309 |
| Mean effective image tokens / case | 1,196 | 187 |
| Aggregate total input tokens | 8,603 | 1,540 |

Key comparison:

- Dynamic visual-area reduction versus actual 1280 x 720 screenshots: `83.33%`.
- Dynamic Qwen2-VL effective image-token reduction: `84.36%`.
- Dynamic total input-token reduction: `82.10%`.

Interpretation:

- This removes the previous C3 caveat that token accounting was only probe-based.
- On real fallback-suite screenshots, the contract ROI reduces Qwen2-VL image tokens from `1196` to `187` per case.
- The dynamic trace uses actual captured cockpit screens, but the ROI is still a deterministic 480 x 320 crop rather than a learned locator output.

## Claim Status After M0-M7

- `C1`: supported.
  - The API-covered SafeRoute path is well below the `<150 ms` target.
  - Under the full-stack M4 load, API task TTFA remained `1 ms` with VLM, STT, and TTS resident on the same 4090.
  - Routine-task success stayed at 100% on the current 20-task suite.
  - Held-out paraphrase/task generalization also stayed at 100% success with `1.5 ms` median TTFA and `0` screenshots.
  - Vision usage dropped from one full-screen screenshot per task to zero on the tested API-covered tasks.
- `C2`: partially supported.
  - On the expanded 34-case remote safety suite, SafeRoute achieved 0% unsafe red-zone execution and 100% decision accuracy.
  - Prompt-only reached 54.5% unsafe red-zone execution, and hybrid-no-gate reached 100%.
  - Learned-only and semantic-guard baselines avoided unsafe red-zone execution but over-restricted state-conditioned allow cases, especially yellow allow-cases.
  - This is stronger scoped safety evidence, but still not a broad functional-safety or DeBERTa/NLI generalization claim.
- `C3`: supported.
  - On the compact API-disabled suite and again on the paraphrased API-gap suite, contract-scoped fallback matched full-screen fallback success and reduced estimated vision area by 92.6%.
  - Processor-level Qwen2-VL accounting now shows a 93.05% effective image-token reduction for the 480 x 320 scoped ROI versus a 1920 x 1080 full-screen probe.
  - Dynamic fallback screenshot tracing shows an 84.36% effective image-token reduction and 82.10% total input-token reduction on the actual 7-case fallback suite.
- `C4`: supported.
  - On the M4 remote stack run, the real local stack peaked at `17,701 MB`, recorded `0` OOM, and preserved `1 ms` API TTFA on one RTX 4090.
  - The remaining caveat is engineering, not claim validity: the run used `transformers` FP16 runtime models rather than the planned AWQ + vLLM serving path.

## Gaps Before Review Loop

- The safety suite is now expanded from 18 to 34 cases and includes a semantic guardrail baseline, but a true DeBERTa/NLI learned guardrail remains future work.
- The dynamic token trace uses a deterministic center crop for the 480 x 320 contract ROI; a future learned ROI locator could make this more task-specific.
- Table 1 could still be polished with a stronger learned-risk or learned-router comparison if needed for reviewer comfort, but C1 itself is now covered.

## Next Step

Proceed to claim judgment or review loop; the bridge-stage must-runs are complete.
