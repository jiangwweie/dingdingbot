# CLAUDE-FINAL-HANDOFFCARDS-006 StrategyGroup Handoff Quality Cards

Generated: 2026-06-17
Source: handoff index + admission priority + conflict policy + required-facts map + research sync + watcher cadence + TASKPACK-003
Mode: task card pack — no implementation

---

## Summary

This report defines post-acceptance quality governance task cards for the
StrategyGroup handoff / research intake layer. It covers completeness
verification, cross-document consistency, testability, boundary enforcement,
Owner-language compliance, and semantic-change escalation paths.

All cards are read-only QA, documentation cleanup, or Codex-decision tasks.
None modify runtime source, tests, scripts, deploy, or live config.

---

## Dispatch Boundary

| Layer | Rule |
|---|---|
| **Read-only QA** | Claude may execute during or after acceptance — no source mutation |
| **Documentation cleanup** | Claude may execute after acceptance — handoff docs and agent instructions only |
| **Codex decision** | Must wait for explicit Codex task card — handoff semantics, boundary, or policy changes |

Cards are grouped by dispatch timing relative to mainline acceptance.

---

## Handoff Quality Dimensions

Eight quality dimensions drive the task cards below:

| # | Dimension | Risk if Missing |
|---|---|---|
| D1 | Handoff completeness per StrategyGroup | Incomplete intake → watcher misconfiguration or silent skip |
| D2 | RequiredFacts ↔ admission priority consistency | Fact class missing for high-rank group → silent candidate block |
| D3 | Conflict policy ↔ watcher cadence testability | Untestable cadence → no regression guard on downshift/block rules |
| D4 | Research handoff boundary enforcement | Research leaking into order authority → safety bypass |
| D5 | Sample packet / review outcome / hard stop / risk defaults gaps | Missing defaults → runtime falls back to ambiguous behavior |
| D6 | Owner-readable status mapping | Raw evidence packet in Owner UI → operator burden, not supervisor model |
| D7 | Post-acceptance read-only QA for Claude | Unbounded Claude scope → silent scope creep into Codex territory |
| D8 | Handoff semantic change escalation | Claude rewriting handoff meaning → silent architecture drift |

---

## Task Card Index

| Card ID | Dimension | Owner | Dispatch Timing |
|---|---|---|---|
| HQ-001A | D1 | Claude | During acceptance |
| HQ-001B | D1 | Claude | During acceptance |
| HQ-001C | D1 | Claude | During acceptance |
| HQ-002A | D2 | Claude | During acceptance |
| HQ-002B | D2 | Codex | After Codex decision |
| HQ-003A | D3 | Claude | During acceptance |
| HQ-003B | D3 | Codex | After Codex decision |
| HQ-004A | D4 | Claude | During acceptance |
| HQ-004B | D4 | Claude | During acceptance |
| HQ-005A | D5 | Claude | During acceptance |
| HQ-005B | D5 | Codex | After Codex decision |
| HQ-006A | D6 | Claude | After acceptance |
| HQ-006B | D6 | Codex | After Codex decision |
| HQ-007A | D7 | Claude | After acceptance |
| HQ-007B | D7 | Claude | After acceptance |
| HQ-008A | D8 | Codex | After Codex decision |
| HQ-008B | D8 | Codex | After Codex decision |

---

## Read-Only QA Cards

### HQ-001A: StrategyGroup Handoff Completeness — Field Presence Audit

| Field | Value |
|---|---|
| **Task ID** | HQ-001A |
| **Goal** | Verify each of the 5 StrategyGroups (MPG-001, TEQ-001, FBS-001, SOR-001, PMR-001) has all required handoff fields present |
| **Why** | Missing a required field (Role, Default Mode, poll cadence, signal validity, candidate freshness) causes silent misconfiguration in watcher or admission |
| **Allowed files** | `docs/current/strategy-group-handoffs/` (read only) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | For each StrategyGroup, check: (1) entry in `main-control-handoff-index.md` batch table, (2) entry in `main-control-admission-priority.md`, (3) entry in `main-control-watcher-cadence.md`, (4) at least one RequiredFacts readiness class in `main-control-required-facts-map.md` covering its fact needs. Produce a 5×4 presence matrix. |
| **Verification** | Matrix has zero empty cells |
| **Done When** | Presence matrix complete; any gap reported as a blocker with the specific missing field and file |
| **Hard Stop** | If any StrategyGroup is missing from any of the 4 files, report the gap — do not silently skip |
| **Risk** | Low — read-only audit |
| **Depends On** | None |
| **Owner** | Claude |
| **Dispatch Timing** | During acceptance |

### HQ-001B: Default Mode ↔ Admission Priority Alignment

| Field | Value |
|---|---|
| **Task ID** | HQ-001B |
| **Goal** | Verify the `Default Mode` column matches between `main-control-handoff-index.md` and `main-control-admission-priority.md` for every StrategyGroup |
| **Why** | Mode mismatch between handoff index and admission priority means one file is stale — watcher or bootstrap may use the wrong mode |
| **Allowed files** | `docs/current/strategy-group-handoffs/main-control-handoff-index.md`, `docs/current/strategy-group-handoffs/main-control-admission-priority.md` (read only) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Compare Default Mode for each StrategyGroup across both files. Flag any discrepancy with file:line references. |
| **Verification** | All 5 groups have identical Default Mode in both files |
| **Done When** | Comparison report produced; discrepancies (if any) listed with exact file and line references |
| **Hard Stop** | If discrepancy found, report to Codex — do not decide which file is authoritative |
| **Risk** | Low — read-only comparison |
| **Depends On** | None |
| **Owner** | Claude |
| **Dispatch Timing** | During acceptance |

### HQ-001C: Admission Priority Rank Completeness

| Field | Value |
|---|---|
| **Task ID** | HQ-001C |
| **Goal** | Verify admission priority ranks 1–5 are contiguous, unique, and cover all StrategyGroups in the batch |
| **Why** | Duplicate or gap ranks cause ambiguous picker ordering; missing group means it never enters admission |
| **Allowed files** | `docs/current/strategy-group-handoffs/main-control-admission-priority.md` (read only) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Check: (1) ranks 1–5 with no gaps, (2) no duplicate ranks, (3) each rank maps to exactly one StrategyGroup, (4) all 5 batch groups present |
| **Verification** | Rank sequence is [1,2,3,4,5] with unique StrategyGroup per rank |
| **Done When** | Completeness confirmed or gap/duplicate reported |
| **Hard Stop** | If rank structure is broken, report to Codex — do not reassign ranks |
| **Risk** | Low — read-only audit |
| **Depends On** | None |
| **Owner** | Claude |
| **Dispatch Timing** | During acceptance |

---

### HQ-002A: RequiredFacts Map ↔ Admission Priority Consistency Audit

| Field | Value |
|---|---|
| **Task ID** | HQ-002A |
| **Goal** | Verify each StrategyGroup's admission rank is supported by the correct RequiredFacts readiness classes |
| **Why** | A high-rank group (e.g. MPG-001 rank 1) that lacks a RequiredFacts class for its domain (e.g. `market` or `account`) will silently block at runtime with no documented reason |
| **Allowed files** | `docs/current/strategy-group-handoffs/main-control-admission-priority.md`, `docs/current/strategy-group-handoffs/main-control-required-facts-map.md` (read only) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | For each StrategyGroup: (1) identify its strategy type (momentum, equity-like, funding/basis, precious-metal, session opening-range), (2) map required fact classes from the readiness table, (3) verify the required-facts-map covers all classes needed for that group's default mode. Produce a StrategyGroup × RequiredFacts class matrix with coverage status. |
| **Verification** | Each armed_observation group has at minimum `market`, `strategy`, `risk`, `account` classes covered. FBS-001 additionally has `derivatives`. PMR-001 at minimum has `market` and `strategy` for observe_only. |
| **Done When** | Coverage matrix produced; any missing class listed as a blocker |
| **Hard Stop** | If a RequiredFacts class needed by a StrategyGroup is not defined in the map, report to Codex — do not invent new classes |
| **Risk** | Low — read-only cross-reference |
| **Depends On** | HQ-001A passed |
| **Owner** | Claude |
| **Dispatch Timing** | During acceptance |

### HQ-002B: RequiredFacts Class Completeness — Missing Class Decision

| Field | Value |
|---|---|
| **Task ID** | HQ-002B |
| **Goal** | If HQ-002A finds a missing RequiredFacts class, Codex decides whether to add it to the map or adjust the StrategyGroup's mode |
| **Why** | Adding a new readiness class changes admission behavior for all groups — this is a Codex semantic decision, not a Claude implementation task |
| **Allowed files** | `docs/current/strategy-group-handoffs/main-control-required-facts-map.md` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Codex issues task card specifying: (1) the missing class name, (2) its meaning and missing-behavior, (3) which StrategyGroups it applies to |
| **Verification** | New class appears in the map with correct Meaning and Missing Behavior columns |
| **Done When** | Codex-approved class added to the map |
| **Hard Stop** | Do not add RequiredFacts classes without Codex task card — classes define admission safety boundaries |
| **Risk** | Medium — affects admission behavior |
| **Depends On** | HQ-002A blocker report |
| **Owner** | Codex |
| **Dispatch Timing** | After Codex decision |

---

### HQ-003A: Conflict Policy ↔ Watcher Cadence Testability Audit

| Field | Value |
|---|---|
| **Task ID** | HQ-003A |
| **Goal** | Verify each conflict policy rule in `main-control-conflict-policy.md` has a testable cadence or freshness window defined in `main-control-watcher-cadence.md` |
| **Why** | A conflict rule (e.g. "Fresh signal with stale facts → Block") without a defined freshness window cannot be tested — the system cannot determine "stale" without a threshold |
| **Allowed files** | `docs/current/strategy-group-handoffs/main-control-conflict-policy.md`, `docs/current/strategy-group-handoffs/main-control-watcher-cadence.md` (read only) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | For each conflict rule: (1) identify which watcher cadence fields (Poll Cadence, Signal Validity, Candidate Packet Freshness) define the testable threshold, (2) verify the threshold exists and is specific (range is acceptable, "TBD" is not). Produce a conflict-rule × cadence-field coverage matrix. |
| **Verification** | Each conflict rule that references freshness, staleness, or timing has a corresponding cadence entry with numeric values |
| **Done When** | Coverage matrix produced; any untestable rule (no cadence threshold) listed as a blocker |
| **Hard Stop** | If a conflict rule has no testable threshold, report to Codex — do not invent thresholds |
| **Risk** | Low — read-only audit |
| **Depends On** | None |
| **Owner** | Claude |
| **Dispatch Timing** | During acceptance |

### HQ-003B: Conflict Policy Rule Completeness — Missing Rule Decision

| Field | Value |
|---|---|
| **Task ID** | HQ-003B |
| **Goal** | If HQ-003A finds a conflict scenario not covered by existing rules, Codex decides whether to add a rule or accept the gap |
| **Why** | Conflict rules define safety boundaries — adding or removing rules changes when candidates are blocked or downshifted |
| **Allowed files** | `docs/current/strategy-group-handoffs/main-control-conflict-policy.md` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Codex issues task card specifying: (1) the uncovered conflict scenario, (2) the proposed rule, (3) the expected behavior (block, downshift, merge, review) |
| **Verification** | New rule appears in the conflict policy table |
| **Done When** | Codex-approved rule added or gap explicitly accepted |
| **Hard Stop** | Do not add conflict rules without Codex task card — rules define candidate blocking behavior |
| **Risk** | Medium — affects candidate preparation safety |
| **Depends On** | HQ-003A blocker report |
| **Owner** | Codex |
| **Dispatch Timing** | After Codex decision |

---

### HQ-004A: Research Handoff Boundary — Picker/Watcher Scope Enforcement

| Field | Value |
|---|---|
| **Task ID** | HQ-004A |
| **Goal** | Verify research handoff content is consumed only as Strategy Picker options, watcher scope, RequiredFacts mapping, conflict/cadence policy, and review outcomes — never as order authority |
| **Why** | The research sync boundary is explicit: research informs picker/watcher/facts, but does not authorize FinalGate bypass, Operation Layer bypass, exchange submit, credential changes, profile expansion, or order-sizing expansion. If code or docs leak research into authority paths, the safety boundary is broken. |
| **Allowed files** | `docs/current/strategy-group-handoffs/main-control-research-sync.md`, `docs/current/strategy-group-handoffs/main-control-handoff-index.md` (read only) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | (1) List every "may inform" item from research-sync.md boundary section. (2) List every "does not authorize" item. (3) Verify each "may inform" item has a corresponding consumer in the handoff index or related handoff docs. (4) Verify no "does not authorize" item appears as a "may inform" item. Produce a two-column boundary audit. |
| **Verification** | "may inform" and "does not authorize" sets are disjoint; every "may inform" item has a documented consumer |
| **Done When** | Boundary audit complete; any leakage (research content appearing in authority position) reported as a hard blocker |
| **Hard Stop** | If research content is referenced as order authority, FinalGate input, or Operation Layer evidence, report immediately — this is a safety boundary violation |
| **Risk** | Medium — safety boundary |
| **Depends On** | None |
| **Owner** | Claude |
| **Dispatch Timing** | During acceptance |

### HQ-004B: Research Source Provenance Chain Verification

| Field | Value |
|---|---|
| **Task ID** | HQ-004B |
| **Goal** | Verify the research sync source (branch, commit, handoff validator, unit test) is documented and the provenance chain is complete |
| **Why** | If the source commit or validator status is missing, there is no way to trace which research version was accepted into main control — future audits cannot reproduce the handoff |
| **Allowed files** | `docs/current/strategy-group-handoffs/main-control-research-sync.md` (read only) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Verify all 4 provenance fields are present and non-empty: Source branch, Source commit, Handoff validator, Unit test. Verify status is `reviewed_and_synced_to_main_control_baseline`. Verify "Raw research artifacts" field documents the disposition. |
| **Verification** | All 4 fields present; status matches expected value; disposition documented |
| **Done When** | Provenance chain confirmed complete or gap reported |
| **Hard Stop** | If handoff validator or unit test status is not `pass`, report to Codex — do not accept unvalidated research |
| **Risk** | Low — read-only provenance check |
| **Depends On** | None |
| **Owner** | Claude |
| **Dispatch Timing** | During acceptance |

---

### HQ-005A: Sample Packet / Review Outcome / Hard Stop / Risk Defaults Gap Scan

| Field | Value |
|---|---|
| **Task ID** | HQ-005A |
| **Goal** | Scan all handoff files for the presence of sample packet definitions, review outcome vocabulary, hard stop definitions, and risk default references for each StrategyGroup |
| **Why** | If a StrategyGroup lacks a sample packet, the watcher cannot validate packet structure. If review outcomes are undefined, post-settlement has no vocabulary. If hard stops are missing, FinalGate has no rejection criteria. If risk defaults are absent, admission falls back to ambiguous behavior. |
| **Allowed files** | `docs/current/strategy-group-handoffs/` (read only, all files) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | For each StrategyGroup, check: (1) sample packet structure defined or referenced, (2) review outcome vocabulary (promote, keep_observing, revise, park, kill) documented, (3) hard stop criteria listed, (4) risk default references present (profile, max exposure, protection template). Produce a 5×4 gap matrix. |
| **Verification** | Matrix shows presence/absence for each cell; any "absence" is flagged for Codex review |
| **Done When** | Gap matrix complete; all gaps listed with recommended action (define, reference, or accept as intentional gap) |
| **Hard Stop** | If hard stop criteria are completely absent for an armed_observation group, report as a safety blocker — armed groups must have rejection criteria |
| **Risk** | Medium — missing safety defaults |
| **Depends On** | HQ-001A passed |
| **Owner** | Claude |
| **Dispatch Timing** | During acceptance |

### HQ-005B: Risk Defaults / Hard Stop Codex Decision

| Field | Value |
|---|---|
| **Task ID** | HQ-005B |
| **Goal** | If HQ-005A finds missing hard stops or risk defaults for an armed_observation group, Codex defines them |
| **Why** | Hard stops and risk defaults are safety boundary definitions — Claude must not invent them |
| **Allowed files** | `docs/current/strategy-group-handoffs/` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Codex issues task card specifying: (1) the missing hard stop or risk default, (2) the value or criteria, (3) which StrategyGroup it applies to |
| **Verification** | New hard stop or risk default appears in the relevant handoff file |
| **Done When** | Codex-approved defaults added or gap explicitly accepted with documented rationale |
| **Hard Stop** | Do not define hard stops or risk defaults without Codex task card — these are safety boundary definitions |
| **Risk** | High — safety boundary definitions |
| **Depends On** | HQ-005A blocker report |
| **Owner** | Codex |
| **Dispatch Timing** | After Codex decision |

---

## Documentation Cleanup Cards

### HQ-006A: Owner-Readable Status Mapping Audit

| Field | Value |
|---|---|
| **Task ID** | HQ-006A |
| **Goal** | Verify every internal gate class and handoff state has a mapping to Owner-readable terse language; flag any raw internal term that could leak into the main Owner interface |
| **Why** | The operating model requires Owner-facing states to be product states (运行中, 等待机会, 处理中, 暂不可用, 需要介入, 已暂停, 已完成, 无需操作). Internal terms (FinalGate, Operation Layer, RequiredFacts, candidate, authorization, preflight, proof, route, refId, blocker code, runtime grant) must not appear as primary UI labels. If handoff docs define states without Owner mappings, implementation may expose raw terms. |
| **Allowed files** | `docs/current/strategy-group-handoffs/` (read only), `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` (read only), `docs/current/AI_AGENT_CONSTRAINTS.md` (read only) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | (1) List all internal state/gate names from handoff files. (2) Cross-reference against the Owner-language allowlist in OWNER_RUNTIME_OPERATING_MODEL.md and AI_AGENT_CONSTRAINTS.md. (3) Flag any internal term that has no Owner-facing mapping. (4) Verify the product state list (not_enabled through completed) covers all handoff lifecycle states. |
| **Verification** | Every internal term has a documented Owner-facing mapping or is explicitly marked as audit/detail-only |
| **Done When** | Status mapping audit complete; any missing mapping reported with the specific internal term and suggested Owner wording |
| **Hard Stop** | If an internal term appears in a handoff file without any Owner mapping and the file does not mark it as audit-only, report as a product surface risk |
| **Risk** | Low — documentation audit |
| **Depends On** | None |
| **Owner** | Claude |
| **Dispatch Timing** | After acceptance |

### HQ-006B: Owner Interface Term Sanitization Decision

| Field | Value |
|---|---|
| **Task ID** | HQ-006B |
| **Goal** | If HQ-006A finds internal terms at risk of leaking into the Owner interface, Codex decides whether to add explicit audit-only markers or rewrite the handoff language |
| **Why** | Changing handoff terminology is a semantic decision — it affects how implementers interpret the handoff. Claude must not silently rewrite handoff meaning. |
| **Allowed files** | `docs/current/strategy-group-handoffs/` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Codex issues task card specifying: (1) the internal term at risk, (2) whether to add audit-only marker or replace with Owner wording, (3) the specific replacement if applicable |
| **Verification** | Updated handoff file has explicit audit-only markers or Owner-compatible wording |
| **Done When** | Codex-approved language change applied |
| **Hard Stop** | Do not rewrite handoff terminology without Codex task card — terminology defines implementation expectations |
| **Risk** | Medium — product surface semantics |
| **Depends On** | HQ-006A blocker report |
| **Owner** | Codex |
| **Dispatch Timing** | After Codex decision |

---

### HQ-007A: Post-Acceptance Read-Only QA Scope Definition

| Field | Value |
|---|---|
| **Task ID** | HQ-007A |
| **Goal** | Document the explicit list of read-only QA tasks Claude may perform on handoff files without Codex task card |
| **Why** | Without a defined scope, Claude may either over-restrict (missing useful audits) or over-reach (modifying handoff semantics). The scope must be explicit and bounded. |
| **Allowed files** | `docs/current/strategy-group-handoffs/` (read only) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Claude's read-only QA scope on handoff files is limited to: (1) field presence checks, (2) cross-file consistency comparisons, (3) internal-vs-Owner term audits, (4) provenance chain verification, (5) gap matrix production. Claude must NOT: rewrite handoff content, add/remove rows, change values, define new classes, or adjust thresholds. |
| **Verification** | Scope list matches the QA cards in this report (HQ-001A through HQ-005A, HQ-006A) |
| **Done When** | Scope documented and consistent with card definitions |
| **Hard Stop** | If a QA task requires modifying handoff content, escalate to Codex — do not modify |
| **Risk** | Low — scope definition |
| **Depends On** | None |
| **Owner** | Claude |
| **Dispatch Timing** | After acceptance |

### HQ-007B: Handoff File Integrity — No Unauthorized Edits Check

| Field | Value |
|---|---|
| **Task ID** | HQ-007B |
| **Goal** | After all QA cards execute, verify no handoff file was modified by QA tasks |
| **Why** | QA is read-only — if a QA task accidentally modified a handoff file, the integrity of the handoff layer is compromised |
| **Allowed files** | `docs/current/strategy-group-handoffs/` (read only via git diff) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Run `git diff -- docs/current/strategy-group-handoffs/` and verify zero changes. If changes exist, identify which QA task introduced them. |
| **Verification** | `git diff -- docs/current/strategy-group-handoffs/` returns empty |
| **Done When** | Integrity confirmed or accidental modification reported and reverted |
| **Hard Stop** | If any handoff file was modified, revert the change and report which card caused it |
| **Risk** | Low — integrity check |
| **Depends On** | All QA cards completed |
| **Owner** | Claude |
| **Dispatch Timing** | After acceptance |

---

## Codex Decision Cards

### HQ-008A: Handoff Batch Extension — New StrategyGroup Intake Process

| Field | Value |
|---|---|
| **Task ID** | HQ-008A |
| **Goal** | Define the process for adding a new StrategyGroup to the handoff batch (beyond the initial 5) |
| **Why** | The current handoff files define 5 groups. When research produces a new StrategyGroup candidate, there is no documented intake process — adding it requires changes to 4+ handoff files and potentially new RequiredFacts classes, conflict rules, and cadence entries. Without a process, additions are ad-hoc and may miss required fields. |
| **Allowed files** | `docs/current/strategy-group-handoffs/` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Codex defines: (1) required fields for a new StrategyGroup handoff entry, (2) which handoff files must be updated, (3) approval process (research sync → handoff pack → Codex review → admission), (4) whether new groups default to observe_only or require explicit mode assignment |
| **Verification** | Intake process document covers all 4 handoff files that need updating |
| **Done When** | Intake process documented in a new or existing handoff file |
| **Hard Stop** | Do not add new StrategyGroups without a documented intake process — each group affects admission, watcher, facts, and conflict layers |
| **Risk** | Medium — affects future handoff quality |
| **Depends On** | Codex decision |
| **Owner** | Codex |
| **Dispatch Timing** | After Codex decision |

### HQ-008B: Handoff Versioning and Change Tracking Decision

| Field | Value |
|---|---|
| **Task ID** | HQ-008B |
| **Goal** | Decide whether handoff files need version tracking (beyond git history) for semantic changes |
| **Why** | Current handoff files use `Status: CURRENT_PILOT_SUPPLEMENT` and `last_updated` dates. If a conflict policy rule changes or a RequiredFacts class is added, there is no mechanism to signal downstream consumers (watcher, admission, bootstrap script) that the handoff semantics changed. Git history is the only record. |
| **Allowed files** | `docs/current/strategy-group-handoffs/` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | Codex decides: (1) whether to add a changelog section to each handoff file, (2) whether to bump a version number on semantic changes, (3) whether downstream consumers (bootstrap script, watcher config) should check handoff version before using it. Document the decision. |
| **Verification** | Decision documented; if versioning adopted, initial versions assigned to all 6 handoff files |
| **Done When** | Versioning decision documented and (if adopted) initial versions set |
| **Hard Stop** | Do not implement version checking in runtime code without Codex task card — that changes runtime behavior |
| **Risk** | Low to medium — affects change management |
| **Depends On** | Codex decision |
| **Owner** | Codex |
| **Dispatch Timing** | After Codex decision |

---

## Do-Not-Dispatch During Live Acceptance

These cards must NOT be dispatched while mainline acceptance is in progress:

| Card ID | Reason |
|---|---|
| HQ-002B | Requires Codex decision on RequiredFacts class — blocks on HQ-002A |
| HQ-003B | Requires Codex decision on conflict rule — blocks on HQ-003A |
| HQ-005B | Requires Codex decision on hard stops / risk defaults — blocks on HQ-005A |
| HQ-006B | Requires Codex decision on handoff terminology — blocks on HQ-006A |
| HQ-008A | Requires Codex decision on intake process — independent but semantic |
| HQ-008B | Requires Codex decision on versioning — independent but semantic |

---

## Suggested Sequence

### Phase 1: During Acceptance (Claude, read-only)

Execute in parallel — all are independent read-only audits:

1. **HQ-001A** — Handoff completeness field presence
2. **HQ-001B** — Default mode alignment
3. **HQ-001C** — Admission rank completeness
4. **HQ-002A** — RequiredFacts ↔ admission consistency
5. **HQ-003A** — Conflict policy ↔ cadence testability
6. **HQ-004A** — Research handoff boundary enforcement
7. **HQ-004B** — Research source provenance chain
8. **HQ-005A** — Sample packet / review / hard stop / risk defaults gap scan
9. **HQ-006A** — Owner-readable status mapping audit

### Phase 2: Codex Review of Phase 1 Blockers

Codex reviews blocker reports from Phase 1 and issues decision cards:

- **HQ-002B** if RequiredFacts class gap found
- **HQ-003B** if conflict rule gap found
- **HQ-005B** if hard stop / risk default gap found
- **HQ-006B** if Owner term leakage found

### Phase 3: After Acceptance (Claude, documentation)

- **HQ-007A** — Document Claude read-only QA scope
- **HQ-007B** — Handoff file integrity check

### Phase 4: Codex Architecture Decisions (independent)

- **HQ-008A** — New StrategyGroup intake process
- **HQ-008B** — Handoff versioning decision

---

## Card-to-TaskPACK-003 Cross-Reference

This report complements TASKPACK-003. Where TASKPACK-003 covers code cleanup
and architecture decisions, this report covers handoff layer quality governance.

| TASKPACK-003 Group | This Report Coverage |
|---|---|
| Group 1 (Acceptance-Safe) | No overlap — TASKPACK-003 covers agent commit cleanup |
| Group 2 (Post-Acceptance P1) | HQ-007A/B align with CARD-002A–002C (documentation cleanup) |
| Group 3 (Post-Acceptance P2) | HQ-006A/B align with CARD-003A (surface classification) |
| Group 4 (Deferred Architecture) | HQ-008A/B are architecture-level handoff decisions |
| Group 5 (Do-Not-Dispatch) | HQ-002B/003B/005B are similarly gated on Codex decision |

---

*End of report.*
