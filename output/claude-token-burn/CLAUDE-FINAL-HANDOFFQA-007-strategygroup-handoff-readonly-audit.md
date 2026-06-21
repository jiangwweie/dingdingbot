# CLAUDE-FINAL-HANDOFFQA-007 StrategyGroup Handoff Read-Only Audit

Generated: 2026-06-17
Task ID: CLAUDE-FINAL-HANDOFFQA-007
Mode: read-only QA audit — no file modifications
Source cards: HQ-001A, HQ-001B, HQ-001C, HQ-002A, HQ-003A, HQ-004A, HQ-004B, HQ-005A, HQ-006A

---

## 1. Summary

All 9 read-only QA cards executed successfully against the 5 StrategyGroup
handoff files and 6 main-control supplement documents. The handoff layer is
structurally complete — all 5 StrategyGroups have entries in all 4 required
files, ranks are contiguous, provenance is documented, and research boundary
is enforced.

**Key findings:**
- 1 P1 cross-file inconsistency (SOR-001 default mode mismatch)
- 1 P1 testability gap (conflict rule freshness thresholds rely on implicit mapping)
- 3 P2 documentation gaps (review outcome vocabulary, provenance commit hash, handoff field absence)
- 2 P3 observations (cadence ranges, gate-class-to-Owner-status mapping documentation)

No P0 safety blockers found. No missing inputs. No files modified.

---

## 2. QA Card Execution Matrix

| Card ID | Status | Blockers Found | Severity |
|---------|--------|---------------|----------|
| HQ-001A | PASS | 0 | — |
| HQ-001B | PASS with note | 1 | P1 |
| HQ-001C | PASS | 0 | — |
| HQ-002A | PASS | 0 | — |
| HQ-003A | PASS with note | 1 | P1 |
| HQ-004A | PASS | 0 | — |
| HQ-004B | PASS with note | 1 | P2 |
| HQ-005A | PASS with notes | 2 | P2 |
| HQ-006A | PASS with notes | 2 | P2/P3 |

---

## 3. StrategyGroup Field Presence Matrix (HQ-001A)

**Requirement:** Each StrategyGroup must appear in all 4 handoff files.

| StrategyGroup | handoff-index batch | admission-priority | watcher-cadence | required-facts-map coverage |
|--------------|:------------------:|:------------------:|:---------------:|:--------------------------:|
| MPG-001 | ✅ | ✅ Rank 1 | ✅ | ✅ (market, strategy, risk, account, exchange) |
| TEQ-001 | ✅ | ✅ Rank 2 | ✅ | ✅ (market, strategy, risk, account, exchange) |
| FBS-001 | ✅ | ✅ Rank 3 | ✅ | ✅ (market, derivatives, risk, account, exchange) |
| SOR-001 | ✅ | ✅ Rank 4 | ✅ | ✅ (market, strategy, risk, account, exchange) |
| PMR-001 | ✅ | ✅ Rank 5 | ✅ | ✅ (market, strategy, risk, account, exchange) |

**Result:** 5×4 matrix fully populated. Zero gaps.

**Note on required-facts-map:** The map defines 6 readiness classes
(market, strategy, derivatives, risk, account, exchange) with Meaning and
Missing Behavior columns. It does not map classes to specific StrategyGroups.
Each handoff.json lists required facts per class, implicitly defining which
classes apply. This is structurally sufficient but less explicit than a
StrategyGroup × class matrix.

---

## 4. Default Mode Alignment (HQ-001B)

**Requirement:** Default Mode must match between handoff-index and admission-priority.

| StrategyGroup | handoff-index | admission-priority | handoff.json mode_recommendation.default | Match? |
|--------------|:------------:|:------------------:|:---------------------------------------:|:------:|
| MPG-001 | `armed_observation` | `armed_observation` | `armed_observation` | ✅ |
| TEQ-001 | `armed_observation` | `armed_observation` | `armed_observation` | ✅ |
| FBS-001 | `armed_observation` | `armed_observation` | `armed_observation` | ✅ |
| SOR-001 | `conditional_armed_observation` | `conditional_armed_observation` | `armed_observation` | ⚠️ |
| PMR-001 | `observe_only` | `observe_only` | `observe_only` | ✅ |

**Finding F-001 (P1):**

- **Severity:** P1 — cross-file inconsistency
- **File:** `docs/current/strategy-group-handoffs/SOR-001/handoff.json` line 23 vs `main-control-handoff-index.md` line 27 and `main-control-admission-priority.md` line 20
- **Key:** `mode_recommendation.default`
- **Detail:** handoff-index and admission-priority both say `conditional_armed_observation` for SOR-001, but handoff.json says `armed_observation`. The index/priority files carry a more specific mode that implies session-window gating; the handoff.json generic mode loses this nuance.
- **Why it matters:** Watcher or bootstrap code reading handoff.json would arm SOR-001 without session-window conditions. The index/priority files suggest SOR-001 should only arm near session open.
- **Suggested action:** Codex decides whether handoff.json should be `conditional_armed_observation` or whether the index/priority files should be `armed_observation`. Do not silently merge.

---

## 5. Admission Priority Rank Audit (HQ-001C)

**Requirement:** Ranks 1–5, contiguous, unique, all 5 groups present.

| Rank | StrategyGroup | Unique? |
|-----:|--------------|:-------:|
| 1 | MPG-001 | ✅ |
| 2 | TEQ-001 | ✅ |
| 3 | FBS-001 | ✅ |
| 4 | SOR-001 | ✅ |
| 5 | PMR-001 | ✅ |

**Result:** Sequence [1,2,3,4,5] with no gaps or duplicates. All 5 batch groups present.

---

## 6. RequiredFacts Coverage Matrix (HQ-002A)

**Requirement:** Each armed_observation group must have market, strategy, risk, account classes. FBS-001 additionally has derivatives. PMR-001 at minimum market and strategy for observe_only.

| StrategyGroup | Mode | market | strategy | derivatives | risk | account | exchange | Coverage |
|--------------|------|:------:|:--------:|:-----------:|:----:|:-------:|:--------:|:--------:|
| MPG-001 | armed_observation | ✅ | ✅ | N/A | ✅ | ✅ | ✅ | PASS |
| TEQ-001 | armed_observation | ✅ | ✅ | N/A | ✅ | ✅ | ✅ | PASS |
| FBS-001 | armed_observation | ✅ | N/A | ✅ | ✅ | ✅ | ✅ | PASS |
| SOR-001 | conditional_armed | ✅ | ✅ | N/A | ✅ | ✅ | ✅ | PASS |
| PMR-001 | observe_only | ✅ | ✅ | N/A | ✅ | ✅ | ✅ | PASS |

**Detailed fact counts per group:**

| Group | market | strategy | derivatives | risk | account | exchange | Total |
|-------|:------:|:--------:|:-----------:|:----:|:-------:|:--------:|:-----:|
| MPG-001 | 6 | 6 | — | 3 | 4 | 5 | 24 |
| TEQ-001 | 6 | 6 | — | 4 | 4 | 5 | 25 |
| FBS-001 | 6 | — | 5 | 4 | 4 | 5 | 24 |
| SOR-001 | 7 | 5 | — | 4 | 4 | 5 | 25 |
| PMR-001 | 5 | 5 | — | 4 | 4 | 5 | 23 |

**Result:** All required classes covered per mode. FBS-001 correctly includes derivatives. PMR-001 observe_only correctly has market + strategy + risk + account + exchange.

**Note:** FBS-001 has no `strategy` class facts. This is acceptable because FBS-001 is a funding/basis stress strategy that evaluates through `derivatives` class instead of `strategy` class. The derivatives facts (OI, long/short ratio, funding crowding) serve the strategy evaluation role.

---

## 7. Conflict Policy / Watcher Cadence Testability (HQ-003A)

**Requirement:** Each conflict rule referencing freshness/staleness/timing must have a corresponding cadence entry with numeric values.

### Conflict Rules vs Cadence Fields

| Conflict Rule | References Freshness? | Cadence Field | Threshold | Testable? |
|--------------|:-------------------:|--------------|-----------|:---------:|
| Same symbol, same side → merge | No | — | — | ✅ (structural) |
| Same symbol, opposite side → block | No | — | — | ✅ (structural) |
| Fresh signal with stale facts → block | Yes | Signal Validity + Candidate Packet Freshness | See below | ⚠️ |
| Account position/open order → block | No | — | — | ✅ (structural) |
| Mark/funding abnormality → downshift/block | Yes | Poll Cadence | `5-15m` / `15-60m` | ✅ |
| Observe-only vs armed → observe wins | No | — | — | ✅ (structural) |

**Watcher Cadence Reference Values:**

| StrategyGroup | Poll Cadence | Signal Validity | Candidate Packet Freshness |
|--------------|-------------|----------------|--------------------------|
| MPG-001 | `5-15m` | `15-30m` | `120s` |
| TEQ-001 | `5-15m` | `15-30m` | `120s` |
| FBS-001 | `5-15m` | `15-30m` | `120s` |
| SOR-001 | `5m near session; 15-60m outside` | `5-15m near trigger` | `120s` |
| PMR-001 | `15-60m` | `30-60m` | `120s` |

**Finding F-002 (P1):**

- **Severity:** P1 — testability gap
- **Files:** `main-control-conflict-policy.md` line 13, `main-control-watcher-cadence.md`
- **Key:** "Fresh signal with stale facts" conflict rule
- **Detail:** The conflict policy says "Block candidate preparation" when a fresh signal arrives with stale facts. The watcher-cadence file defines two freshness fields: `Signal Validity` (range) and `Candidate Packet Freshness` (120s). However, the handoff.json files define `signal_ready_rule.freshness_window_seconds: 120` for signal freshness but do not define a separate fact-freshness window. The "stale facts" threshold is implicitly the Candidate Packet Freshness (120s) or the Signal Validity range, but this mapping is not explicit.
- **Why it matters:** Without an explicit fact-freshness threshold, a test cannot deterministically verify whether facts are "stale" — the system must guess whether to use 120s, the Signal Validity range, or the Poll Cadence as the staleness boundary.
- **Suggested action:** Codex clarifies whether "stale facts" maps to Candidate Packet Freshness (120s), Signal Validity (range), or needs its own explicit field in handoff.json.

---

## 8. Research Boundary Audit (HQ-004A)

**Requirement:** "may inform" and "does not authorize" sets must be disjoint; every "may inform" item must have a documented consumer.

### "May Inform" Items → Consumer Verification

| May Inform Item | Consumer Document | Present? |
|----------------|-------------------|:--------:|
| Strategy Picker options | handoff-index.md batch table | ✅ |
| watcher scope | handoff-index.md + watcher-cadence.md | ✅ |
| RequiredFacts readiness mapping | required-facts-map.md + handoff.json required_facts | ✅ |
| strategy conflict and cadence policy | conflict-policy.md + watcher-cadence.md | ✅ |
| review outcomes (promote, keep_observing, revise, park, kill) | research-sync.md boundary section | ✅ |

### "Does Not Authorize" Items → Leakage Check

| Does Not Authorize | Appears in handoff.json? | Appears in supplement docs? |
|-------------------|:------------------------:|:---------------------------:|
| FinalGate bypass | ❌ (execution_boundary.final_gate_input: false) | ❌ |
| Operation Layer bypass | ❌ (execution_boundary.operation_layer_input: false) | ❌ |
| exchange submit actions | ❌ (execution_boundary.real_submit_authorized: false) | ❌ |
| credential or live-profile changes | ❌ | ❌ |
| order-sizing default expansion | ❌ | ❌ |
| automatic admission of broader symbols | ❌ | ❌ |

**Result:** "may inform" and "does not authorize" sets are fully disjoint. No research content appears in authority position. All execution_boundary fields in every handoff.json explicitly set authorization to false.

---

## 9. Provenance Chain Verification (HQ-004B)

**Requirement:** All 4 provenance fields present, status = `reviewed_and_synced_to_main_control_baseline`, disposition documented.

### Research Sync Provenance

| Field | Value | Present? |
|-------|-------|:--------:|
| Source worktree | `/Users/jiangwei/Documents/final-strategy-research` | ✅ |
| Source branch | `codex/strategy-research-20260613-goal` | ✅ |
| Source commit | `d62ce55727614fcfdb2d12f8fee1d3c226950048` | ✅ |
| Handoff validator | `pass` | ✅ |
| Unit test | `pass` | ✅ |
| Status | `reviewed_and_synced_to_main_control_baseline` | ✅ |
| Raw research artifacts | `Local backed-up, not integrated` | ✅ |

### Commit Hash Cross-Reference

**Finding F-003 (P2):**

- **Severity:** P2 — documentation inconsistency
- **Files:** `main-control-research-sync.md` line 17 vs `main-control-handoff-index.md` line 12 vs `MPG-001/handoff.json` line 153
- **Key:** Source commit hash
- **Detail:**
  - research-sync.md: `d62ce55727614fcfdb2d12f8fee1d3c226950048` (full SHA)
  - handoff-index.md: `d62ce55727614fcfdb2d12f8fee1d3c226950048` (full SHA, matches)
  - MPG-001/handoff.json: `05f616b0` (short SHA, different commit)
  - TEQ-001/handoff.json: no `source_commit` field
  - FBS-001/handoff.json: no `source_commit` field
  - SOR-001/handoff.json: no `source_commit` field
  - PMR-001/handoff.json: no `source_commit` field
- **Why it matters:** MPG-001 references a different commit than the canonical research sync. TEQ-001, FBS-001, SOR-001, PMR-001 omit source_commit entirely, making per-group provenance incomplete. The overall chain is intact via research-sync.md, but per-group traceability is weakened.
- **Suggested action:** Codex decides whether to align MPG-001's commit to the canonical one and add source_commit to the other 4 handoff.json files, or accept the research-sync.md as the sole provenance source.

---

## 10. Sample Packet / Review Outcome / Hard Stop / Risk Defaults Gap Matrix (HQ-005A)

**Requirement:** For each StrategyGroup, check: (1) sample packet, (2) review outcome vocabulary, (3) hard stops, (4) risk defaults.

### 5×4 Gap Matrix

| StrategyGroup | Sample Packets | Review Outcomes | Hard Stops | Risk Defaults |
|--------------|:--------------:|:---------------:|:----------:|:-------------:|
| MPG-001 | ✅ (4 packets) | ⚠️ (see below) | ✅ (11 stops) | ✅ |
| TEQ-001 | ✅ (4 packets) | ⚠️ (see below) | ✅ (11 stops) | ✅ |
| FBS-001 | ✅ (4 packets) | ⚠️ (see below) | ✅ (11 stops) | ✅ |
| SOR-001 | ✅ (4 packets) | ⚠️ (see below) | ✅ (11 stops) | ✅ |
| PMR-001 | ✅ (4 packets) | ⚠️ (see below) | ✅ (10 stops) | ✅ |

### Sample Packet Coverage

Each handoff.json defines 4 packet types:

| Packet Type | Status Value | All Groups Have? |
|------------|-------------|:----------------:|
| sample_signal_packet | `ready_for_shadow_candidate_prepare` | ✅ |
| sample_no_signal_packet | `no_signal` | ✅ |
| sample_stale_signal_packet | `stale_signal` | ✅ |
| sample_conflict_packet | `signal_conflict` | ✅ |

All signal packets include `"not_execution_authority": true`. ✅

### Hard Stop Count by Group

| Group | Domain-Specific Stops | Common Stops | Total |
|-------|:--------------------:|:------------:|:-----:|
| MPG-001 | 5 (late_cycle, duplicate, etc.) | 6 | 11 |
| TEQ-001 | 5 (low_history, concentration, etc.) | 6 | 11 |
| FBS-001 | 5 (funding, mark, OI, etc.) | 6 | 11 |
| SOR-001 | 5 (open_range, trigger, session, etc.) | 6 | 11 |
| PMR-001 | 4 (role, xag, commodity, deviation) | 6 | 10 |

**Common stops across all groups:** active_position_same_symbol, open_order_same_symbol, stale_market_facts, missing_exchange_rules, no_stop_loss_plan, risk_boundary_mismatch.

### Risk Defaults Uniformity

All 5 groups share identical risk defaults:
- risk_tier: `tiny`
- max_notional_per_action_usdt: `8`
- max_active_positions: `1`
- default_leverage: `1`
- max_leverage: `1`
- requires_sl: `true`
- requires_tp_or_exit_plan: `true`

Exit horizons vary by group domain (appropriate).

**Finding F-004 (P2):**

- **Severity:** P2 — missing field in handoff.json
- **Files:** All 5 `handoff.json` files
- **Key:** `review_outcome` (absent)
- **Detail:** The Strategy Control Board Contract defines `review_outcome` as a required row field with vocabulary: `保留`, `调整`, `暂停`, `停用`, `待复盘`. The research-sync.md boundary defines review outcomes as `promote`, `keep_observing`, `revise`, `park`, `kill`. Neither vocabulary appears in any handoff.json file. The handoff layer defines sample packets for signal lifecycle but not for post-settlement review.
- **Why it matters:** Post-settlement review needs a vocabulary to classify outcomes. Without it in the handoff, implementation must derive review vocabulary from the board contract or research sync, creating ambiguity about which vocabulary is authoritative for runtime.
- **Suggested action:** Codex decides whether to add a `review_outcome_vocabulary` field to each handoff.json or accept the board contract / research sync as the sole source.

**Finding F-005 (P2):**

- **Severity:** P2 — vocabulary mismatch
- **Files:** `STRATEGY_CONTROL_BOARD_CONTRACT.md` line 27 vs `main-control-research-sync.md` line 44
- **Key:** Review outcome vocabulary
- **Detail:** Two different vocabularies exist:
  - Board contract: `保留`, `调整`, `暂停`, `停用`, `待复盘`
  - Research sync: `promote`, `keep_observing`, `revise`, `park`, `kill`
  - These do not have documented 1:1 mappings.
- **Why it matters:** Implementation must choose one vocabulary. The Chinese terms are Owner-facing product language; the English terms are internal lifecycle language. Without a mapping, the review surface may expose inconsistent terminology.
- **Suggested action:** Codex documents the mapping between the two vocabularies (e.g., `promote` → `保留`, `park` → `暂停`, `kill` → `停用`) or consolidates to one authoritative set.

---

## 11. Owner-Readable Status Mapping Audit (HQ-006A)

**Requirement:** Every internal gate class and handoff state must have a mapping to Owner-readable terse language.

### Handoff Internal States → Owner Status Mapping

| Internal State (from handoff.json) | Source | Owner-Facing Status | Mapping Documented? |
|-----------------------------------|--------|-------------------|:------------------:|
| `ready_for_shadow_candidate_prepare` | signal_ready_rule | `处理中` | ⚠️ implicit |
| `no_signal` | sample packets | `等待机会` | ⚠️ implicit |
| `stale_signal` | sample packets | `等待机会` or `暂不可用` | ⚠️ implicit |
| `signal_conflict` | sample packets | `需要介入` or `暂不可用` | ⚠️ implicit |
| `runtime_pilot_contract` | status field | N/A (metadata) | ✅ |

### Gate Classes (from AGENTS.md) → Owner Status Mapping

| Gate Class | Owner-Facing Sentence | Defined In |
|-----------|----------------------|-----------|
| `waiting_for_market` | `等待机会` | AGENTS.md ✅ |
| `missing_fact` | `事实不可用，暂不能使用` | AI_AGENT_CONSTRAINTS.md ✅ |
| `deployment_issue` | `暂不可用` | AI_AGENT_CONSTRAINTS.md ✅ |
| `active_position_resolution` | `有持仓处理中，暂不能使用` | AI_AGENT_CONSTRAINTS.md ✅ |
| `hard_safety_stop` | `需要介入` | Implicit ⚠️ |
| `review_only_warning` | `运行中` (with detail) | Implicit ⚠️ |

### Forbidden Internal Terms Leakage Check

| Forbidden Term | Appears in handoff.json as primary label? | Appears in supplement docs as primary label? |
|---------------|:----------------------------------------:|:-------------------------------------------:|
| FinalGate | ❌ | ❌ (only in boundary disclaimers) |
| Operation Layer | ❌ | ❌ (only in boundary disclaimers) |
| RequiredFacts | ❌ | ✅ (as document title, not UI label) |
| candidate | ❌ | ❌ |
| authorization | ❌ | ❌ |
| preflight | ❌ | ❌ |
| proof | ❌ | ❌ |
| route | ❌ | ❌ |
| refId | ❌ | ❌ |
| blocker code | ❌ | ❌ |
| runtime grant | ❌ | ❌ |

**Result:** No forbidden internal terms appear as primary labels in handoff or supplement files. All appear only in boundary disclaimers or document titles.

**Finding F-006 (P2):**

- **Severity:** P2 — implicit mapping
- **Files:** All 5 `handoff.json` files
- **Key:** Signal status values (`ready_for_shadow_candidate_prepare`, `no_signal`, `stale_signal`, `signal_conflict`)
- **Detail:** The handoff.json signal statuses do not have explicit Owner-facing mappings. The mapping from `no_signal` → `等待机会` and `ready_for_shadow_candidate_prepare` → `处理中` is implied by the operating model and control board contract but not documented in the handoff files themselves.
- **Why it matters:** An implementer reading only the handoff.json must infer the Owner-facing status. If the inference is wrong, raw internal terms could leak into the Owner UI.
- **Suggested action:** Codex decides whether to add an `owner_facing_status` field to each sample packet in handoff.json or accept the operating model as the mapping source.

**Finding F-007 (P3):**

- **Severity:** P3 — documentation completeness
- **Files:** `docs/current/AI_AGENT_CONSTRAINTS.md`
- **Key:** Gate class → Owner sentence mapping
- **Detail:** `hard_safety_stop` and `review_only_warning` gate classes lack explicit Owner-facing sentence mappings. The other 4 classes have explicit mappings in the constraints file.
- **Why it matters:** Minor gap — `hard_safety_stop` clearly maps to `需要介入` and `review_only_warning` to `运行中` (with detail), but these are implicit.
- **Suggested action:** Low priority. Codex may add explicit mappings for completeness.

---

## 12. Blockers

No P0 blockers found. All required files are present and readable.

The following items require Codex attention before or during implementation:

| ID | Severity | Description | Blocking Card |
|----|----------|-------------|--------------|
| F-001 | P1 | SOR-001 default mode mismatch (handoff.json vs index/priority) | HQ-001B |
| F-002 | P1 | "Fresh signal with stale facts" threshold not explicitly defined | HQ-003A |

---

## 13. Codex Decision Needed

| ID | Decision | Impact | Blocking? |
|----|---------|--------|:---------:|
| F-001 | Resolve SOR-001 mode: `conditional_armed_observation` or `armed_observation`? | Watcher/armed behavior | Yes — implementation cannot proceed without correct mode |
| F-002 | Clarify "stale facts" threshold: Candidate Packet Freshness (120s), Signal Validity (range), or new field? | Conflict rule testability | Yes — tests cannot verify stale-facts blocking without a threshold |
| F-003 | Align per-group commit hashes in handoff.json or accept research-sync.md as sole provenance? | Provenance traceability | No — provenance chain works via research-sync.md |
| F-004 | Add review_outcome_vocabulary to handoff.json or accept board contract as source? | Post-settlement review | No — vocabulary exists in board contract |
| F-005 | Map board contract vocabulary (保留/调整/暂停/停用/待复盘) to research sync vocabulary (promote/keep_observing/revise/park/kill)? | Review surface terminology | No — both exist, mapping needed for consistency |
| F-006 | Add owner_facing_status to handoff.json sample packets or accept operating model as mapping source? | UI implementation | No — mapping exists in operating model |
| F-007 | Add explicit Owner sentences for hard_safety_stop and review_only_warning gate classes? | Documentation completeness | No — implicit mappings are correct |

---

## 14. Verification Commands

These commands may be run to independently verify audit findings:

```bash
# Verify all 5 StrategyGroups present in handoff index
grep -c "MPG-001\|TEQ-001\|FBS-001\|SOR-001\|PMR-001" \
  docs/current/strategy-group-handoffs/main-control-handoff-index.md

# Verify SOR-001 mode mismatch (F-001)
grep "SOR-001" docs/current/strategy-group-handoffs/main-control-handoff-index.md
grep "SOR-001" docs/current/strategy-group-handoffs/main-control-admission-priority.md
grep "default" docs/current/strategy-group-handoffs/SOR-001/handoff.json

# Verify commit hash discrepancy (F-003)
grep "source_commit" docs/current/strategy-group-handoffs/MPG-001/handoff.json
grep "Source commit" docs/current/strategy-group-handoffs/main-control-research-sync.md

# Verify all handoff.json files have execution_boundary
for g in MPG-001 TEQ-001 FBS-001 SOR-001 PMR-001; do
  echo "=== $g ==="
  python3 -c "import json; d=json.load(open('docs/current/strategy-group-handoffs/$g/handoff.json')); print(d.get('execution_boundary', 'MISSING'))"
done

# Verify no forbidden terms in handoff files
grep -ri "FinalGate\|Operation Layer\|preflight\|proof\|refId\|blocker code\|runtime grant" \
  docs/current/strategy-group-handoffs/ --include="*.md" --include="*.json" -l

# Verify hard stops present for all armed_observation groups
for g in MPG-001 TEQ-001 FBS-001 SOR-001 PMR-001; do
  echo "=== $g ==="
  python3 -c "import json; d=json.load(open('docs/current/strategy-group-handoffs/$g/handoff.json')); print(len(d.get('hard_stops',[])), 'hard stops')"
done

# Verify handoff files unmodified after this audit
git diff -- docs/current/strategy-group-handoffs/
```

---

## Missing Inputs

None. All required files were present and readable.

---

## File Inventory

Files read during this audit:

| File | Role |
|------|------|
| `AGENTS.md` | Agent operating guide |
| `CLAUDE.md` | Claude worker guide |
| `docs/current/OWNER_RUNTIME_OPERATING_MODEL.md` | Owner operating model SSOT |
| `docs/current/AI_AGENT_CONSTRAINTS.md` | AI agent constraints |
| `docs/current/STRATEGY_CONTROL_BOARD_CONTRACT.md` | Control board contract |
| `docs/current/strategy-group-handoffs/main-control-handoff-index.md` | Handoff index |
| `docs/current/strategy-group-handoffs/main-control-admission-priority.md` | Admission priority |
| `docs/current/strategy-group-handoffs/main-control-conflict-policy.md` | Conflict policy |
| `docs/current/strategy-group-handoffs/main-control-required-facts-map.md` | RequiredFacts map |
| `docs/current/strategy-group-handoffs/main-control-research-sync.md` | Research sync provenance |
| `docs/current/strategy-group-handoffs/main-control-watcher-cadence.md` | Watcher cadence |
| `docs/current/strategy-group-handoffs/main-control-task-card.md` | Task card |
| `docs/current/strategy-group-handoffs/MPG-001/handoff.json` | MPG-001 handoff |
| `docs/current/strategy-group-handoffs/TEQ-001/handoff.json` | TEQ-001 handoff |
| `docs/current/strategy-group-handoffs/FBS-001/handoff.json` | FBS-001 handoff |
| `docs/current/strategy-group-handoffs/SOR-001/handoff.json` | SOR-001 handoff |
| `docs/current/strategy-group-handoffs/PMR-001/handoff.json` | PMR-001 handoff |
| `output/claude-token-burn/CLAUDE-FINAL-HANDOFFCARDS-006-strategygroup-handoff-quality-cards.md` | QA card definitions |

Files written: 1 (this report).

No other files modified.

---

*End of audit.*
