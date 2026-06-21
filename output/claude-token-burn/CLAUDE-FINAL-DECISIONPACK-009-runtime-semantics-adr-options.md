# CLAUDE-FINAL-DECISIONPACK-009 Runtime Semantics ADR Options

Generated: 2026-06-17
Task ID: CLAUDE-FINAL-DECISIONPACK-009
Mode: final-only decision pack — no implementation, no file modifications except this report
Source findings: CLAUDE-FINAL-HANDOFFQA-007, CLAUDE-FINAL-CODETRACE-008, CLAUDE-FINAL-TESTCARDS-004, CLAUDE-FINAL-TASKPACK-003

---

## 1. Executive Summary

This pack produces architecture decision options for three runtime semantics
issues discovered during the StrategyGroup handoff QA and code-trace audits:

| Topic | Core Issue | Severity |
|---|---|---|
| SOR-001 conditional mode | `conditional_armed_observation` exists as intake-only hardcoded label; runtime has no session-window gating; handoff.json says `armed_observation` | P1 |
| Freshness semantics | Candidate Packet Freshness 120s is metadata-only; stale detection relies entirely on upstream enum/status strings, not numeric windows | P2 |
| Review outcome vocabulary | Backend emits English (`promote`/`revise`/`park`); board contract defines Chinese (`保留`/`调整`/`暂停`/`停用`/`待复盘`); no mapping layer exists | P2 |

**No P0 safety blockers were found.** All three issues are semantic
inconsistencies or documentation gaps, not runtime safety violations. The
current code works because hardcoded overrides paper over the SOR-001 mismatch,
upstream sources correctly report stale status, and the frontend can implement
the review vocabulary mapping.

The recommended path is to resolve each issue through explicit Codex decision,
then implement via scoped Claude task cards after mainline acceptance.

---

## 2. Current Facts vs Analysis

### 2.1 Verified Facts from Code Traces

| Fact | Source | Verified |
|---|---|---|
| `CONDITIONAL_GROUPS = {"SOR-001"}` is hardcoded in intake builder | `scripts/build_strategy_group_handoff_intake_packet.py:90` | ✅ |
| SOR-001 `handoff.json` says `default: "armed_observation"` | `docs/current/strategy-group-handoffs/SOR-001/handoff.json:23` | ✅ |
| Handoff index says `conditional_armed_observation` for SOR-001 | `main-control-handoff-index.md:27` | ✅ |
| Runtime planning enums have no `conditional_armed_observation` variant | `runtime_strategy_signal_planning_service.py:69-72`, `runtime_strategy_signal_scheduler_planning_service.py:61-66` | ✅ |
| Observation scheduler has no conditional logic | `strategy_group_readonly_observation_scheduler.py:44` | ✅ |
| Readmodel collapses to `armed_observation` or `observe_only` | `readmodels/trading_console.py:215` | ✅ |
| Stale detection uses string-token match (`stale`, `expired`, `outdated`) | `strategy_evaluation_context_builder.py:613-617` | ✅ |
| Stale detection uses enum comparison (`AccountFactsFreshnessStatus.STALE`) | `strategy_runtime_fact_overlay_service.py:299-303` | ✅ |
| `candidate_packet_freshness_seconds: 120` is metadata passthrough only | `build_strategy_group_handoff_intake_packet.py:52-72`, `build_strategygroup_runtime_pilot_status.py:638-639` | ✅ |
| Backend review vocabulary is `["promote", "revise", "park"]` | `readmodels/trading_console.py:4458, 6360` | ✅ |
| Chinese review vocabulary (`保留`/`调整`/`暂停`/`停用`/`待复盘`) is absent from all `src/` and `scripts/` | grep verified | ✅ |
| `review_only_warning` gate class has no explicit Owner-facing mapping in readmodel | `readmodels/trading_console.py:7640-7688` (absent) | ✅ |
| Zero test coverage for `conditional_armed_observation_intake_ready` path | grep verified | ✅ |

### 2.2 What Works Today Despite the Gaps

- SOR-001 bootstraps correctly because the intake builder overrides
  `handoff.json` with `CONDITIONAL_GROUPS`.
- Stale facts are blocked correctly because upstream sources report `stale`/
  `STALE` enum values.
- Review outcomes work because the frontend can map English to Chinese.
- Owner status mapping is correct for all gate classes except
  `review_only_warning` (falls through to default `运行中`).

---

## 3. Decision Topic 1: SOR-001 Conditional Mode

### Context

The handoff layer has a three-way inconsistency:

- `main-control-handoff-index.md` → `conditional_armed_observation`
- `main-control-admission-priority.md` → `conditional_armed_observation`
- `SOR-001/handoff.json` → `armed_observation`

The intake builder papers over this by hardcoding `CONDITIONAL_GROUPS = {"SOR-001"}`,
but the runtime has no session-window gating logic. Once past intake, SOR-001
behaves identically to MPG-001/TEQ-001/FBS-001.

### Option A: Implement Real Session-Window Gating

**Summary:** Make `conditional_armed_observation` a first-class runtime mode
where SOR-001 only arms near session open (e.g., 5m before/after TradFi
session boundaries) and degrades to `observe_only` outside those windows.

**Benefits:**
- Honors the research intent — SOR-001 is a session-opening-range strategy
  that only has edge near session boundaries.
- Reduces unnecessary watcher polling and candidate-prep work outside
  active windows.
- Creates a reusable pattern for future time-window-gated strategies.

**Risks:**
- Requires changes to observation scheduler, planning service, and
  potentially the signal evaluation context builder.
- Session-window logic adds complexity to the shared runtime pipe.
- Incorrect session-boundary detection could silently disable SOR-001.
- Needs TradFi session mapping facts to be reliable and fresh.

**Affected files/functions:**
- `src/application/strategy_group_readonly_observation_scheduler.py` — add
  conditional arming logic based on session window.
- `src/application/runtime_strategy_signal_planning_service.py` — add
  `CONDITIONAL_ARMED` status variant to `RuntimeStrategySignalCandidatePlanningStatus`.
- `src/application/runtime_strategy_signal_scheduler_planning_service.py` — add
  conditional variant to `RuntimeStrategySignalSchedulerPlanningStatus`.
- `src/application/readmodels/trading_console.py` — add Owner-facing label
  for conditional state.
- `scripts/build_strategy_group_handoff_intake_packet.py` — keep
  `CONDITIONAL_GROUPS` override, align `handoff.json` to
  `conditional_armed_observation`.
- `docs/current/strategy-group-handoffs/SOR-001/handoff.json` — change
  `default` to `conditional_armed_observation`.

**Blast radius:** Medium. Affects the shared observation scheduler and
planning service. All StrategyGroups pass through these, so changes must
be backward-compatible with `armed_observation` and `observe_only`.

**Safety risk:** Low-Medium. The worst failure mode is SOR-001 not arming
when it should (missed opportunity) or arming outside session windows
(no worse than current behavior). No execution safety impact because
FinalGate and Operation Layer are unaffected.

**Owner-facing risk:** Low. The Owner sees `运行中` or `等待机会` regardless.
Conditional mode is an internal scheduling detail.

**Test requirements:**
- Unit test: SOR-001 with session window active → arms normally.
- Unit test: SOR-001 with session window inactive → degrades to observe.
- Unit test: MPG-001/TEQ-001/FBS-001 unaffected by conditional logic.
- Unit test: `CONDITIONAL_GROUPS` override produces correct intake status.
- Integration test: session-window-gated SOR-001 reaches candidate-prep
  during active window.

**Rollback plan:** Revert `CONDITIONAL_GROUPS` to empty set; change
`handoff.json` back to `armed_observation`. SOR-001 resumes unconditional
arming. No data migration needed.

**Recommendation status:** **Acceptable** — correct long-term solution but
not required for first bounded live-order closure. Defer to post-acceptance.

---

### Option B: Collapse to `armed_observation` Everywhere

**Summary:** Remove `conditional_armed_observation` from all handoff docs.
Change `main-control-handoff-index.md` and `main-control-admission-priority.md`
to say `armed_observation`. Remove `CONDITIONAL_GROUPS` from intake builder.
SOR-001 arms unconditionally like MPG-001/TEQ-001/FBS-001.

**Benefits:**
- Eliminates the inconsistency immediately.
- Simplest change — only documentation and one hardcoded set.
- Zero runtime code changes needed.
- Aligns handoff.json with index/priority (handoff.json already says
  `armed_observation`).

**Risks:**
- SOR-001 arms outside session windows, wasting watcher polling and
  candidate-prep cycles on signals with low probability of edge.
- Research intent (session-window gating) is lost until a future iteration.
- If session-window gating is safety-critical for SOR-001, this is incorrect.

**Affected files/functions:**
- `docs/current/strategy-group-handoffs/main-control-handoff-index.md` —
  change SOR-001 Default Mode to `armed_observation`.
- `docs/current/strategy-group-handoffs/main-control-admission-priority.md` —
  change SOR-001 default mode to `armed_observation`.
- `scripts/build_strategy_group_handoff_intake_packet.py` — remove
  `SOR-001` from `CONDITIONAL_GROUPS` set (line 90).

**Blast radius:** Minimal. Three documentation lines and one set membership.

**Safety risk:** None. SOR-001 already behaves as `armed_observation` at
runtime. This change aligns the documentation with actual behavior.

**Owner-facing risk:** None. Owner status is unchanged.

**Test requirements:**
- Verify intake builder produces `armed_observation_intake_ready` for SOR-001.
- Verify bootstrap accepts SOR-001 with `armed_observation` mode.

**Rollback plan:** Re-add `SOR-001` to `CONDITIONAL_GROUPS`; restore
`conditional_armed_observation` in index/priority docs.

**Recommendation status:** **Recommended** for immediate implementation.
Clean, safe, and aligns documentation with actual runtime behavior.
Session-window gating can be added later as a distinct feature with
proper runtime support.

---

### Option C: Document `conditional` as Intake-Only Advisory

**Summary:** Keep the current state (index/priority say `conditional`,
handoff.json says `armed_observation`, intake builder hardcodes override).
Add explicit documentation that `conditional_armed_observation` is an
intake-only advisory label that the observation scheduler may use in a
future iteration, and that runtime behavior is currently `armed_observation`.

**Benefits:**
- Zero code changes.
- Preserves the research intent marker for future implementation.
- Documents the current inconsistency as intentional.

**Risks:**
- The inconsistency remains — future readers must understand the nuance.
- `CONDITIONAL_GROUPS` override remains untested.
- Handoff.json still says `armed_observation` while index says `conditional`,
  which is confusing regardless of documentation.

**Affected files/functions:**
- `docs/current/strategy-group-handoffs/main-control-handoff-index.md` —
  add a note that `conditional_armed_observation` is advisory.
- `scripts/build_strategy_group_handoff_intake_packet.py` — add comment
  explaining `CONDITIONAL_GROUPS` override.

**Blast radius:** None. Documentation-only.

**Safety risk:** None.

**Owner-facing risk:** None.

**Test requirements:** None — no behavior change.

**Rollback plan:** N/A — documentation only.

**Recommendation status:** **Not recommended.** Documenting an inconsistency
as intentional is weaker than either resolving it (Option B) or implementing
it (Option A). The `CONDITIONAL_GROUPS` override remains a hidden coupling
that will confuse future developers.

---

## 4. Decision Topic 2: Freshness Semantics

### Context

The watcher cadence doc defines `Candidate Packet Freshness: 120s` for all
StrategyGroups. The handoff.json files define `signal_ready_rule.freshness_window_seconds: 120`.
However, the runtime stale detection uses **enum/status checks** (string
tokens like `stale`, `expired`, `outdated` or enum values like
`AccountFactsFreshnessStatus.STALE`), not numeric time-window comparisons.

The 120s value is consumed only as metadata — it appears in intake packets
and pilot status output but is never compared against a timestamp.

The conflict policy says "Fresh signal with stale facts → block candidate
preparation" but does not define what "stale facts" means numerically.

### Option A: Keep Upstream Status/Enum-Only Stale Detection

**Summary:** Accept that stale detection depends on upstream sources
correctly reporting stale status via enum/string values. The 120s
Candidate Packet Freshness remains watcher cadence metadata, not a
runtime enforcement gate.

**Benefits:**
- Simplest — no runtime code changes.
- Upstream sources (Tokyo watcher, account facts, exchange facts) already
  report freshness status correctly.
- Avoids duplicating freshness logic at the runtime layer.
- The enum-based approach is robust against clock-skew issues.

**Risks:**
- If an upstream source reports `fresh` for a fact that is actually 200s
  old, the runtime accepts it.
- No defense-in-depth against upstream freshness reporting bugs.
- The conflict policy's "stale facts" rule remains untestable against a
  numeric threshold.

**Affected files/functions:** None — no changes.

**Blast radius:** None.

**Safety risk:** Low. Upstream sources are currently reliable. The risk
is a future regression in upstream freshness reporting that goes undetected.

**Owner-facing risk:** None.

**Test requirements:**
- Existing tests cover enum-based stale detection adequately.
- Add one test verifying that `freshness_window_seconds` metadata is
  present in intake packets (documentation test).

**Rollback plan:** N/A — no changes.

**Recommendation status:** **Recommended** for now. The upstream sources
are reliable, and adding numeric enforcement is a defense-in-depth measure
that can be deferred.

---

### Option B: Enforce Numeric 120s at Fact Overlay/Candidate Prep Boundary

**Summary:** Add a timestamp comparison in the fact overlay service or
candidate prep boundary that marks facts as stale if they are older than
120 seconds, regardless of upstream freshness status.

**Benefits:**
- Defense-in-depth against upstream freshness reporting bugs.
- Makes the conflict policy's "stale facts" rule testable.
- Aligns runtime behavior with the documented 120s threshold.

**Risks:**
- Requires fact sources to include timestamps (most do, but verify).
- Clock skew between fact source and runtime could cause false staleness.
- The 120s threshold may not be appropriate for all fact types (e.g.,
  exchange rules change infrequently; account balance may be fresh at 300s).
- Adds complexity to the fact overlay service.

**Affected files/functions:**
- `src/application/strategy_runtime_fact_overlay_service.py` — add
  timestamp comparison in `_mark_stale_fields()` or similar.
- `src/application/strategy_evaluation_context_builder.py` — extend
  `_freshness_is_stale()` to include numeric window check.
- `docs/current/strategy-group-handoffs/main-control-required-facts-map.md` —
  document per-fact freshness expectations.

**Blast radius:** Medium. Affects all StrategyGroups' fact overlay path.
If the threshold is wrong, it could block all candidate preparation.

**Safety risk:** Medium. Over-aggressive staleness detection blocks
candidate preparation (safe but annoying). Under-aggressive detection
lets stale facts through (the current behavior).

**Owner-facing risk:** Low. Owner sees `暂不可用` or `等待机会` if facts
are blocked by numeric staleness. This is correct behavior.

**Test requirements:**
- Unit test: fact with `freshness="fresh"` but timestamp 121s old → marked stale.
- Unit test: fact with `freshness="fresh"` and timestamp 119s old → accepted.
- Unit test: fact with `freshness="stale"` and timestamp 10s old → marked stale (enum wins).
- Unit test: all 5 StrategyGroups' RequiredFacts have timestamps in test fixtures.

**Rollback plan:** Remove timestamp comparison from fact overlay service.
Reverts to enum-only detection.

**Recommendation status:** **Acceptable** as a post-acceptance hardening
measure. Not required for first bounded live-order closure.

---

### Option C: Per-Fact Freshness Windows

**Summary:** Introduce explicit per-fact freshness windows in the handoff
contract (e.g., `available_balance: 60s`, `symbol_availability: 3600s`)
separate from signal freshness and candidate packet freshness.

**Benefits:**
- Most precise — different facts have different staleness tolerances.
- Aligns with the reality that exchange rules rarely change while
  account balance changes frequently.
- Makes the conflict policy fully testable per fact.

**Risks:**
- Significant contract change — all 5 handoff.json files need new fields.
- Requires runtime to look up per-fact thresholds.
- Over-engineering for the current pilot stage.
- No evidence that uniform 120s is causing real problems.

**Affected files/functions:**
- All 5 `docs/current/strategy-group-handoffs/*/handoff.json` — add
  `freshness_windows` field.
- `docs/current/strategy-group-handoffs/main-control-required-facts-map.md` —
  add per-fact freshness column.
- `src/application/strategy_runtime_fact_overlay_service.py` — consume
  per-fact windows.
- `src/application/strategy_evaluation_context_builder.py` — consume
  per-fact windows.

**Blast radius:** High. Touches all handoff files and the fact overlay path.

**Safety risk:** Medium. Incorrect per-fact windows could block or
permit incorrectly.

**Owner-facing risk:** None directly, but increases implementation
complexity.

**Test requirements:**
- Per-fact window unit tests for each StrategyGroup.
- Integration test: mixed freshness across facts → correct blocking.

**Rollback plan:** Remove per-fact windows; revert to uniform or
enum-only detection.

**Recommendation status:** **Not recommended** for current stage. Too
much contract surface area for unproven benefit. Consider after the
pilot has real market data showing that uniform 120s is insufficient.

---

## 5. Decision Topic 3: Review Outcome Vocabulary

### Context

Two vocabularies exist:

- **Backend (English internal):** `promote`, `revise`, `park`, `pending`
  — used in `readmodels/trading_console.py:4458, 6360` and
  `runtime_closed_trade_lifecycle_review_service.py:757-764`.
- **Board contract (Chinese Owner-facing):** `保留`, `调整`, `暂停`, `停用`, `待复盘`
  — defined in `STRATEGY_CONTROL_BOARD_CONTRACT.md:27`.
- **Research sync (English lifecycle):** `promote`, `keep_observing`,
  `revise`, `park`, `kill` — defined in `main-control-research-sync.md:44`.

No mapping exists between these vocabularies in any backend code.

### Option A: Backend Emits Internal English, Frontend Translates

**Summary:** Keep the backend emitting `promote`/`revise`/`park`/`pending`.
The frontend (Owner Console) implements a mapping layer to display Chinese
Owner-facing labels per the board contract.

**Benefits:**
- No backend changes.
- Frontend already owns Owner-language display.
- Clean separation: backend = internal semantics, frontend = presentation.
- The board contract's Chinese vocabulary is a display concern, not a
  runtime concern.

**Risks:**
- Frontend must implement the mapping correctly — no backend guard.
- If a new API consumer reads `promote` directly, they see English.
- The mapping logic is duplicated if multiple frontend surfaces exist.

**Affected files/functions:**
- `owner-runtime-console/` — add review outcome mapping (outside this
  task's scope per forbidden files).
- No backend changes.

**Blast radius:** None in backend. Frontend-only change.

**Safety risk:** None. Review outcomes are post-settlement — no execution
impact.

**Owner-facing risk:** Low. If frontend mapping is wrong, Owner sees
wrong Chinese label. No operational impact.

**Test requirements:**
- Frontend test: `promote` → `保留`, `revise` → `调整`, `park` → `暂停`.
- Frontend test: `pending` → `待复盘`.

**Rollback plan:** N/A — frontend-only.

**Recommendation status:** **Recommended.** Clean separation of concerns.
Backend owns semantics, frontend owns presentation.

---

### Option B: Backend ReadModel Emits Both Internal and Chinese Fields

**Summary:** Add a `review_outcome_owner_label` field to the readmodel
that maps `promote` → `保留`, `revise` → `调整`, `park` → `暂停`,
`pending` → `待复盘`. Emit both `review_decision` (English) and
`review_outcome_owner_label` (Chinese) in the API response.

**Benefits:**
- Single source of truth for the mapping — backend owns it.
- Frontend consumes Chinese directly — no mapping logic needed.
- Any API consumer gets both internal and display values.

**Risks:**
- Backend now has presentation logic (Chinese strings in Python code).
- Board contract vocabulary (`停用`/`kill`) is not in the current backend
  enum — needs extension.
- If the board contract vocabulary changes, backend code must change.

**Affected files/functions:**
- `src/application/readmodels/trading_console.py` — add mapping function
  and emit `review_outcome_owner_label`.
- `src/application/runtime_closed_trade_lifecycle_review_service.py` —
  extend allowed values if `停用`/`kill` is added.

**Blast radius:** Low. Additive change to readmodel. No existing fields
modified.

**Safety risk:** None.

**Owner-facing risk:** None — additive.

**Test requirements:**
- Unit test: `promote` → `保留`, `revise` → `调整`, `park` → `暂停`,
  `pending` → `待复盘`.
- Unit test: unknown outcome → fallback label.

**Rollback plan:** Remove `review_outcome_owner_label` field from readmodel.

**Recommendation status:** **Acceptable.** Works but couples backend to
display vocabulary. Preferable only if the frontend cannot implement the
mapping.

---

### Option C: Consolidate Contract Vocabulary to Internal English + Display Mapping Doc

**Summary:** Keep backend English vocabulary. Document the mapping in
`STRATEGY_CONTROL_BOARD_CONTRACT.md` as a display mapping table. Add
`keep_observing` and `kill` from research sync to the backend allowed
values. Frontend implements mapping per the documented table.

**Benefits:**
- Single authoritative mapping document.
- Backend vocabulary aligns with research sync (`promote`/`keep_observing`/
  `revise`/`park`/`kill`).
- No backend presentation logic.
- Mapping is human-readable and reviewable.

**Risks:**
- Frontend still must implement the mapping (same as Option A).
- Board contract currently has `待复盘` which maps to `pending` — needs
  alignment with `keep_observing`.

**Affected files/functions:**
- `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` — add mapping table.
- `src/application/readmodels/trading_console.py` — extend
  `allowed_values` to include `keep_observing` and `kill` if needed.
- `src/application/runtime_closed_trade_lifecycle_review_service.py` —
  extend allowed values.

**Blast radius:** Low. Documentation change plus minor enum extension.

**Safety risk:** None.

**Owner-facing risk:** None.

**Test requirements:**
- Unit test: extended allowed values accepted by readmodel.
- Documentation test: mapping table present in board contract.

**Rollback plan:** Revert mapping table; restore original allowed values.

**Recommendation status:** **Acceptable.** Good middle ground if the
project wants a documented mapping without backend Chinese strings.

---

## 6. Technical Debt Slimming Map

### 6.1 Concepts to Remove

| Concept | Location | Reason |
|---|---|---|
| `CONDITIONAL_GROUPS` override | `build_strategy_group_handoff_intake_packet.py:90` | Hidden coupling; handoff.json should be authoritative. Remove after Option B decision. |
| `candidate_packet_freshness_seconds` as implied enforcement | Watcher cadence doc, intake packet | Rename to `candidate_packet_freshness_target` or add explicit note that it is metadata-only, not a runtime gate. |

### 6.2 Concepts to Rename

| Current | Proposed | Reason |
|---|---|---|
| `conditional_armed_observation` (in index/priority) | `armed_observation` (if Option B chosen) | Align with handoff.json and runtime behavior. |
| `review_outcome` in board contract | Keep, but add mapping column | Clarify that it is the Owner-facing display vocabulary, not the internal lifecycle vocabulary. |

### 6.3 Concepts to Document as Transitional

| Concept | Location | Status |
|---|---|---|
| `review_only_warning` gate class | `AGENTS.md`, `AI_AGENT_CONSTRAINTS.md` | Defined but has no explicit Owner-facing mapping in readmodel. Document that it falls through to default `运行中`. |
| Per-group `source_commit` in handoff.json | All 5 `handoff.json` files | MPG-001 has a different commit hash; others omit it. Document that `main-control-research-sync.md` is the sole provenance source. |

### 6.4 Concepts to Promote to First-Class

| Concept | Current Status | Promotion Action |
|---|---|---|
| Gate class → Owner status mapping | Partially documented in `AI_AGENT_CONSTRAINTS.md` | Add explicit mapping for all 6 classes including `hard_safety_stop` → `需要介入` and `review_only_warning` → `运行中` (with detail). |
| Review outcome vocabulary mapping | Undocumented | Add mapping table to `STRATEGY_CONTROL_BOARD_CONTRACT.md` per Option C. |

### 6.5 Glue Code to Avoid

The `CONDITIONAL_GROUPS` hardcoded override is the primary example of
glue code that should be eliminated. The handoff.json should be the
single source of truth for mode, and the intake builder should read it
directly without group-ID-based overrides.

If session-window gating is needed in the future, it should be a
first-class runtime feature with its own enum variant, test coverage,
and documentation — not a hardcoded set membership check in a build
script.

---

## 7. Recommended Sequencing

### Phase 1: Immediate (Pre-Acceptance, Safe Now)

| Step | Action | Decision |
|---|---|---|
| 1.1 | Resolve SOR-001 mode mismatch | **Option B recommended** — collapse to `armed_observation` |
| 1.2 | Remove `CONDITIONAL_GROUPS` from intake builder | Part of Step 1.1 |
| 1.3 | Document freshness semantics as metadata-only | Add note to watcher cadence doc |

### Phase 2: Post-Acceptance P1

| Step | Action | Decision |
|---|---|---|
| 2.1 | Document review outcome vocabulary mapping | **Option C recommended** — mapping table in board contract |
| 2.2 | Extend backend allowed values (`keep_observing`, `kill`) | Part of Step 2.1 |
| 2.3 | Add `review_only_warning` Owner mapping to readmodel | Documentation + optional code |
| 2.4 | Add test coverage for intake builder multi-group paths | Test card from TESTCARDS-004 |

### Phase 3: Post-Acceptance P2

| Step | Action | Decision |
|---|---|---|
| 3.1 | Implement numeric freshness enforcement (Option B) if real-market data shows upstream gaps | Deferred |
| 3.2 | Implement session-window gating (Option A) if SOR-001 shows edge outside session windows | Deferred |
| 3.3 | Clean up per-group source_commit in handoff.json | Low priority |

### Sequencing Rationale

1. **SOR-001 mode resolution first** — it is the only P1 that blocks
   implementation. Option B is safe and immediate.
2. **Review vocabulary second** — it is P2 and does not block the first
   bounded live-order closure.
3. **Freshness enforcement last** — it is a defense-in-depth measure
   that can wait for real-market data.

---

## 8. Claude-Compatible Task Cards

### Group A: Decision-First (Require Codex Decision Before Implementation)

---

#### DECISIONPACK-TC-001: SOR-001 Mode Alignment

| Field | Value |
|---|---|
| **Task ID** | DECISIONPACK-TC-001 |
| **Goal** | Align SOR-001 default mode to `armed_observation` across all handoff documents and remove `CONDITIONAL_GROUPS` override |
| **Why** | P1 finding F-001: three-way inconsistency between handoff.json, handoff-index, and admission-priority. The `CONDITIONAL_GROUPS` override in the intake builder papers over the mismatch but is untested and creates hidden coupling. |
| **Allowed files** | `docs/current/strategy-group-handoffs/main-control-handoff-index.md`, `docs/current/strategy-group-handoffs/main-control-admission-priority.md`, `scripts/build_strategy_group_handoff_intake_packet.py` |
| **Forbidden files** | `src/**`, `tests/**`, `deploy/**`, `live-config.env`, `.env*`, `owner-runtime-console/**` |
| **Requirements** | 1. Change SOR-001 Default Mode in `main-control-handoff-index.md` from `conditional_armed_observation` to `armed_observation`. 2. Change SOR-001 default mode in `main-control-admission-priority.md` from `conditional_armed_observation` to `armed_observation`. 3. Remove `SOR-001` from `CONDITIONAL_GROUPS` set in `build_strategy_group_handoff_intake_packet.py` line 90. 4. Verify intake builder produces `armed_observation_intake_ready` for SOR-001. |
| **Tests** | `python3 scripts/build_strategy_group_handoff_intake_packet.py --check` (or equivalent verification). Grep for `conditional_armed_observation` in handoff docs returns zero. |
| **Done When** | All three files consistent: SOR-001 mode is `armed_observation` everywhere. No `CONDITIONAL_GROUPS` reference to SOR-001. |
| **Hard Stop** | If Codex decides Option A (implement session-window gating), do not proceed with this card. |
| **Risk** | Low — aligns documentation with existing runtime behavior. |
| **Depends On** | Codex decision on SOR-001 mode (Option A/B/C). |

---

#### DECISIONPACK-TC-002: Review Outcome Vocabulary Mapping

| Field | Value |
|---|---|
| **Task ID** | DECISIONPACK-TC-002 |
| **Goal** | Document the mapping between backend English review outcomes and board contract Chinese Owner-facing vocabulary |
| **Why** | P2 finding F-005/F-004: two vocabularies exist with no documented mapping. Backend uses `promote`/`revise`/`park`; board contract uses `保留`/`调整`/`暂停`/`停用`/`待复盘`. |
| **Allowed files** | `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` |
| **Forbidden files** | `src/**`, `tests/**`, `scripts/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1. Add a mapping table to `STRATEGY_CONTROL_BOARD_CONTRACT.md` after the `review_outcome` row: `promote` → `保留`, `revise` → `调整`, `park` → `暂停`, `pending` → `待复盘`. 2. Document that `停用` maps to `kill` (from research sync) and `keep_observing` maps to `待复盘`. 3. Note that the board contract vocabulary is the Owner-facing display vocabulary; the backend emits English internal values. |
| **Tests** | Grep for mapping table in board contract. Verify all 5 English values have Chinese mappings. |
| **Done When** | Mapping table present in board contract with all vocabulary pairs documented. |
| **Hard Stop** | Do not modify `src/` or `scripts/`. Documentation only. |
| **Risk** | Low — documentation only. |
| **Depends On** | Codex decision on review vocabulary (Option A/B/C). |

---

#### DECISIONPACK-TC-003: Freshness Semantics Documentation

| Field | Value |
|---|---|
| **Task ID** | DECISIONPACK-TC-003 |
| **Goal** | Document that Candidate Packet Freshness 120s is watcher cadence metadata, not a runtime enforcement gate, and clarify stale detection semantics |
| **Why** | P2 finding BF-002: `candidate_packet_freshness_seconds: 120` is metadata-only. Stale detection uses upstream enum/status checks. The conflict policy's "stale facts" rule has no explicit numeric threshold. |
| **Allowed files** | `docs/current/strategy-group-handoffs/main-control-watcher-cadence.md`, `docs/current/strategy-group-handoffs/main-control-conflict-policy.md` |
| **Forbidden files** | `src/**`, `tests/**`, `scripts/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1. Add a note to `main-control-watcher-cadence.md`: "Candidate Packet Freshness is watcher-side metadata for packet staleness tracking. Runtime stale detection uses upstream freshness status enums, not numeric window enforcement." 2. Add a note to `main-control-conflict-policy.md` after the "Fresh signal with stale facts" row: "Stale facts are determined by upstream freshness status reporting (`stale`/`expired`/`outdated` string tokens or `STALE` enum values), not by numeric age comparison." |
| **Tests** | Grep for documentation notes in both files. |
| **Done When** | Both documents have explicit notes clarifying freshness semantics. |
| **Hard Stop** | Do not modify `src/` or `scripts/`. Documentation only. |
| **Risk** | Negligible — documentation only. |
| **Depends On** | Codex decision on freshness (Option A/B/C). Option A recommended. |

---

### Group B: Safe Test-Only (No Source Changes)

---

#### DECISIONPACK-TC-004: Intake Builder Multi-Group Coverage

| Field | Value |
|---|---|
| **Task ID** | DECISIONPACK-TC-004 |
| **Goal** | Add test coverage for all 5 StrategyGroups' intake status assignment, including SOR-001's mode handling |
| **Why** | Finding BF-004: zero test coverage for `conditional_armed_observation_intake_ready` path. The only multi-group test uses `armed_observation` for all except PMR-001. |
| **Allowed files** | `tests/unit/test_trading_console_readmodels.py` (add test cases) |
| **Forbidden files** | `src/**`, `scripts/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1. Add test: SOR-001 handoff with `default_mode: "armed_observation"` → assert intake_status matches current behavior (either `conditional_armed_observation_intake_ready` if CONDITIONAL_GROUPS still has SOR-001, or `armed_observation_intake_ready` if removed). 2. Add test: all 5 StrategyGroups produce correct intake status. 3. Add test: `CONDITIONAL_GROUPS` override logic is exercised. |
| **Tests** | `python -m pytest tests/unit/test_trading_console_readmodels.py -k "intake" -v` |
| **Done When** | All intake status paths have test coverage. |
| **Hard Stop** | Do not modify `scripts/build_strategy_group_handoff_intake_packet.py`. Tests only. |
| **Risk** | Low — tests only. |
| **Depends On** | DECISIONPACK-TC-001 landed (so the expected behavior is known). |

---

#### DECISIONPACK-TC-005: Review Outcome Allowed Values Test

| Field | Value |
|---|---|
| **Task ID** | DECISIONPACK-TC-005 |
| **Goal** | Verify that the readmodel's `allowed_values` and `allowed_outcomes` include all expected review outcomes and that unknown values are handled gracefully |
| **Why** | Finding BF-003: backend exposes `["promote", "revise", "park"]` and `["promote", "revise", "park", "pending"]`. If `keep_observing` or `kill` are added, tests must verify acceptance. |
| **Allowed files** | `tests/unit/test_trading_console_readmodels.py` (add test cases) |
| **Forbidden files** | `src/**`, `scripts/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1. Test: `promote`, `revise`, `park`, `pending` are in allowed values. 2. Test: unknown outcome value does not crash readmodel. 3. Test: review decision status propagates correctly to Owner-facing label. |
| **Tests** | `python -m pytest tests/unit/test_trading_console_readmodels.py -k "review" -v` |
| **Done When** | Review outcome handling is test-covered. |
| **Hard Stop** | Do not modify `src/`. Tests only. |
| **Risk** | Low — tests only. |
| **Depends On** | None. |

---

#### DECISIONPACK-TC-006: Gate Class Owner Mapping Completeness

| Field | Value |
|---|---|
| **Task ID** | DECISIONPACK-TC-006 |
| **Goal** | Verify that all 6 gate classes have Owner-facing label mappings in the readmodel, including `review_only_warning` |
| **Why** | Finding BF-005/F-007: `review_only_warning` gate class has no explicit Owner-facing mapping. Falls through to default `运行中`. |
| **Allowed files** | `tests/unit/test_trading_console_readmodels.py` (add test cases) |
| **Forbidden files** | `src/**`, `scripts/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1. Test: `hard_safety_stop` → `需要介入`. 2. Test: `review_only_warning` → currently `运行中` (default). 3. Test: all 6 gate classes produce a valid Owner label. 4. Test: unknown gate class falls through to `暂不可用` (default degraded). |
| **Tests** | `python -m pytest tests/unit/test_trading_console_readmodels.py -k "gate_class" -v` |
| **Done When** | All gate class → Owner label mappings are test-covered. |
| **Hard Stop** | Do not modify `src/`. Tests only. |
| **Risk** | Low — tests only. |
| **Depends On** | None. |

---

### Group C: Safe Documentation (No Code Changes)

---

#### DECISIONPACK-TC-007: Gate Class Mapping Completeness in AI_AGENT_CONSTRAINTS

| Field | Value |
|---|---|
| **Task ID** | DECISIONPACK-TC-007 |
| **Goal** | Add explicit Owner-facing sentence mappings for `hard_safety_stop` and `review_only_warning` gate classes in `AI_AGENT_CONSTRAINTS.md` |
| **Why** | Finding F-007: these two classes lack explicit mappings. `hard_safety_stop` clearly maps to `需要介入` and `review_only_warning` to `运行中` (with detail), but these are implicit. |
| **Allowed files** | `docs/current/AI_AGENT_CONSTRAINTS.md` |
| **Forbidden files** | `src/**`, `tests/**`, `scripts/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1. Add `hard_safety_stop` → `需要介入` to the gate class mapping table. 2. Add `review_only_warning` → `运行中` (with audit detail available) to the gate class mapping table. |
| **Tests** | Grep for both class names in the mapping table. |
| **Done When** | All 6 gate classes have explicit Owner-facing sentences. |
| **Hard Stop** | Do not modify `src/` or `scripts/`. Documentation only. |
| **Risk** | Negligible. |
| **Depends On** | None. |

---

#### DECISIONPACK-TC-008: Handoff.json Review Outcome Vocabulary Field

| Field | Value |
|---|---|
| **Task ID** | DECISIONPACK-TC-008 |
| **Goal** | Add `review_outcome_vocabulary` field to each handoff.json documenting the accepted review outcomes for post-settlement classification |
| **Why** | Finding F-004: review outcome vocabulary is absent from handoff.json. The handoff layer defines sample packets for signal lifecycle but not for post-settlement review. |
| **Allowed files** | `docs/current/strategy-group-handoffs/MPG-001/handoff.json`, `docs/current/strategy-group-handoffs/TEQ-001/handoff.json`, `docs/current/strategy-group-handoffs/FBS-001/handoff.json`, `docs/current/strategy-group-handoffs/SOR-001/handoff.json`, `docs/current/strategy-group-handoffs/PMR-001/handoff.json` |
| **Forbidden files** | `src/**`, `tests/**`, `scripts/**`, `deploy/**`, `live-config.env`, `.env*` |
| **Requirements** | 1. Add to each handoff.json: `"review_outcome_vocabulary": ["promote", "revise", "park", "kill", "pending"]`. 2. Add a `review_outcome_mapping` field with `{"promote": "保留", "revise": "调整", "park": "暂停", "kill": "停用", "pending": "待复盘"}`. |
| **Tests** | Python one-liner to verify field presence in all 5 files. |
| **Done When** | All 5 handoff.json files have `review_outcome_vocabulary` and `review_outcome_mapping`. |
| **Hard Stop** | Do not modify `src/` or `scripts/`. Handoff docs only. |
| **Risk** | Low — additive field. |
| **Depends On** | DECISIONPACK-TC-002 landed (vocabulary mapping decided). |

---

### Group D: Implementation-After-Decision

---

#### DECISIONPACK-TC-009: Backend Review Outcome Enum Extension

| Field | Value |
|---|---|
| **Task ID** | DECISIONPACK-TC-009 |
| **Goal** | Extend backend allowed review outcome values to include `keep_observing` and `kill` from research sync vocabulary |
| **Why** | The research sync defines 5 outcomes (`promote`, `keep_observing`, `revise`, `park`, `kill`) but the backend only allows 3 (`promote`, `revise`, `park`) plus `pending`. Alignment needed. |
| **Allowed files** | `src/application/readmodels/trading_console.py`, `src/application/runtime_closed_trade_lifecycle_review_service.py`, `src/domain/owner_bounded_execution.py` |
| **Forbidden files** | `deploy/**`, `live-config.env`, `.env*`, exchange gateway, credentials |
| **Requirements** | 1. Add `keep_observing` and `kill` to `allowed_values` in readmodel. 2. Add to `allowed_outcomes` in review service. 3. Add to `owner_bounded_execution.py` allowed values. 4. Add test coverage for new values. |
| **Tests** | `python -m pytest tests/unit/test_trading_console_readmodels.py -k "review" -v` |
| **Done When** | All 5 research sync outcomes plus `pending` are accepted by backend. |
| **Hard Stop** | Do not change review outcome semantics — only extend allowed values. If a new value would change runtime behavior, stop and report to Codex. |
| **Risk** | Low — additive enum extension. Existing values unchanged. |
| **Depends On** | DECISIONPACK-TC-002 (vocabulary mapping decided) + mainline acceptance complete. |

---

#### DECISIONPACK-TC-010: `review_only_warning` Owner Label Mapping

| Field | Value |
|---|---|
| **Task ID** | DECISIONPACK-TC-010 |
| **Goal** | Add explicit `review_only_warning` → `运行中` mapping in readmodel's `_owner_console_runtime_goal_status_source` function |
| **Why** | Finding BF-005: `review_only_warning` falls through to default `运行中` which is correct, but the mapping should be explicit for maintainability and audit clarity. |
| **Allowed files** | `src/application/readmodels/trading_console.py` |
| **Forbidden files** | `deploy/**`, `live-config.env`, `.env*`, exchange gateway, credentials |
| **Requirements** | 1. Add `review_only_warning` to the `status in {"ready", "completed"}` block or create a dedicated block that returns `owner_label="运行中"` with `reason="review_only_warning"`. 2. Add test coverage. |
| **Tests** | `python -m pytest tests/unit/test_trading_console_readmodels.py -k "review_only_warning" -v` |
| **Done When** | `review_only_warning` has an explicit Owner label mapping. |
| **Hard Stop** | Do not change the Owner label from `运行中` — the current behavior is correct. This is an explicit-mapping improvement, not a behavior change. |
| **Risk** | Low — explicit mapping of existing implicit behavior. |
| **Depends On** | Mainline acceptance complete. |

---

## 9. Tests and Rollback Strategy

### 9.1 Test Coverage Summary

| Decision | New Tests Required | Existing Coverage |
|---|---|---|
| SOR-001 Option B | 2 (intake status, bootstrap acceptance) | Partial (multi-group test exists but uses wrong mode for SOR-001) |
| Freshness Option A | 1 (metadata presence documentation test) | Good (enum-based stale detection fully tested) |
| Review vocabulary Option C | 2 (mapping table presence, allowed values) | Partial (English values tested, Chinese mapping not tested) |

### 9.2 Rollback Matrix

| Change | Rollback Action | Data Migration | Downtime |
|---|---|---|---|
| SOR-001 mode alignment (Option B) | Revert 3 files | None | None |
| Review vocabulary mapping doc (Option C) | Revert 1 file | None | None |
| Freshness documentation (Option A) | Revert 2 files | None | None |
| Backend enum extension (TC-009) | Revert 3 files | None | None |
| `review_only_warning` mapping (TC-010) | Revert 1 file | None | None |

All changes are documentation or additive enum extensions. No data migration,
no schema changes, no runtime behavior changes. Rollback is trivial.

### 9.3 Safety Invariant Tests (from TESTCARDS-004)

The following test cards from CLAUDE-FINAL-TESTCARDS-004 remain valid and
should be dispatched after mainline acceptance regardless of this decision
pack's outcomes:

| TestCard | Priority | Rationale |
|---|---|---|
| TESTCARD-004 | CRITICAL | FinalGate blocker class coverage — independent of freshness/mode decisions |
| TESTCARD-005 | HIGH | Admission stale facts + duplicate guard — independent |
| TESTCARD-006 | HIGH | Post-submit partial fill + reconciliation — independent |
| TESTCARD-001 | MEDIUM | Stale facts confirmation blocking — independent |
| TESTCARD-002 | MEDIUM | Idempotency degraded mode — independent |
| TESTCARD-007 | MEDIUM | Notification/review propagation — independent |
| TESTCARD-003 | LOW | No-safe-executor blocked status — independent |

These test cards address runtime safety invariants that are orthogonal to
the semantic decisions in this pack.

---

## 10. Explicit Non-Interference Confirmation

This decision pack performed the following actions:

- **Read** authority documents: AGENTS.md, CLAUDE.md, OWNER_RUNTIME_OPERATING_MODEL.md,
  AI_AGENT_CONSTRAINTS.md, STRATEGY_CONTROL_BOARD_CONTRACT.md, MAIN_CONTROL_ROADMAP.md
- **Read** handoff documents: all 5 handoff.json files, all 7 main-control
  supplement markdowns
- **Read** previous audits: CLAUDE-FINAL-HANDOFFQA-007, CLAUDE-FINAL-CODETRACE-008,
  CLAUDE-FINAL-TESTCARDS-004, CLAUDE-FINAL-TASKPACK-003
- **Read** backend/runtime code: `scripts/build_strategy_group_handoff_intake_packet.py`,
  `src/application/readmodels/trading_console.py`,
  `src/application/strategy_evaluation_context_builder.py`
- **Did not modify** any file except this output report
- **Did not run** pytest, npm, deploy, watcher, exchange, curl, ssh, git
  commit, git push, or process management commands
- **Did not read or write** owner-runtime-console source
- **Did not read or write** /Users/jiangwei/Documents/zhishiku or any other
  workspace
- **Did not make** architecture decisions — produced options and recommendations
  for Codex/Owner review only
- **Did not create** chat-confirmation blockers

The only file written is:
`output/claude-token-burn/CLAUDE-FINAL-DECISIONPACK-009-runtime-semantics-adr-options.md`

---

*End of decision pack.*
