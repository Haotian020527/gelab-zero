# Experiment Tracker

Last updated: 2026-04-09
Source of truth for new results: `results/safe_route/remote_sanity/`, `results/safe_route/remote_routine/`, `results/safe_route/remote_safety_expanded/`, `results/safe_route/remote_fallback/`, `results/safe_route/remote_stack/`, `results/safe_route/remote_generalization/`, `results/safe_route/remote_token_accounting/`, and `results/safe_route/remote_dynamic_token_trace/`

| Run ID | Milestone | Purpose | Status | Exit Criterion | Notes |
|---|---|---|---|---|---|
| S001 | M0 | Freeze action-contract schema and risk taxonomy | DONE | Contract fields and zone policy finalized | `schema_version=1.0`; zones: `green/yellow/red`; fallback policies: `allow/challenge/deny` |
| S002 | M0 | Gateway unit tests on seed red/yellow/green cases | DONE | All hard-safety unit tests pass | Remote sanity PASS: red blocks on bad gear, red requires 2FA, yellow challenges without confirmation |
| S003 | M0 | Re-run 3-task cockpit pilot with instrumentation | DONE | Latency, VRAM, and routing traces captured | Remote pilot PASS: SafeRoute 100% success, median 1 ms, 0 screenshots; GUI-only 33.3% success, median 1136 ms |
| S004 | M1 | Full routine-task benchmark on 20 cockpit tasks | DONE | Table 1 ready | Remote 20-task run: SafeRoute 100% success, median 1 ms; GUI-only 60% success, median 1178.5 ms |
| S005 | M2 | Build `CockpitSafeBench` prompt and hardware-state suite | DONE | Benchmark specification frozen | Expanded to 34 explicit-label cases with green/yellow/red zones, clean/paraphrase/attack/confirmed/hard-negative prompts, signal permutations, and 2FA permutations |
| S006 | M2 | Safety evaluation against learned-guardrail baselines | DONE | Table 2 ready | Original remote safety PASS on 18 cases; superseded by expanded S011 result for current C2 reporting |
| S007 | M3 | API-disabled fallback ablation | DONE | Table 3 ready | Remote fallback PASS: no-fallback 0%, full-screen 100%, contract-scoped 100%; vision area reduced by 92.6% with no success drop |
| S008 | M4 | Full local stack VRAM and stability run | DONE | Table 4 ready | Remote stack PASS: `Qwen2-VL-7B-Instruct` + `wav2vec2-base-960h` + `mms-tts-eng` + gateway peaked at `17,701 MB` with `0` OOM; API TTFA stayed at `1 ms` |
| S009 | M5 | Held-out paraphrase and API-gap generalization | DONE | Table 5 ready | Remote generalization PASS: held-out SafeRoute `100%` success with `1.5 ms` median TTFA; GUI-only `20%`; paraphrased API-gap contract-scoped fallback matched full-screen at `100%` success with `92.6%` less vision area |
| S010 | M6 | Qwen2-VL processor token accounting for full-screen versus scoped fallback | DONE | Token accounting ready | Remote token accounting PASS: full-screen probe `2691` effective image tokens, contract ROI `187`; image-token reduction `93.05%`, total input-token reduction `91.92%` |
| S011 | M2 polish | Expanded safety suite with semantic guardrail baseline | DONE | C2 table updated | Remote expanded safety PASS: 34 cases; SafeRoute decision accuracy `100%`, unsafe-red `0%`; prompt-only unsafe-red `54.5%`; hybrid-no-gate `100%`; semantic-guard unsafe-red `0%` but false non-allow on yellow allow-cases `100%` |
| S012 | M7 | Dynamic fallback screenshot token trace | DONE | C3 token trace ready | Remote dynamic trace PASS: 7 actual fallback screens; aggregate image tokens `8372 -> 1309` (`84.36%` reduction), total input tokens `8603 -> 1540` (`82.10%` reduction), actual screenshot-area reduction `83.33%` |

## Current Claim Status

- C1: SUPPORT
- C2: SUPPORT (SCOPED)
- C3: SUPPORT
- C4: SUPPORT

## Existing Evidence Already Available

- `results/idea_discovery_pilot/micro_latency_fixed.json`
  - Hybrid mean latency: 13.44 ms
  - API-only mean latency: 17.78 ms
  - GUI-only mean latency: 1293.33 ms
  - Hybrid/API success: 100%
  - GUI-only success: 33.3%
- `results/idea_discovery_pilot/sanity/sanity_results.json`
  - Deterministic replay and validators pass
- `results/safe_route/remote_sanity/sanity_results.json`
  - Gateway unit checks: PASS
  - 3-task pilot: SafeRoute 100% success, median 1 ms, 0 screenshots
  - 3-task pilot GUI-only: 33.3% success, median 1136 ms, 1 screenshot/task
- `results/safe_route/remote_routine/routine_results.json`
  - 20-task routine: SafeRoute 100% success, median 1 ms, 0 screenshots
  - 20-task routine GUI-only: 60% success, median 1178.5 ms, 1 screenshot/task
- `results/safe_route/remote_safety_expanded/safety_results.json`
  - 34-case expanded `CockpitSafeBench`: SafeRoute unsafe red-zone execution = 0%, decision accuracy = 100%
  - Prompt-only baseline: unsafe red-zone execution = 54.5%, decision accuracy = 50.0%
  - Hybrid without gate: unsafe red-zone execution = 100%
  - Learned-only baseline: 0% unsafe red-zone execution but 100% false non-allow on yellow allow-cases
  - Semantic-guard baseline: 0% unsafe red-zone execution and 0% false block on green, but 100% false non-allow on yellow allow-cases
- `results/safe_route/remote_fallback/fallback_results.json`
  - 7-category API-disabled fallback suite: contract-scoped fallback success = 100%
  - Full-screen fallback success = 100%, no-fallback success = 0%
  - Estimated vision area reduction versus full-screen fallback = 92.6%
- `results/safe_route/remote_stack/stack_results.json`
  - Full local stack PASS on 1x RTX 4090 with real VLM, STT, TTS, and gateway loaded together
  - Peak VRAM = 17,701 MB, average sampled VRAM = 13,205.7 MB, OOM count = 0
  - API task TTFA = 1 ms under full-stack load
  - Warmup probe latencies: STT = 108 ms, TTS = 215 ms, VLM = 771 ms
  - Mixed-workload cycle latency: routine API = 47.5 ms, blocked safety = 36.5 ms, forced GUI fallback = 1904.5 ms
- `results/safe_route/remote_generalization/generalization_results.json`
  - Held-out paraphrase/task suite PASS: SafeRoute `100%` success, median TTFA `1.5 ms`, `0` screenshots on 10 held-out tasks
  - Held-out GUI-only baseline: `20%` success, median latency `10,142.5 ms`, one full-screen screenshot per task
  - Paraphrased API-gap suite: no-fallback `0%`, full-screen fallback `100%`, contract-scoped fallback `100%`
  - Vision-area reduction versus full-screen fallback stayed `92.6%` on the held-out API-gap subset
- `results/safe_route/remote_token_accounting/token_accounting_results.json`
  - Processor-only `Qwen/Qwen2-VL-7B-Instruct` token accounting PASS
  - Full-screen 1920 x 1080 probe: `2691` effective image tokens and `2724` total input tokens
  - Contract-scoped 480 x 320 ROI probe: `187` effective image tokens and `220` total input tokens
  - Effective image-token reduction versus full screen: `93.05%`
- `results/safe_route/remote_dynamic_token_trace/dynamic_token_trace_results.json`
  - Dynamic fallback-suite screenshot token trace PASS on 7 actual cockpit screens
  - Full actual screenshots: aggregate `8372` effective image tokens, `8603` total input tokens
  - Contract ROI crops: aggregate `1309` effective image tokens, `1540` total input tokens
  - Effective image-token reduction: `84.36%`; total input-token reduction: `82.10%`

## Immediate Next Runs

1. Bridge-stage must-runs are complete.
2. Optional polish runs: true DeBERTa/NLI safety baseline or human-written adversarial prompts if needed for review.
3. Preferred next step: `result-to-claim` or review loop.

## Notes

- The current cockpit router scaffold exists, but full natural-language cockpit tool coverage is still incomplete.
- Current M0-M7 plus expanded safety results support C1, scoped C2, C3, and the one-4090 practicality claim behind C4.
- The earlier `peak_vram_mb=116` benchmark-process measurement must still not be cited for C4; only `results/safe_route/remote_stack/stack_results.json` measures the real multimodal stack.
- The current C2 table now includes both Naive Bayes and semantic guardrail baselines, but not a true DeBERTa/NLI model baseline.
- The fallback and generalization benchmarks report estimated visual area, supplemented by both controlled Qwen2-VL processor accounting and dynamic fallback screenshot token tracing.
- The stack result used `transformers` FP16 runtime models instead of the originally planned AWQ + vLLM stack, so the memory fit result is conservative but not yet an implementation of the final optimized serving design.
