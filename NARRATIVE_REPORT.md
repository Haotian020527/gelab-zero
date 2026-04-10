# Narrative Report: SafeRoute-Cockpit

Date: 2026-04-09
Target venue class: ICLR/NeurIPS/ICML

## Problem

Smart-cockpit agents are brittle when treated as screenshot-native GUI users. Pure GUI/VLM control is too slow for dynamic IVI states, consumes visual context aggressively, and leaves safety-critical authorization inside probabilistic model behavior.

## Method

SafeRoute-Cockpit routes cockpit commands through typed `Action Contracts` before actuation. Each contract records the intent, risk zone, required vehicle signals, 2FA or confirmation requirements, allowed API paths, GUI fallback policy, and postconditions.

Execution is gated by a deterministic middleware outside the LLM/VLM:

1. Compile the request and target task into an action contract.
2. Check vehicle-signal preconditions and 2FA or explicit confirmation.
3. Execute authorized covered actions through API-first cockpit tools.
4. Use GUI fallback only when the contract permits it.
5. Verify postconditions and log the route decision.

## Current Empirical Support

Canonical evidence is in `results/safe_route/`.

| Claim | Status | Main Evidence |
|---|---|---|
| C1: API-first contract routing is faster and lighter than screenshot-native control | SUPPORT | 20 routine tasks: SafeRoute 100% success, median 1 ms, 0 screenshots; GUI-only 60%, median 1178.5 ms. Held-out 10-task suite: SafeRoute 100%, median 1.5 ms; GUI-only 20%, median 10142.5 ms. |
| C2: Deterministic signal and 2FA gating prevents unsafe high-risk execution under tested attacks/states | SUPPORT (SCOPED) | 34-case expanded safety suite: SafeRoute 0% unsafe red-zone execution and 100% decision accuracy; prompt-only unsafe red-zone 54.5%; hybrid-no-gate 100%. Semantic guardrail also reaches 0% unsafe red-zone but fails state-conditioned authorization with 100% false non-allow on yellow allow-cases. |
| C3: Contract-scoped GUI fallback preserves API-gap coverage with bounded visual context | SUPPORT | In-domain and paraphrased API-gap suites: contract-scoped fallback matched full-screen fallback at 100% success while reducing estimated vision area by 92.6%. Qwen2-VL controlled probe accounting reduces effective image tokens from 2691 to 187; dynamic fallback screenshots reduce aggregate image tokens from 8372 to 1309. |
| C4: Full local multimodal stack is practical on one RTX 4090 | SUPPORT | Qwen2-VL-7B, wav2vec2 STT, mms-tts, and gateway loaded together; peak VRAM 17,701 MB, 0 OOM, API TTFA 1 ms. |

## Submission Framing

The defensible paper is an architecture-plus-evaluation paper:

- Primary result: deterministic, signal-grounded authorization plus API-first routing makes cockpit agents faster and safer than screenshot-native control under the evaluated conditions.
- Supporting result: contract-scoped fallback preserves coverage without returning to full-screen rolling visual context.
- Deployment result: the full local stack fits on one 24 GB RTX 4090.

The paper must not claim:

- ISO 26262 certification or full automotive functional-safety compliance.
- A new foundation model, generic GUI-agent benchmark, or novel quantization method.
- Broad real-world safety beyond the tested command/state/prompt suite.

## Remaining Review Risks

1. C2 is stronger after the expanded 34-case suite and semantic guardrail baseline, but it is still scoped evidence rather than broad functional-safety validation.
2. Reviewers may still ask for a true DeBERTa/NLI baseline or human-written adversarial prompts.
3. Dynamic token tracing now covers the fallback suite, but the 480 x 320 ROI is a deterministic crop rather than a learned locator output.
4. GUI-only baseline performance is weak on held-out tasks; the paper should report this honestly as an edge-local screenshot-native baseline rather than overstate it as a state-of-the-art GUI agent.

## Immediate Next Step

Run result-to-claim or a critical review loop. If more work is needed before writing, prioritize:

1. True DeBERTa/NLI safety baseline.
2. Extra safety paraphrases or human-written adversarial prompts.
3. A task-specific learned ROI locator if the fallback section becomes a larger paper component.
