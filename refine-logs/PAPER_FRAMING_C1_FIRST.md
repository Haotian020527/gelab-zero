# Paper Framing (SafeRoute-Cockpit, Claim-Safe)

Date: 2026-04-09
Target: ICLR/NeurIPS/ICML style empirical systems paper

## 1) One-Sentence Positioning

SafeRoute-Cockpit turns cockpit agents from screenshot-native GUI controllers into contract-mediated, API-first agents with a deterministic safety gateway and a scoped GUI fallback, reducing action latency and visual context load while preserving hard safety boundaries.

## 2) Claim Guardrails (Must Follow)

### Safe claims

- C1 is supported: API-first SafeRoute completes all routine cockpit tasks in the current benchmark with near-millisecond time-to-first-action and zero routine screenshots.
- C2 is supported under a scoped benchmark claim: the deterministic gateway blocks unsafe execution in the expanded 34-case suite, while prompt-only/no-gate baselines fail unsafely and semantic/text guardrails over-restrict state-conditioned allow cases.
- C3 is supported at the benchmark level: contract-scoped fallback recovers API-gap tasks while reducing estimated visual area by 92.6%, Qwen2-VL effective image tokens by 93.05% on controlled probes, and dynamic fallback screenshot image tokens by 84.36%.
- C4 is supported: a real local VLM/STT/TTS/gateway stack fits on one RTX 4090 in the current probe with a measured peak below the 22 GB operational budget.
- The method should be framed as an agent-control and safety architecture, not as a new foundation GUI model.

### Avoid or weaken wording

- Do not claim ISO 26262 compliance; claim alignment with deterministic safety-boundary principles only.
- Do not claim AWQ/vLLM deployment unless those exact serving components are measured in the reported experiment.
- Do not call the GUI-only baseline state-of-the-art; frame it as an edge-local screenshot-native baseline.
- Do not claim broad natural-language safety generalization until a true DeBERTa/NLI baseline and larger human-written paraphrase suite are added.
- Do not imply all vehicle functions are covered; the benchmark currently covers cockpit UI/API tasks and scripted safety cases.

## 3) Abstract Draft (Claim-Safe)

Large vision-language agents promise general cockpit control, but screenshot-native interaction is a poor default for edge vehicles: visual grounding adds seconds of latency, repeated high-resolution screenshots inflate context load, and probabilistic self-reflection cannot provide a dependable safety boundary for vehicle actions. We present SafeRoute-Cockpit, a hybrid cockpit-agent architecture that compiles intents into action contracts, routes executable operations through a local VSS-style API, and places a deterministic gateway before execution. GUI grounding is retained only as a scoped fallback when an API is missing. Across routine cockpit tasks, SafeRoute completes all tasks with near-millisecond first actions and no routine screenshots, while an edge-local GUI-only baseline is slower and less reliable. In an expanded 34-case safety suite, the gateway reaches 0% unsafe red-zone execution and 100% decision accuracy; prompt-only/no-gate baselines allow unsafe operations, while semantic/text guardrails remain over-restrictive on state-conditioned allow cases. For API-gap tasks, scoped fallback matches full-screen fallback success while reducing estimated visual area by 92.6%; Qwen2-VL processor accounting shows a 93.05% effective image-token reduction on controlled probes and an 84.36% reduction on actual fallback screenshots. A full local stack probe with Qwen2-VL, wav2vec2, MMS-TTS, and the gateway fits within a single RTX 4090 budget. These results support API-first routing plus deterministic middleware as a practical alternative to pure GUI cockpit agents, while leaving broader safety-language coverage as the main remaining limitation.

## 4) Contribution Statements

1. A contract-mediated cockpit agent architecture that separates generative intent parsing from deterministic safety and execution.
2. An API-first routing protocol for cockpit tasks that avoids visual grounding on routine operations and preserves GUI fallback only for API gaps.
3. A deterministic red/yellow/green safety gateway with explicit hardware and biometric preconditions before high-risk execution.
4. A local edge evaluation showing latency, visual-load, safety, fallback, generalization, and full-stack memory behavior under a single RTX 4090 budget.

## 5) Section-by-Section Writing Plan

## Section 1: Introduction

- Problem: pure GUI/VLM cockpit agents are too slow, memory-heavy, and unsafe as direct vehicle controllers.
- Gap: current GUI-agent papers optimize visual operation, not deterministic vehicle safety boundaries or API-first cockpit routing.
- Main take-away: most routine cockpit actions should not require screenshots; the VLM should be a fallback, not the default executor.
- Honest scope: the work validates a cockpit benchmark and local stack probe, not a production-certified vehicle controller.

## Section 2: Related Work

- GUI agents and multimodal computer control.
- Vehicle APIs, VSS-style signal abstractions, and cockpit automation.
- Runtime verification, guardrails, and safety middleware.
- Edge multimodal serving and context/memory pressure.

## Section 3: Method (SafeRoute-Cockpit)

- Action Contract schema.
- Contract compiler and API-first routing.
- Deterministic safety gateway with red/yellow/green zones.
- Contract-scoped GUI fallback.
- Local edge deployment stack.

## Section 4: Experimental Setup

- Cockpit task suite and held-out generalization tasks.
- Baselines: API-only, hybrid executor, edge-local GUI-only, prompt-only safety, learned-only Naive Bayes, semantic guardrail, no-gate hybrid, full-screen fallback.
- Metrics: success, time-to-first-action, screenshot count, visual area, unsafe execution rate, challenge accuracy, VRAM peak.
- Canonical evidence paths under `results/safe_route/`.

## Section 5: Results

- 5.1 C1 routine routing: SafeRoute success and latency versus GUI-only.
- 5.2 C2 safety boundary: deterministic gateway versus prompt-only/no-gate/learned-only/semantic-guard variants.
- 5.3 C3 fallback: scoped fallback success and visual-load reduction.
- 5.4 C4 full stack: local RTX 4090 memory and latency probe.
- 5.5 Generalization: held-out routine tasks and paraphrased API-gap tasks.

## Section 6: Discussion and Limitations

- C2 still needs a true NLI/DeBERTa baseline for broad language-generalization claims.
- Current GUI-only baseline is useful but not a claim against all GUI-agent systems.
- Full-stack memory is measured with FP16 transformers, not AWQ/vLLM production serving.
- Dynamic token tracing uses deterministic ROI crops, not a learned ROI locator.
- Safety claims are architectural and empirical, not certification claims.

## Section 7: Conclusion

- Re-state API-first routing as the default for cockpit agents.
- Emphasize deterministic safety isolation before execution.
- Position scoped GUI fallback as a bounded recovery path rather than a primary control loop.
