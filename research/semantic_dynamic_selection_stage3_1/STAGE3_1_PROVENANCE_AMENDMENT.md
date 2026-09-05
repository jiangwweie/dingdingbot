# Stage-3.1 Independent Review and Provenance Amendment

Recorded: 2026-09-06. Classification: **post-result provenance documentation**.
Source: Owner-supplied independent review, accepted in the active design task.

## Frozen evidence identity

| Evidence | Exact identity |
| --- | --- |
| Protocol commit | `9907153b94b2603535c9c846611ed90b0a2ea112` |
| Pre-result correction / run commit | `46d7fecc9222bbbf1e85308410be2924b34cfdff` |
| Results commit | `f65d72fa92580de4b8c0323f4106d5975b97f4eb` |
| Original Protocol SHA-256 | `7e3ab69dce47cb583efc041195cd82fcbbd7acff68c3dfbb03f61bbbcb73ab17` |
| Original replay manifest SHA-256 | `289c75428742c1bebfa8b6585aaed82a8af0ae7b1b1feefcc482f017911f305e` |

The original PROTOCOL.md, results, report and manifest remain unchanged. This
amendment is an additional audit record, not an amendment backdated into the
Protocol commit and not a new Replay run.

## Recommendation-policy clarification

The Protocol text states that the smallest of Top8 / Top12 / Top16 must satisfy
80% Good Event Capture and no persistent clear adverse selection. It does **not**
explicitly specify a fallback when none passes that capture floor. The initial
implementation returned `NO_COMPATIBLE_CARDINALITY` in that case.

Commit `46d7fecc9222bbbf1e85308410be2924b34cfdff`, before the committed result
artifacts, changed the recommendation code to retain Top16 when Top8 / Top12
do not pass and Top16 does not show persistent clear adverse selection:

> If Top8 and Top12 fail the 80% Good Event Capture floor, Top16 may be retained
> as a compatibility fallback provided Top16 does not show persistent clear
> adverse selection. This fallback does **not** mean the 80% capture floor
> passed. Evidence status remains `TOP16_FALLBACK_CAPTURE_BELOW_FLOOR`.

This is the correction authority for CPM and BRF2 recommendations. Git history
establishes the correction preceded the committed results; it does not prove
that no exploratory values had ever been seen. The report's broad statement
that cardinality was selected by the pre-registered 80% floor must be read
with this explicit exception. Do not describe the record as perfect two-phase
pre-registration.

The finding is **P1 PROVENANCE DOCUMENTATION DEFECT** accepted with this note.
It concerns the recommendation policy, not a change to frozen Replay inputs,
features, Top8/12/16 measurements, Outcome semantics, rank parity or turnover.

## Accepted design inputs and evidence limits

| Strategy | Feature | Entry / retain rank | Evidence interpretation |
| --- | --- | --- | --- |
| CPM | Absolute Directional Efficiency V1 | 16 / 16 | Capture 62.6%, below floor; no longer persistently adverse under the frozen rejection rule; improvement not established |
| MPG | Persistent Leadership Score V1 | 12 / 16 | Meaningful discrimination; Top12 capture 86.5%; effects -0.040 / -0.621 with excluded resolved N=4 / 3; weak, adverse-looking but sparse |
| MI | Positive Impulse Recency V0 | 16 / 16 | Capture 86.7%; sparse comparison; no empirical alpha claim |
| BRF2 | Residual Extension V0 | 16 / 16 | Capture 74.4%, below floor; approximately neutral quality comparison |
| SOR | Existing Dynamic V0 | 7 / 7 | Existing Decimal Golden and production contract remain unchanged |

MPG hysteresis means union of new rank <=12 members and previous selected
members still ranked <=16. Actual membership can be 12..16 on a complete
eligible panel; it is not fixed-capacity Top12. The reported 36.2% turnover
reduction is a membership diagnostic, not a new outcome or profitability test.

Sources: original `PROTOCOL.md`, `core.py`, `analyze.py` and `artifacts/` at the
commits above; Owner-supplied independent review. No statistics were rerun for
this amendment.

## Authority after review

```text
STAGE3_1_REVIEW = ACCEPTED_WITH_PROVENANCE_NOTE
research_status = STAGE3_1_FINAL_SEMANTIC_REVISION_COMPLETE
independent_review = ACCEPTED
further_feature_research = CLOSED
generic_selection_design_authority = ALLOWED_FOR_ELIGIBLE_STRATEGIES
generic_selection_implementation_authority = NONE
production_dynamic_activation_authority = NONE
```

The detailed design may define independent STATIC / DYNAMIC control for each
eligible strategy. Implementation, deployment and strategy activation require
their respective subsequent authority; a research eligibility field does not
grant any of them.
