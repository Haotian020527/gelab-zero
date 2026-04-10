# Research Proposal: HybridStress — Diagnosing and Mitigating Modality-Boundary Failures in Hybrid API/GUI Agents

## Problem Anchor
- **Bottom-line problem**: Hybrid API/GUI agents (like gelab-zero) silently fail at modality boundaries — when execution switches between API and GUI paths, the application state can become inconsistent without any error signal, causing cascading downstream failures.
- **Must-solve bottleneck**: No existing benchmark or method specifically detects or measures modality-boundary failures. Current systems use heuristic routing with no verification at switch points, leading to an unmeasured class of failures.
- **Non-goals**: (1) Building a better general GUI agent. (2) Improving single-modality API or GUI performance. (3) Replacing MCP protocol. (4) Full end-to-end agent training.
- **Constraints**: 1x RTX 4090; AndroidWorld as primary test environment; 4-6 weeks timeline; target NeurIPS 2025 Datasets & Benchmarks track or ICML main track.
- **Success condition**: (1) Demonstrate that boundary-specific failures account for a non-trivial fraction (>15%) of hybrid agent failures. (2) Show that a simple verifier trained on synthetic faults transfers to natural failure traces. (3) Show that verification-triggered recovery improves task success without excessive latency overhead.

## Technical Gap

Current hybrid API/GUI architectures operate with a critical blind spot: they assume that a successful API call and a successful GUI action produce equivalent, consistent application states. This assumption is violated in practice due to:
- **Temporal skew**: API responses and GUI rendering operate on different timescales
- **Phantom acknowledgments**: APIs may report success before the app fully processes the command
- **State divergence**: API-side state and GUI-side visual appearance can diverge under concurrent execution

Existing benchmarks (AndroidWorld, OSWorld, WebArena) evaluate end-to-end task success but cannot isolate **where** in the modality pipeline failures originate. MAS-FIRE injects faults into multi-agent systems but is not designed for API↔GUI boundary failures. GTArena focuses on GUI defects without cross-modal considerations.

The gap is both diagnostic (no instrument to measure boundary failures) and methodological (no mechanism to detect and recover from them at runtime).

## Method Thesis
- **One-sentence thesis**: Hybrid agents fail silently at modality boundaries, and a lightweight cross-modal consistency verifier trained on systematically injected boundary faults can detect and recover from these failures with controllable latency-accuracy tradeoff.
- **Why this is the smallest adequate intervention**: We do not retrain the agent, change the routing policy, or modify the base models. We add a single binary verification step at switch points.
- **Why this route is timely**: As MCP-based hybrid architectures become the production standard, understanding and mitigating their unique failure modes is critical — analogous to how crash testing followed automotive standardization.

## Contribution Focus
- **Dominant contribution**: HybridStress benchmark — a modality-boundary fault taxonomy and injection framework for hybrid API/GUI agents, validated against real failure traces.
- **Supporting contribution**: Cross-Modal Verifier (CMV) — a lightweight consistency checker at modality switch points that detects silent desynchronization and triggers recovery.
- **Explicit non-contributions**: (1) A new routing algorithm (the router is NOT the contribution). (2) A new GUI agent architecture. (3) End-to-end agent training method.

## Proposed Method

### Complexity Budget
- **Frozen / reused backbone**: gelab-zero's cockpit_router, MCP server, ADB backend, all unmodified
- **New trainable components**: 1 — Cross-Modal Verifier (CMV), a binary classifier (~10M params)
- **Tempting additions intentionally not used**: (1) Learned routing policy. (2) World model for state prediction. (3) Hierarchical planning. (4) RL-based policy refinement.

### System Overview
```
Task → cockpit_router (unchanged) → {API path | GUI path}
                                          ↓
                              [modality switch detected]
                                          ↓
                    CMV: verify(pre_screenshot, action, api_response, post_screenshot)
                                          ↓
                              {consistent → continue}
                              {inconsistent → recovery protocol}
                                          ↓
                              Recovery: re-screenshot → retry → GUI-only fallback
```

### Core Mechanism: Cross-Modal Verifier (CMV)

**Input**: Tuple of (pre_switch_screenshot, action_description, api_response_json, post_switch_screenshot)

**Output**: Binary {consistent, inconsistent} with calibrated confidence score

**Architecture**:
- Pre/post screenshots: frozen SigLIP ViT-B/16 encoder → 768-dim visual embeddings
- Action + API response: frozen text encoder (same ViT text tower) → 768-dim text embedding
- Cross-attention layer (2 heads, 768-dim) between visual diff features and text features
- Binary classification head with temperature-scaled calibration

**Training signal**: Binary cross-entropy on HybridStress-generated positive/negative pairs

**Training data construction**:
- Positive (consistent): natural switch events from successful gelab-zero rollouts
- Negative (inconsistent): same events with injected boundary faults (see taxonomy below)
- Ratio: 1:1 positive:negative, with augmentation via fault combination

**Why this is the main novelty (method-side)**: Existing success detectors and state estimators operate within a single modality. CMV specifically targets the cross-modal boundary, using both pre-switch and post-switch observations plus the action semantics to assess consistency. The pre-switch screenshot is critical — it provides the "expected state" against which the post-switch state is compared.

### HybridStress Benchmark: Boundary Fault Taxonomy

**4 fault types** (Schema Drift removed per review):

| Fault Type | Description | Injection Method | Expected Effect |
|------------|-------------|------------------|-----------------|
| **Stale Screenshot** | GUI perception lags behind API-driven state change | Serve cached screenshot from t-k instead of t | Agent operates on outdated visual context |
| **Phantom Ack** | API reports success, but app didn't fully execute | Intercept API response, inject success code before completion | Agent proceeds based on false success signal |
| **Partial Rollback** | API undo succeeds server-side, but GUI shows pre-undo state | Inject rollback at API level without triggering GUI refresh | State divergence between API and GUI |
| **Temporal Mismatch** | API and GUI operate at different effective timestamps | Introduce variable delay (100ms-2s) between API execution and GUI observation | Transient inconsistency that may or may not self-resolve |

**Injection mechanism**: Wrapper around gelab-zero's mcp_backend_implements.py that intercepts ADB commands and API responses to inject controlled faults at switch points.

**Benchmark structure**:
- 50 AndroidWorld tasks × 4 fault types × 3 severity levels = 600 fault-injected episodes
- Plus 50 clean episodes for baseline comparison
- Each episode annotated with: fault location, fault type, whether failure is boundary-specific (operational counterfactual definition below)

**Operational counterfactual definition of boundary-specific failure**:
A failure is boundary-specific if the same subtask succeeds when executed purely in API mode AND purely in GUI mode from the same pre-switch state, but fails when execution crosses the boundary. This is evaluated by running counterfactual single-modality rollouts from checkpointed states.

### Real-Trace Validation (Critical)

To address the key reviewer concern about ecological validity:
1. Collect 200+ natural switch events from real gelab-zero rollouts on 10 held-out apps
2. Two annotators label each event: consistent/inconsistent, fault type (if applicable), transient/persistent
3. Report inter-annotator agreement (target κ > 0.7)
4. Evaluate CMV (trained only on synthetic HybridStress data) on these natural traces
5. Compare against baselines: API-status heuristic, fixed-delay+re-screenshot, OCR postcondition check

### Failure Modes and Diagnostics
- **False positive (CMV)**: flagging consistent states as inconsistent → unnecessary recovery, increased latency
  - Detect via: false alarm rate monitoring; mitigate via: confidence threshold tuning
- **False negative (CMV)**: missing actual inconsistency → cascading failure
  - Detect via: downstream task failure correlated with switch events; mitigate via: lowering confidence threshold
- **Shortcut learning**: CMV learns injector artifacts rather than real inconsistency
  - Detect via: real-trace transfer evaluation; mitigate via: diverse injection methods, held-out injector types
- **Latency overhead**: CMV verification adds ~200ms per switch point
  - Mitigate via: selective verification (only at high-risk switch points based on action type)

### Novelty and Elegance Argument
- **Closest work**: (1) VLM Success Detectors (Du et al., 2023) — post-action success detection, but single-modality and no boundary-specific focus. (2) Latent State Estimation (2024) — hidden state estimation for UI agents, but not at cross-modal boundaries. (3) MAS-FIRE (2026) — fault injection for multi-agent systems, but no modality-boundary taxonomy.
- **Exact difference**: We are the first to (a) define and measure modality-boundary failures as a distinct failure class, (b) build a controlled injection framework targeting specifically these failures, and (c) validate that synthetic boundary faults transfer to real traces.
- **Why this is focused**: One benchmark + one verifier. No routing changes, no architecture changes, no RL training. The method is additive and modular.

## Claim-Driven Validation Sketch

### Claim 1 (Primary): Modality-boundary failures are a distinct, common, and measurable phenomenon in hybrid API/GUI agents.
- **Minimal experiment**: Run gelab-zero on AndroidWorld, classify failures as boundary-specific vs within-modality using counterfactual definition, report prevalence.
- **Baselines**: Random fault attribution, within-modality-only analysis.
- **Metric**: Boundary failure prevalence (%), inter-annotator agreement (κ)
- **Expected evidence**: >15% of failures are boundary-specific

### Claim 2 (Supporting): A lightweight verifier trained on synthetic boundary faults can detect real boundary inconsistencies and improve task success.
- **Minimal experiment**: Train CMV on HybridStress, evaluate on natural traces, then run online with recovery.
- **Baselines**: API-status heuristic, fixed-delay+re-screenshot, OCR postcondition check, no verification
- **Metric**: AUPRC, AUROC, ECE, task success delta, latency delta, false alarm rate
- **Expected evidence**: CMV AUPRC > 0.7 on natural traces; task success improvement > 3% with < 15% latency increase

## Experiment Handoff Inputs
- **Must-prove claims**: Boundary failures exist and are common; CMV detects them; recovery helps
- **Must-run ablations**: CMV vs blind retry; CMV input ablation (pre-screenshot necessity); real-trace transfer
- **Critical datasets**: AndroidWorld, 10 held-out apps for natural traces
- **Highest-risk assumptions**: (1) Boundary failures are common enough to matter. (2) Synthetic faults transfer to real distribution.

## Compute & Timeline Estimate
- **CMV training**: ~8 GPU-hours on 1x 4090 (small classifier on frozen features)
- **HybridStress episodes**: ~100 GPU-hours for 650 episodes (mostly emulator time)
- **Natural trace collection**: ~40 GPU-hours (200+ rollouts)
- **Evaluation**: ~20 GPU-hours
- **Total**: ~170 GPU-hours ≈ 1 week of continuous 4090 time
- **Data/annotation**: 2 annotators × 200 events × 5 min/event ≈ 33 person-hours
- **Timeline**: 4-5 weeks (data collection: 1w, CMV training: 0.5w, evaluation: 1w, natural trace validation: 1w, writing: 1w)
