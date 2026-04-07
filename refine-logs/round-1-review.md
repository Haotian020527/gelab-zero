# Round 1 Review

**Overall Score**: 6.7/10
**Verdict**: REVISE

## Scores
| Dimension | Score | Status |
|-----------|-------|--------|
| Problem Fidelity | 8/10 | ✅ |
| Method Specificity | 6/10 | ❌ Needs fix |
| Contribution Quality | 7/10 | ✅ |
| Frontier Leverage | 6/10 | ❌ Needs fix |
| Feasibility | 6/10 | ❌ Needs fix |
| Validation Focus | 8/10 | ✅ |
| Venue Readiness | 6/10 | ❌ Needs fix |

## Key Action Items
1. **[HIGH] Method Specificity**: Make dataset unit a `switch event`, not full episode. Capture pre-switch checkpoint and replay 3 branches (hybrid/API-only/GUI-only). Replace raw action+api_response with canonicalized expected postcondition.
2. **[HIGH] Feasibility**: Reduce to 15-20 audited replayable tasks with strong checkpoints, not 50 loosely controlled.
3. **[HIGH] Venue Readiness**: Commit to NeurIPS D&B; make HybridStress the main contribution, CMV as reference detector, recovery as utility study.
4. **[MEDIUM-HIGH] Frontier Leverage**: Use pretrained VLM judge as main baseline/teacher, distill into lightweight CMV. This is the natural FM-era move.

## Simplification Opportunities
- Event-centric benchmark (switch events, not episodes)
- Verifier input: (pre_image, post_image, expected_postcondition)
- Fixed minimal recovery protocol
- Drop bespoke cross-attention unless it beats simpler scorer

## Modernization Opportunities
- VLM judge as main baseline + distillation teacher
- LLM/VLM for canonicalizing API→postcondition
- No RL or diffusion needed

## Drift Warning
- No routing/planning/RL expansion
- Keep counterfactual definition strict
- Main claim = diagnosis/measurement, not end-to-end success
