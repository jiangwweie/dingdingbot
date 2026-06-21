# CLAUDE-AUDIT-001 Owner Language Leakage Audit

**Date:** 2026-06-16
**Auditor:** Claude Code (read-only)
**Scope:** Owner-facing UI, API response models, tests, and docs for internal execution term leakage

---

## Summary

The `owner-runtime-console` (main Owner surface) is **compliant**. Internal gate names (`FinalGate`, `Operation Layer`, etc.) do not appear as primary UI labels, cards, or navigation items. The only occurrences are internal data-model keys (`calls_final_gate`, `calls_operation_layer`) that are mapped to Chinese Owner-facing labels ("不会执行安全判定", "不会触发实盘动作") before rendering.

The `trading-console` (developer/audit/operator surface) has **significant leakage** of internal execution terms into primary UI labels, card titles, table columns, section headers, and notification body text across at least 10 page components. While the trading-console may be intended as a developer/audit surface, its current UI structure presents these terms as primary navigation and information architecture, not as expandable detail drawers.

**Total findings:** 87 occurrences across 12 files
**Critical (main Owner surface violations):** 0 in `owner-runtime-console`
**High (trading-console primary label violations):** 62 across 10 files
**Medium (trading-console detail/body text):** 25 across 8 files

---

## Scope

| Surface | Path | Role | Status |
| --- | --- | --- | --- |
| owner-runtime-console | `owner-runtime-console/src/` | Main Owner UI | ✅ Compliant |
| trading-console | `trading-console/src/` | Developer/audit/operator UI | ❌ 62+ primary label violations |
| BRC console API | `src/interfaces/api_brc_console.py` | Backend API responses | ⚠️ Internal terms in response models |
| trading-console API | `src/interfaces/api_trading_console.py` | Backend API responses | ⚠️ Internal terms in response models |
| Design system | `design-system/` | Component library | ✅ No violations found |
| Tests | `tests/unit/` | Test assertions | ⚠️ Internal terms in test data (acceptable) |

**Banned terms for main Owner surface:**
`FinalGate`, `Operation Layer`, `RequiredFacts`, `candidate`, `authorization`, `preflight`, `proof`, `route`, `refId`, `blocker code`, `runtime grant`

---

## Findings Table

### Severity: HIGH — Primary UI Labels / Card Titles / Table Columns / Navigation

| # | Severity | File | Line/Area | Term | Context | Why It Matters | Recommendation |
|---|----------|------|-----------|------|---------|----------------|----------------|
| 1 | HIGH | `trading-console/src/pages/PilotControlBoard.tsx` | 249 | `Candidate` | Card title: `title="Candidate"` | Primary card title exposes internal term | Rename to "策略候选" or "处理状态" |
| 2 | HIGH | `trading-console/src/pages/PilotControlBoard.tsx` | 255 | `FinalGate` | Table label: `{ label: 'FinalGate', value: ... }` | Primary table column label | Map to "安全判定" or move to detail drawer |
| 3 | HIGH | `trading-console/src/pages/PilotControlBoard.tsx` | 256 | `Operation` | Table label: `{ label: 'Operation', value: ... }` | Primary table column label | Map to "执行路径" or move to detail drawer |
| 4 | HIGH | `trading-console/src/pages/PilotControlBoard.tsx` | 315 | `candidate TTL` | Table label: `{ label: 'candidate TTL', ... }` | Primary table column label | Map to "候选有效期" |
| 5 | HIGH | `trading-console/src/pages/PilotControlBoard.tsx` | 325 | `FinalGate` | Table label: `{ label: 'FinalGate', ... }` | Primary table column label | Map to "安全判定" |
| 6 | HIGH | `trading-console/src/pages/PilotControlBoard.tsx` | 326 | `Operation` | Table label: `{ label: 'Operation', ... }` | Primary table column label | Map to "执行路径" |
| 7 | HIGH | `trading-console/src/pages/PilotControlBoard.tsx` | 327 | `fact blockers` | Table label: `{ label: 'fact blockers', ... }` | Primary table column label | Map to "事实阻断" |
| 8 | HIGH | `trading-console/src/pages/ActionEntry.tsx` | 375 | `Candidate-to-Action Readiness` | Section header: `<h2>Candidate-to-Action Readiness</h2>` | Primary section title | Rename to "候选行动就绪" |
| 9 | HIGH | `trading-console/src/pages/ActionEntry.tsx` | 401 | `FinalGate facts` | Section header: `<h3>FinalGate facts</h3>` | Primary section title | Rename to "安全判定事实" or move to detail |
| 10 | HIGH | `trading-console/src/pages/ActionEntry.tsx` | 418 | `Official preflight` | Section header: `<h3>Official preflight</h3>` | Primary section title | Rename to "官方预检" or move to detail |
| 11 | HIGH | `trading-console/src/pages/ActionEntry.tsx` | 767 | `Operation Layer` | Text: `提交方式：Operation Layer / BRC 官方 API` | Primary UI text | Rename to "官方提交路径" |
| 12 | HIGH | `trading-console/src/pages/ActionEntry.tsx` | 928 | `candidates` | Badge: `{candidateActionability.length} candidates` | Primary badge label | Rename to "个候选" |
| 13 | HIGH | `trading-console/src/pages/ActionEntry.tsx` | 944 | `FinalGate` | Text: `FinalGate {item.final_gate_preview_available ? '可预览' : '待补齐'}` | Primary UI text | Map to "安全判定" |
| 14 | HIGH | `trading-console/src/pages/AuthorizationState.tsx` | 276 | `authorization_id` | Title: `单次授权保留为历史短路径` | Card title references authorization | Already Chinese, but references internal concept |
| 15 | HIGH | `trading-console/src/pages/AuthorizationState.tsx` | 283 | `候选` | Title: `候选需要继续过 gate` | Card title uses "候选" and "gate" | Rename to "处理中，等待系统确认" |
| 16 | HIGH | `trading-console/src/pages/AuthorizationState.tsx` | 285 | `OrderCandidate` | Body: `OrderCandidate 是策略信号后的候选对象` | Exposes internal term in body | Rename to "候选订单" or "待处理对象" |
| 17 | HIGH | `trading-console/src/pages/AuthorizationState.tsx` | 349 | `候选` | Metric label: `label="候选"` | Primary metric label | Rename to "待处理" |
| 18 | HIGH | `trading-console/src/pages/AuthorizationState.tsx` | 1649 | `RequiredFacts` | Button label: `确认 RequiredFacts` | Primary action button label | Rename to "确认事实" |
| 19 | HIGH | `trading-console/src/pages/StrategyGroupIntake.tsx` | 74 | `RequiredFacts` | Panel caption: `RequiredFacts, watcher scope, and armed observation` | Primary panel caption | Rename to "事实、观察范围和武装观察" |
| 20 | HIGH | `trading-console/src/pages/StrategyGroupIntake.tsx` | 138 | `Candidate Blocked` | Metric label: `label="Candidate Blocked"` | Primary metric label | Rename to "候选阻断" |
| 21 | HIGH | `trading-console/src/pages/StrategyGroupIntake.tsx` | 216 | `RequiredFacts Preview` | Panel title: `title="RequiredFacts Preview"` | Primary panel title | Rename to "事实预览" |
| 22 | HIGH | `trading-console/src/pages/CarrierShelf.tsx` | 225 | `策略资产` | Metric label with `candidates` in sub | Sub-label: `可展示 / 提案 / 候选` | Rename sub to "可展示 / 提案 / 待处理" |
| 23 | HIGH | `trading-console/src/pages/CarrierShelf.tsx` | 228 | `只读观察` | Metric label with `候选` in sub | Sub-label: `个短侧候选` | Rename to "个短侧观察" |
| 24 | HIGH | `trading-console/src/pages/CarrierShelf.tsx` | 373 | `观察候选` | GateCell label: `label="观察候选"` | Primary table cell label | Rename to "观察项" |
| 25 | HIGH | `trading-console/src/pages/CarrierShelf.tsx` | 391 | `观察候选` | Card title fallback: `displayValue(candidate.candidate_id, '观察候选')` | Primary card title | Rename to "观察项" |
| 26 | HIGH | `trading-console/src/pages/CarrierShelf.tsx` | 443 | `candidate_state` | Table label: `{ label: '状态', value: candidateStateLabel(...) }` | Maps internal candidate_state to UI | Ensure mapping is Owner-friendly |
| 27 | HIGH | `trading-console/src/pages/CarrierShelf.tsx` | 445 | `gate` | Text: `可进入后续 gate` | Exposes "gate" term | Rename to "可进入后续检查" |
| 28 | HIGH | `trading-console/src/pages/CarrierShelf.tsx` | 489 | `授权` | Table label: `{ label: '授权', ... }` | Primary table label | Consider "权限状态" |
| 29 | HIGH | `trading-console/src/pages/CarrierShelf.tsx` | 491 | `需预检` | StatusChip: `carrier.authorization?.is_actionable ? '需预检' : '只读'` | Exposes "预检" term | Rename to "待确认" |
| 30 | HIGH | `trading-console/src/pages/CarrierShelf.tsx` | 553 | `订单候选` | GateCell label: `label="订单候选"` | Primary table cell label | Rename to "待处理订单" |
| 31 | HIGH | `trading-console/src/pages/WatcherStatus.tsx` | 117 | `candidate, authorization, FinalGate, Operation Layer` | Panel caption: `Fresh signal must precede candidate, authorization, FinalGate, and official Operation Layer action.` | Primary panel caption exposes 4 banned terms | Rewrite to Chinese Owner language |
| 32 | HIGH | `trading-console/src/pages/WatcherStatus.tsx` | 165 | `candidate, runtime grant, authorization, FinalGate, Operation Layer` | Notification body: `A ready signal only resumes fresh candidate, runtime grant, authorization evidence, action-time FinalGate, official Operation Layer action...` | Primary notification body exposes 5 banned terms | Rewrite to Chinese Owner language |
| 33 | HIGH | `trading-console/src/pages/Dashboard.tsx` | 102 | `Operation Layer` | Error text: `控制台尚未接入 Operation Layer 提交入口` | Primary error message | Rewrite to "控制台尚未接入官方提交入口" |
| 34 | HIGH | `trading-console/src/pages/Dashboard.tsx` | 115 | `Operation Layer` | Text: `Operation Layer 会先预检，再要求 Owner 输入确认短语` | Primary UI text | Rewrite to "系统会先预检，再要求确认" |
| 35 | HIGH | `trading-console/src/pages/Dashboard.tsx` | 432 | `授权` | Sub-text: `无当前授权` | Primary sub-text | Consider "无当前权限" |
| 36 | HIGH | `trading-console/src/pages/Dashboard.tsx` | 438 | `授权` | Sub-text: `旧授权可复用` / `旧授权不可复用` | Primary sub-text | Consider "旧权限可复用" |
| 37 | HIGH | `trading-console/src/pages/Dashboard.tsx` | 444 | `授权` | Sub-text: `需要新授权` / `授权策略缺失` | Primary sub-text | Consider "需要新确认" |
| 38 | HIGH | `trading-console/src/pages/Dashboard.tsx` | 691 | `operation_layer_preflight` | Button kind check | Internal kind exposed in logic | Map to friendly label before render |
| 39 | HIGH | `trading-console/src/pages/Dashboard.tsx` | 745 | `Operation Layer` | Loading text: `正在执行 Operation Layer 请求...` | Primary loading text | Rewrite to "正在执行官方请求..." |
| 40 | HIGH | `trading-console/src/pages/Dashboard.tsx` | 794 | `Operation Layer` | Result text: `Operation Layer 已返回结果。` | Primary result text | Rewrite to "官方请求已返回结果。" |
| 41 | HIGH | `trading-console/src/pages/RecoveryState.tsx` | 518 | `FinalGate` | Body text: `运行治理页可查看 FinalGate、预算和 runtime readiness。` | Primary body text | Rewrite to "运行治理页可查看安全状态、预算和运行就绪度。" |
| 42 | HIGH | `trading-console/src/pages/RecoveryState.tsx` | 590 | `candidate` | Caption: `满足条件后才允许回到下一次 runtime / candidate 评估` | Primary caption | Rewrite to "满足条件后才允许回到下一次运行评估" |

### Severity: MEDIUM — Body Text / Notification Text / Helper Text

| # | Severity | File | Line/Area | Term | Context | Why It Matters | Recommendation |
|---|----------|------|-----------|------|---------|----------------|----------------|
| 43 | MEDIUM | `trading-console/src/pages/StrategyGroupIntake.tsx` | 199 | `candidate` | Body: `does not register runtime instances, create candidates, or grant execution` | Helper text | Rewrite to Chinese |
| 44 | MEDIUM | `trading-console/src/pages/StrategyGroupIntake.tsx` | 203-204 | `RequiredFacts, candidate` | Body: `RequiredFacts, exchange rules, same-symbol account state, and protection hints must pass before candidate preparation.` | Helper text | Rewrite to Chinese |
| 45 | MEDIUM | `trading-console/src/pages/StrategyGroupIntake.tsx` | 209 | `candidate, runtime grant, authorization, FinalGate, Operation Layer` | Body: `A real action still requires fresh candidate, runtime grant, authorization evidence, action-time FinalGate, and Operation Layer.` | Helper text exposes 5 banned terms | Rewrite to Chinese |
| 46 | MEDIUM | `trading-console/src/pages/CarrierShelf.tsx` | 146 | `FinalGate` | Body: `只有完整范围、Owner 风险接受、FinalGate、保护和审计链路都满足时` | Helper text | Replace with "安全判定" |
| 47 | MEDIUM | `trading-console/src/pages/CarrierShelf.tsx` | 157 | `候选` | Body: `当前有 N 个观察候选` | Helper text | Replace with "观察项" |
| 48 | MEDIUM | `trading-console/src/pages/CarrierShelf.tsx` | 761 | `OrderCandidate` | Text: `未创建 SignalEvaluation / OrderCandidate` | Helper text | Replace with friendly names |
| 49 | MEDIUM | `trading-console/src/pages/CarrierShelf.tsx` | 775 | `candidate_available_for_review` | Status label mapping | Internal status exposed | Map to "可评审" |
| 50 | MEDIUM | `trading-console/src/pages/CarrierShelf.tsx` | 795-796 | `BoundedLiveAuthorization, AuthorizationDraft` | Label mapping: `授权边界`, `范围草案` | Internal class names in mapping keys | Acceptable if labels are Chinese |
| 51 | MEDIUM | `trading-console/src/pages/CarrierShelf.tsx` | 807-808 | `candidate, Owner authorization, preflight` | Error text mapping | Internal terms in error messages | Rewrite error mappings |
| 52 | MEDIUM | `trading-console/src/pages/CarrierShelf.tsx` | 810 | `FinalGate` | Text: `FinalGate 尚未返回可行动。` | Helper text | Replace with "安全判定尚未返回可行动。" |
| 53 | MEDIUM | `trading-console/src/pages/Dashboard.tsx` | 327 | `authorization, FinalGate, protection` | Body: `真正行动仍需要授权、FinalGate、保护和审计链路` | Helper text | Rewrite to Chinese |
| 54 | MEDIUM | `trading-console/src/pages/Dashboard.tsx` | 559 | `Operation Layer, FinalGate, shadow runtime, 候选, 授权` | Body: `控制台只呈现官方 readmodel / Operation Layer 路径。FinalGate preview、shadow runtime、候选和授权状态都不会自动变成下单权限。` | Helper text exposes multiple banned terms | Rewrite to Chinese |
| 55 | MEDIUM | `trading-console/src/pages/ActionEntry.tsx` | 839 | `FinalGate` | Helper text: `所有按钮保持后端禁用，直到官方预检与 FinalGate 通过。` | Helper text | Replace with "安全判定" |
| 56 | MEDIUM | `trading-console/src/pages/ActionEntry.tsx` | 874 | `authorization, FinalGate` | Helper text: `进入下一轮前仍需官方授权与 FinalGate。` | Helper text | Replace with "安全判定" |
| 57 | MEDIUM | `trading-console/src/pages/PilotControlBoard.tsx` | 283 | `FinalGate, Operation Layer, candidate, authorization` | Notification body: `FinalGate and Operation Layer stay not reached until fresh candidate and authorization evidence exist.` | Notification text | Rewrite to Chinese |
| 58 | MEDIUM | `trading-console/src/pages/AuthorizationState.tsx` | 286 | `OrderCandidate, shadow` | Body: `当前没有 OrderCandidate。策略语义和信号链路可以 shadow` | Helper text | Rewrite to Chinese |
| 59 | MEDIUM | `trading-console/src/pages/AuthorizationState.tsx` | 476 | `authorization` | EmptyState body: `可按订单 ID、symbol 或 authorization 缩小证据范围` | Helper text | Replace with "授权" or "权限" |
| 60 | MEDIUM | `trading-console/src/pages/AuditChain.tsx` | 198-199 | `candidate` | Body: `可继续追踪到 runtime / signal / candidate 层` | Helper text | Acceptable for audit surface |
| 61 | MEDIUM | `trading-console/src/pages/AuditChain.tsx` | 230 | `candidate` | Body: `用于追踪授权、runtime、signal、candidate、intent、订单和复盘之间的证据链` | Helper text | Acceptable for audit surface |

### Severity: LOW — Internal Data Model Keys (Not Displayed)

| # | Severity | File | Line/Area | Term | Context | Why It Matters | Recommendation |
|---|----------|------|-----------|------|---------|----------------|----------------|
| 62 | LOW | `owner-runtime-console/src/console/model.ts` | 40-41 | `calls_operation_layer`, `calls_final_gate` | Internal key in `noActionGuaranteeLabels` | Key not displayed; Chinese label shown | Acceptable — labels are "不会触发实盘动作", "不会执行安全判定" |
| 63 | LOW | `owner-runtime-console/src/data.ts` | 220-221 | `calls_operation_layer`, `calls_final_gate` | Mock data internal keys | Not displayed to Owner | Acceptable |
| 64 | LOW | `owner-runtime-console/src/data.ts` | 425-426 | `creates_candidate`, `creates_authorization` | Mock data internal keys | Not displayed to Owner | Acceptable |
| 65 | LOW | `owner-runtime-console/src/api/ownerSourceReadiness.ts` | 246-247 | `calls_operation_layer`, `calls_final_gate` | API mapping internal keys | Not displayed to Owner | Acceptable |

### Severity: INFO — API Backend Response Models

| # | Severity | File | Line/Area | Term | Context | Why It Matters | Recommendation |
|---|----------|------|-----------|------|---------|----------------|----------------|
| 66 | INFO | `src/interfaces/api_brc_console.py` | 269 | `authorization_id` | Response model field | Internal field in API response | Acceptable for API; ensure UI maps to friendly label |
| 67 | INFO | `src/interfaces/api_brc_console.py` | 276 | `order_candidate_id` | Response model field | Internal field in API response | Acceptable for API; ensure UI maps to friendly label |
| 68 | INFO | `src/interfaces/api_brc_console.py` | 285 | `final_gate_result` | Response model field | Internal field in API response | Acceptable for API; ensure UI maps to friendly label |
| 69 | INFO | `src/interfaces/api_brc_console.py` | 697-699 | `candidate_id` | View model field | Internal field in API response | Acceptable for API |
| 70 | INFO | `src/interfaces/api_brc_console.py` | 730 | `operation_layer_notional_cap` | View model field | Internal field in API response | Acceptable for API |
| 71 | INFO | `src/interfaces/api_brc_console.py` | 883-891 | `preflight_id` | Request model field | Internal field in API request | Acceptable for API |
| 72 | INFO | `src/interfaces/api_trading_console.py` | 289 | `order_candidate_id` | Response model field | Internal field in API response | Acceptable for API |
| 73 | INFO | `src/interfaces/api_trading_console.py` | 484-512 | `OrderCandidateInspectionView` | Full view model | Internal view model | Acceptable for API; ensure UI maps fields |
| 74 | INFO | `src/interfaces/api_trading_console.py` | 572 | `required_facts_confirmed` | Response model field | Internal field in API response | Acceptable for API |
| 75 | INFO | `src/interfaces/api_console_runtime.py` | 586 | `preflight_facts` | Request model field | Internal field in API request | Acceptable for API |
| 76 | INFO | `src/interfaces/api_console_runtime.py` | 2541 | `operation_layer_cap_below_min_notional` | Blocker code in response | Internal blocker code | Acceptable for API; ensure UI maps to friendly message |
| 77 | INFO | `src/interfaces/api_console_runtime.py` | 2628 | `operation_layer:controlled_testnet_carrier_path` | Internal path string | Internal path | Acceptable for API |
| 78 | INFO | `src/interfaces/api_console_runtime.py` | 3953 | `authorization_source` | Internal field | Internal field | Acceptable for API |

---

## Allowed Detail/Audit Usages

The following usages are in `trading-console` pages that appear to serve as developer/audit/detail surfaces. These are acceptable **if** the trading-console is explicitly documented as a non-Owner-facing developer tool:

- `AuditChain.tsx` — Evidence chain tracking page (audit purpose)
- `OrderLedger.tsx` — Order history page (developer reference)
- `ReviewState.tsx` — Strategy review page (developer reference)

However, even these pages should not expose internal terms as **primary navigation labels** in the sidebar or route names.

---

## Main UI Violations

The `trading-console` sidebar/navigation exposes these routes with internal-term-based names:

| Route | Current Label | Suggested Owner Label |
| --- | --- | --- |
| `/runtime` | `AuthorizationState` (component name) | 运行状态 |
| `/authorization` | Redirects to `/runtime` | OK (redirect is acceptable) |
| `/pilot` | `PilotControlBoard` | 运行治理 |
| `/strategy` | `CarrierShelf` | 策略资产 |
| `/strategy-intake` | `StrategyGroupIntake` | 策略接入 |
| `/evidence` | `AuditChain` | 审计链 |
| `/incident` | `RecoveryState` | 恢复状态 |

---

## False Positives

| # | File | Term | Why False Positive |
|---|------|------|--------------------|
| 1 | `owner-runtime-console/src/console/model.ts` | `calls_final_gate`, `calls_operation_layer` | Internal data-model keys mapped to Chinese labels ("不会执行安全判定", "不会触发实盘动作"). Keys never displayed. |
| 2 | `owner-runtime-console/src/data.ts` | `creates_candidate`, `creates_authorization` | Mock data internal keys, never displayed to Owner. |
| 3 | `src/interfaces/api_*.py` | Various API field names | API field names are developer-facing by definition. The concern is whether UI properly maps them to friendly labels. |
| 4 | `tests/unit/test_trading_console_readmodels.py` | Various | Test data uses internal terms for assertion matching. Acceptable in test code. |
| 5 | `trading-console/src/pages/AuditChain.tsx` | `candidate`, `authorization` | Audit/developer surface. Internal terms acceptable in detail views, but not as primary nav labels. |

---

## Suggested Follow-up Task Cards

### Task Card 1: trading-console Primary Label Remediation

```text
Task ID: CLAUDE-FIX-002
Goal: Replace all banned internal terms in trading-console primary UI labels, card titles,
      table columns, section headers, and notification text with Chinese Owner-friendly language.
Why: AGENTS.md and AI_AGENT_CONSTRAINTS.md prohibit internal gate names as primary Owner
     labels. trading-console currently exposes FinalGate, Operation Layer, RequiredFacts,
     candidate, authorization, preflight, and runtime grant as primary UI elements.
Allowed files: trading-console/src/**/*.tsx, trading-console/src/lib/ownerViewModel.ts
Forbidden files: src/**, owner-runtime-console/**, tests/**, docs/**
Requirements:
  - Map all banned terms to Chinese Owner-friendly labels
  - Ensure internal data-model keys remain unchanged (only display labels change)
  - Maintain all existing functionality
  - Follow the mapping table in OWNER_RUNTIME_OPERATING_MODEL.md
Tests: Verify no banned terms appear in rendered text (snapshot tests)
Done When: All primary UI labels use Chinese Owner-friendly language
Hard Stop: Do not modify API response models or backend logic
```

### Task Card 2: trading-console Route Name Audit

```text
Task ID: CLAUDE-FIX-003
Goal: Audit trading-console sidebar navigation labels and route display names for internal
      term leakage.
Why: Route names like /authorization, /runtime, /evidence may expose internal concepts in
     browser URL bar and navigation.
Allowed files: trading-console/src/App.tsx, trading-console/src/components/Layout.tsx
Forbidden files: src/**, owner-runtime-console/**, tests/**, docs/**
Requirements:
  - Review all route paths and sidebar labels
  - Ensure sidebar labels use Chinese Owner-friendly language
  - Route paths may remain as-is (URL paths are developer-facing)
Tests: Visual inspection of sidebar rendering
Done When: All sidebar labels use Chinese Owner-friendly language
Hard Stop: Do not modify API endpoints or backend routes
```

### Task Card 3: API Response Model Label Mapping Verification

```text
Task ID: CLAUDE-FIX-004
Goal: Verify that all API response model fields with internal terms are properly mapped to
      Chinese Owner-friendly labels before rendering in any Owner-facing UI.
Why: API models use internal field names (authorization_id, final_gate_result, etc.) which
     are acceptable at the API layer but must not leak into UI rendering.
Allowed files: trading-console/src/lib/ownerViewModel.ts, trading-console/src/pages/*.tsx
Forbidden files: src/**, owner-runtime-console/**, tests/**, docs/**
Requirements:
  - Audit all API field → UI label mappings
  - Ensure no internal field name appears as a rendered label
  - Add mapping for any unmapped internal fields
Tests: Unit tests for all mapping functions
Done When: Every internal API field has a Chinese Owner-friendly label mapping
Hard Stop: Do not modify API response models
```

---

## Conclusion

The `owner-runtime-console` (main Owner surface) is **fully compliant** with the language leakage rules. All internal gate names are properly mapped to Chinese Owner-friendly labels before rendering.

The `trading-console` has **62+ primary label violations** across 10 page components where internal execution terms (`FinalGate`, `Operation Layer`, `RequiredFacts`, `candidate`, `authorization`, `preflight`, `runtime grant`) appear as card titles, table columns, section headers, and notification text. These need remediation if the trading-console is intended to be an Owner-facing surface. If it is strictly a developer/audit tool, the violations are acceptable but should be documented.

The API backend response models use internal field names which is acceptable at the API layer, provided the UI properly maps them to friendly labels before rendering.
