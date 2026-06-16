# CLAUDE-FINAL-UICARDS-005 Owner Console Surface Governance Cards

Generated: 2026-06-17
Source: CLAUDE-AUDIT-001, CLAUDE-FINAL-TASKPACK-003, docs/current UI contracts
Mode: task card pack — no implementation

---

## Summary

This pack defines post-acceptance governance task cards for Owner Console and Trading Console surface compliance. It covers:

- **owner-runtime-console** compliance maintenance and anti-regression QA (currently clean)
- **trading-console** developer/audit-only classification decision (62+ primary label violations found)
- **trading-console** internal term remediation if it remains Owner-visible
- **API field → Owner label mapping** verification
- **Visual QA gate** and **forbidden term scanner** hardening
- **docs/current** UI contract deduplication and SSOT consolidation
- **Do-Not-During-Acceptance** change list

The `owner-runtime-console` is **fully compliant** — zero primary label violations. The `trading-console` has **62+ HIGH-severity violations** across 10 page components where internal execution terms (`FinalGate`, `Operation Layer`, `RequiredFacts`, `candidate`, `authorization`, `preflight`, `runtime grant`) appear as card titles, table columns, section headers, and notification text.

---

## Dispatch Boundary

| Phase | Cards | Gate |
|---|---|---|
| Acceptance-Safe Now | UIG-001 | Can land during mainline acceptance |
| Post-Live-Acceptance P1 | UIG-002, UIG-003 | After mainline acceptance + live-test close |
| Post-Live-Acceptance P2 | UIG-004, UIG-005, UIG-006 | After P1 settled |
| Codex Decision Required | UIG-007, UIG-008 | Blocked on Codex classification |

---

## Task Card Index

| Card | Title | Owner | Dispatch |
|---|---|---|---|
| UIG-001 | owner-runtime-console Compliance Anti-Regression Gate | Claude | Now |
| UIG-002 | trading-console Developer/Audit Classification Decision | Codex | Post-acceptance |
| UIG-003 | trading-console Primary Label Remediation (conditional) | Claude | Post-acceptance (if Owner-visible) |
| UIG-004 | API Internal Field → Owner-Friendly Label Mapping Verification | Claude | Post-P1 |
| UIG-005 | Visual QA Gate + Forbidden Term Scanner Hardening | Claude | Post-P1 |
| UIG-006 | docs/current UI Contract Dedup and SSOT Reference Cleanup | Claude | Post-P1 |
| UIG-007 | Do-Not-Dispatch During Live Acceptance Change List | Codex (reference) | Reference |
| UIG-008 | trading-console Route Name + Sidebar Label Audit | Claude | Post-UIG-002 |

---

## Acceptance-Safe Now

### UIG-001: owner-runtime-console Compliance Anti-Regression Gate

| Field | Value |
|---|---|
| **Task ID** | UIG-001 |
| **Goal** | Add automated forbidden-term scan to `owner-runtime-console` CI or visual:qa gate to prevent regression of currently-clean compliance |
| **Why** | `owner-runtime-console` is the only fully compliant Owner surface (0 violations in CLAUDE-AUDIT-001). Without automated guard, future PRs may reintroduce banned terms. The existing `npm run visual:qa` checks for forbidden terms but does not enforce a zero-tolerance hard fail on new introductions. |
| **Allowed files** | `owner-runtime-console/scripts/visual-qa.ts` (or equivalent QA script), `owner-runtime-console/package.json` |
| **Forbidden files** | `src/`, `tests/`, `scripts/` (backend), `deploy/`, `trading-console/`, `live-config.env`, `.env*` |
| **Requirements** | (1) Add or verify a grep-based scanner that checks all `owner-runtime-console/src/**/*.tsx` files for forbidden terms (`FinalGate`, `Operation Layer`, `RequiredFacts`, `candidate`, `authorization`, `preflight`, `proof`, `route`, `refId`, `blocker code`, `runtime grant`) in primary UI render paths. (2) Scanner must distinguish internal data-model keys (acceptable) from rendered text (forbidden). (3) Hard fail on any new violation. (4) Whitelist existing low-risk internal keys: `calls_final_gate`, `calls_operation_layer`, `creates_candidate`, `creates_authorization`. |
| **Verification** | (1) Run scanner against current codebase — zero violations. (2) Intentionally inject a banned term in a test branch — scanner catches it. (3) `npm run visual:qa` still passes. |
| **Done When** | Scanner is integrated into QA gate and passes on current codebase with zero false positives |
| **Hard Stop** | Do not modify `trading-console/` or backend source. Do not relax the forbidden term list. |
| **Risk** | Low — additive QA tooling only |
| **Depends On** | None |
| **Owner** | Claude |
| **Dispatch Timing** | Acceptance-safe now |

---

## Post-Live-Acceptance UI Governance

### UIG-002: trading-console Developer/Audit Classification Decision

| Field | Value |
|---|---|
| **Task ID** | UIG-002 |
| **Goal** | Codex decides whether `trading-console/` is (a) developer/audit-only, (b) a secondary Owner surface requiring remediation, or (c) to be archived. Document the decision. |
| **Why** | CLAUDE-AUDIT-001 found 62+ HIGH-severity violations in `trading-console/`. If it is developer-only, the violations are acceptable with documentation. If Owner-visible, remediation is required before live use. The decision gates UIG-003 and UIG-008. |
| **Allowed files** | `trading-console/README.md` (for classification header), `docs/current/` (for decision documentation) |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `owner-runtime-console/`, `live-config.env`, `.env*` |
| **Requirements** | (1) Codex chooses one of: (a) add `DEVELOPER/AUDIT ONLY — NOT OWNER-FACING` header to `trading-console/README.md` and document in `docs/current/`, (b) classify as Owner surface and dispatch UIG-003, (c) archive the surface. (2) Document the decision rationale. (3) If option (a), verify no active Owner workflow routes to `trading-console/`. |
| **Verification** | Decision documented; README header applied if option (a); UIG-003 dispatched if option (b) |
| **Done When** | Classification decision is documented and applied |
| **Hard Stop** | Do not delete `trading-console/` without explicit Codex approval — it has audit value. Do not modify `owner-runtime-console/`. |
| **Risk** | Medium — product surface semantics |
| **Depends On** | Mainline acceptance complete |
| **Owner** | Codex (decision) + Claude (documentation) |
| **Dispatch Timing** | Post-live-acceptance |

### UIG-003: trading-console Primary Label Remediation (Conditional)

| Field | Value |
|---|---|
| **Task ID** | UIG-003 |
| **Goal** | Replace all 62+ banned internal terms in `trading-console` primary UI labels, card titles, table columns, section headers, and notification text with Chinese Owner-friendly language |
| **Why** | CLAUDE-AUDIT-001 found violations across 10 page components. AGENTS.md and AI_AGENT_CONSTRAINTS.md prohibit internal gate names as primary Owner labels. Required only if UIG-002 classifies trading-console as Owner-visible. |
| **Allowed files** | `trading-console/src/**/*.tsx`, `trading-console/src/lib/ownerViewModel.ts` |
| **Forbidden files** | `src/`, `owner-runtime-console/`, `tests/`, `docs/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | (1) Map all banned terms to Chinese Owner-friendly labels per the mapping in CLAUDE-AUDIT-001 findings table. (2) Key mappings: `FinalGate` → `安全判定`, `Operation Layer` → `官方提交路径`, `RequiredFacts` → `事实`, `candidate` → `候选`/`待处理`, `authorization` → `权限`/`确认`, `preflight` → `预检`, `runtime grant` → `运行授权`, `gate` → `检查`. (3) Internal data-model keys remain unchanged — only display labels change. (4) All existing functionality preserved. (5) Follow the mapping table in `docs/current/OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT.md`. |
| **Verification** | (1) `grep -rn "FinalGate\|Operation Layer\|RequiredFacts\|runtime grant\|preflight" trading-console/src/ --include="*.tsx"` returns zero hits in primary render paths. (2) All 10 affected pages render correctly. (3) No TypeScript compilation errors. |
| **Done When** | All primary UI labels use Chinese Owner-friendly language; zero banned terms in rendered text |
| **Hard Stop** | Do not modify API response models or backend logic. Do not modify `owner-runtime-console/`. Do not change internal data-model keys. |
| **Risk** | Medium — broad UI label changes across 10 files |
| **Depends On** | UIG-002 decision (option b) |
| **Owner** | Claude |
| **Dispatch Timing** | Post-acceptance, only if UIG-002 selects option (b) |

---

## Codex Decision Cards

### UIG-004: API Internal Field → Owner-Friendly Label Mapping Verification

| Field | Value |
|---|---|
| **Task ID** | UIG-004 |
| **Goal** | Verify that all API response model fields with internal terms (`authorization_id`, `order_candidate_id`, `final_gate_result`, `candidate_id`, `operation_layer_notional_cap`, `preflight_id`, `required_facts_confirmed`, `preflight_facts`) are properly mapped to Chinese Owner-friendly labels before rendering in any Owner-facing UI |
| **Why** | CLAUDE-AUDIT-001 found 13 INFO-severity API fields that use internal names. These are acceptable at the API layer but must not leak into rendered UI. The `owner-runtime-console` already maps correctly (`calls_final_gate` → `不会执行安全判定`). The `trading-console` mapping needs verification. |
| **Allowed files** | `trading-console/src/lib/ownerViewModel.ts`, `trading-console/src/pages/*.tsx`, `owner-runtime-console/src/console/model.ts`, `owner-runtime-console/src/api/ownerSourceReadiness.ts` |
| **Forbidden files** | `src/interfaces/*.py`, `src/application/`, `tests/`, `scripts/`, `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | (1) Audit every API field → UI label mapping in both consoles. (2) Ensure no internal field name appears as a rendered label. (3) Add mapping for any unmapped internal fields. (4) Document the mapping table. |
| **Verification** | (1) Grep rendered output (or snapshot tests) for internal field names — zero hits. (2) All mapped labels are Chinese Owner-friendly. |
| **Done When** | Every internal API field has a verified Chinese Owner-friendly label mapping in both consoles |
| **Hard Stop** | Do not modify API response models. Do not change backend source. |
| **Risk** | Low — verification + label mapping only |
| **Depends On** | UIG-002 decision |
| **Owner** | Claude |
| **Dispatch Timing** | Post-P1 |

### UIG-005: Visual QA Gate + Forbidden Term Scanner Hardening

| Field | Value |
|---|---|
| **Task ID** | UIG-005 |
| **Goal** | Harden the visual QA gate to automatically fail on forbidden engineering terms in primary UI, and add a standalone forbidden-term scanner script usable by both consoles |
| **Why** | The current `npm run visual:qa` in `owner-runtime-console` checks for forbidden terms but the scanner logic is embedded in the visual QA script. A standalone scanner enables CI integration, cross-console reuse, and faster developer feedback. |
| **Allowed files** | `owner-runtime-console/scripts/visual-qa.ts`, `owner-runtime-console/scripts/forbidden-term-scan.ts` (new), `owner-runtime-console/package.json`, `trading-console/scripts/forbidden-term-scan.ts` (new, if UIG-002 selects option b), `trading-console/package.json` |
| **Forbidden files** | `src/`, `tests/`, `scripts/` (backend), `deploy/`, `live-config.env`, `.env*` |
| **Requirements** | (1) Extract forbidden-term scanning into a standalone script. (2) Script reads all `*.tsx` files, parses rendered JSX text content, and checks against the forbidden term list from `docs/current/OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT.md`. (3) Whitelist internal data-model keys (`calls_final_gate`, `calls_operation_layer`, `creates_candidate`, `creates_authorization`). (4) Add npm script `scan:forbidden-terms` to both consoles. (5) Integrate into existing `visual:qa` pipeline. (6) Generate machine-readable report (JSON) for CI. |
| **Verification** | (1) `npm run scan:forbidden-terms` passes on current codebase. (2) Intentionally inject a banned term — scanner catches it. (3) JSON report is generated. |
| **Done When** | Standalone scanner exists, passes on current codebase, and is integrated into visual:qa |
| **Hard Stop** | Do not modify backend source. Do not relax the forbidden term list. |
| **Risk** | Low — additive tooling |
| **Depends On** | UIG-001 landed |
| **Owner** | Claude |
| **Dispatch Timing** | Post-P1 |

### UIG-006: docs/current UI Contract Dedup and SSOT Reference Cleanup

| Field | Value |
|---|---|
| **Task ID** | UIG-006 |
| **Goal** | Consolidate UI governance rules from 3 overlapping docs into a single SSOT reference chain and remove duplicated forbidden-term lists, layout rules, and component inventories |
| **Why** | Current UI governance is spread across 3 files with overlapping content: (1) `OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT.md` — element contract, forbidden terms, layout, components, data projection. (2) `OWNER_RUNTIME_CONSOLE_UI_VISUAL_GOVERNANCE.md` — visual governance, layout hard rules, forbidden terms, component governance, QA gate. (3) `STRATEGY_CONTROL_BOARD_CONTRACT.md` — row fields, language rules, forbidden terms. All three define the same forbidden term list independently. Any update to the list requires 3 coordinated edits. |
| **Allowed files** | `docs/current/OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT.md`, `docs/current/OWNER_RUNTIME_CONSOLE_UI_VISUAL_GOVERNANCE.md`, `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` |
| **Forbidden files** | `src/`, `tests/`, `scripts/`, `deploy/`, `trading-console/`, `owner-runtime-console/src/`, `live-config.env`, `.env*` |
| **Requirements** | (1) Designate `OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT.md` as SSOT for: element contract, forbidden terms, allowed terms, data projection, component inventory. (2) Designate `OWNER_RUNTIME_CONSOLE_UI_VISUAL_GOVERNANCE.md` as SSOT for: layout hard rules, visual QA gate, design authority, locked decisions. (3) Designate `STRATEGY_CONTROL_BOARD_CONTRACT.md` as SSOT for: row fields, internal lifecycle mapping, notification rules. (4) Replace duplicated sections with SSOT cross-references: "See `docs/current/OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT.md` § Forbidden Main UI Terms". (5) Ensure the forbidden term list is defined exactly once. (6) Add `last_verified` date to each file. |
| **Verification** | (1) `grep -rn "FinalGate" docs/current/OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT.md docs/current/OWNER_RUNTIME_CONSOLE_UI_VISUAL_GOVERNANCE.md docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` — forbidden term list appears in exactly one file. (2) Cross-references are valid. (3) No content lost. |
| **Done When** | Forbidden term list defined once; cross-references valid; no duplicated governance rules |
| **Hard Stop** | Do not remove any governance rule — only deduplicate. Do not change the forbidden term list content. |
| **Risk** | Low — doc-only reorganization |
| **Depends On** | Mainline acceptance complete |
| **Owner** | Claude |
| **Dispatch Timing** | Post-P1 |

---

## Do-Not-Dispatch During Live Acceptance

The following UI changes must **not** be dispatched during mainline acceptance. They risk visual disruption, merge conflict with acceptance PRs, or scope creep.

| Card | Change | Why Blocked |
|---|---|---|
| UIG-003 | trading-console label remediation (62+ files) | Large diff, visual disruption, conflicts with acceptance screenshots |
| UIG-004 | API field mapping verification | Touches both consoles' view model layers |
| UIG-005 | Visual QA scanner hardening | Changes QA pipeline behavior during acceptance runs |
| UIG-006 | docs/current UI contract dedup | Multi-file doc reorganization during acceptance review cycle |
| UIG-008 | trading-console route/sidebar audit | Navigation label changes disrupt acceptance testing |
| Any | New pages or navigation items in owner-runtime-console | Scope creep during acceptance |
| Any | Forbidden term list changes | Changes governance baseline during acceptance |
| Any | Component library additions | Visual inconsistency risk during acceptance |

**Safe during acceptance:**
- UIG-001 (anti-regression scanner — additive, no visual change)
- Bug fixes that restore compliance with existing contracts
- Screenshot updates for visual:qa reference images

---

## Suggested Sequence

```text
Phase 0 — Now (during acceptance)
  UIG-001  owner-runtime-console anti-regression scanner

Phase 1 — Post-acceptance (immediate)
  UIG-002  trading-console classification decision (Codex)
  [blocks UIG-003, UIG-008]

Phase 2 — Post-acceptance P1
  UIG-003  trading-console label remediation (if Owner-visible)
  UIG-004  API field mapping verification
  UIG-006  docs/current SSOT dedup

Phase 3 — Post-P1
  UIG-005  Visual QA scanner hardening
  UIG-008  trading-console route/sidebar audit (if Owner-visible)
```

---

## Summary Table

| Card | Title | Risk | Owner | Can Dispatch Now? |
|---|---|---|---|---|
| UIG-001 | Anti-Regression Gate | Low | Claude | Yes |
| UIG-002 | Classification Decision | Medium | Codex | After acceptance |
| UIG-003 | Label Remediation | Medium | Claude | After UIG-002 |
| UIG-004 | API Field Mapping | Low | Claude | After UIG-002 |
| UIG-005 | Scanner Hardening | Low | Claude | After UIG-001 |
| UIG-006 | SSOT Dedup | Low | Claude | After acceptance |
| UIG-007 | Do-Not-Dispatch List | — | Codex (ref) | Reference |
| UIG-008 | Route/Sidebar Audit | Low | Claude | After UIG-002 |

---

## Appendix: Forbidden Term Reference

Canonical list (defined in `docs/current/OWNER_RUNTIME_CONSOLE_UI_ELEMENT_CONTRACT.md`):

```text
FinalGate
Operation Layer
RequiredFacts
candidate
authorization
preflight
proof
route
refId
blocker code
runtime grant
next step
下一步
检查器
系统自动观察中
暂无可用机会
```

These terms are forbidden in primary navigation, homepage cards, table headers, primary buttons, and Owner action labels. They may appear only inside collapsed technical detail, audit, or developer surfaces.
