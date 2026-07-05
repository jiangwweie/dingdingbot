---
title: L1_L9_SYSTEM_REVIEW_AND_OPTIMIZATION_AUDIT
status: CURRENT_REVIEW
authority: docs/current/L1_L9_SYSTEM_REVIEW_AND_OPTIMIZATION_AUDIT.md
last_verified: 2026-07-06
---

# L1-L9 System Review And Optimization Audit

## Purpose

This document is the current **L1-L9 full-chain audit** for the StrategyGroup
runtime system.

It answers four questions:

1. What is the complete trading chain from strategy governance to review.
2. Where the current system is strong.
3. Which problems or optimization opportunities remain at each layer.
4. Which repair or design work should be executed next.

This is a design and review document. It does not authorize live profile
changes, order-sizing changes, FinalGate bypass, Operation Layer bypass, or
exchange writes.

## Evidence Basis

### Known Objective Facts

| Fact | Evidence |
| --- | --- |
| Current pre-trade contract already defines PG-backed L2-L7 | `docs/current/PRE_TRADE_RUNTIME_CONTRACT.md` |
| Active StrategyGroups and side scope are Owner-confirmed | `docs/current/strategy-group-handoffs/STRATEGYGROUP_REGISTRY_CONTRACT.md` and `docs/current/L2_L7_PRETRADE_CHAIN_RESET_TEMPORARY_DRAFT.md` |
| Runtime control state DB architecture exists | `docs/current/RUNTIME_CONTROL_STATE_DB_ARCHITECTURE.md` |
| DB table design includes event specs, candidate scope, signal events, promotion, lane, ticket, safety, submit, closure, projection, monitor, and retention concepts | `docs/current/RUNTIME_CONTROL_STATE_DB_TABLE_DESIGN.md` |
| PG foundation migration exists | `migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py` |
| Ticket-bound protected submit and retention follow-up migrations exist | `migrations/versions/2026-07-05-088_create_ticket_bound_protected_submit_attempts.py`, `migrations/versions/2026-07-05-090_create_runtime_retention_runs.py` |
| Candidate Pool, Daily Table, and server monitor are PG-only entrypoints in current code | `scripts/build_strategy_live_candidate_pool.py`, `scripts/build_daily_live_enablement_table.py`, `scripts/run_tokyo_runtime_server_monitor.py` |
| Action-Time Ticket materialization exists | `scripts/materialize_action_time_ticket.py` |
| SOR code still has a semantic mismatch risk between broad side support and a short-oriented reference evaluator | `src/domain/strategy_semantics.py`, `src/domain/reference_price_action_evaluators.py`, `scripts/build_sor_session_scope_detector.py` |
| Legacy `owner_console` / `trading_console` names remain in code although frontend constraints were removed from docs/AI entrypoints | `src/application/readmodels/trading_console.py`, `src/interfaces/api_trading_console.py`, `src/infrastructure/pg_models.py` |

### Analysis Boundary

This audit does not claim the server is currently live-submit ready. It reviews
the system structure and the next optimization path. Market freshness and real
order proof remain action-time/runtime facts, not documentation conclusions.

## L1-L9 Layer Model

The project already defines **L2-L7**. This audit extends that chain with one
upstream and two downstream layers so the whole system can be reasoned about
without gaps.

| Layer | Name | Plain Chinese | Owner of Truth | Main Question |
| --- | --- | --- | --- | --- |
| **L1** | Strategy Governance | 策略治理和准入 | Strategy registry, Owner policy, PG versions | What strategy is allowed to exist and under what scope. |
| **L2** | Candidate Universe | 候选交易范围 | PG candidate scope and event bindings | Which StrategyGroup + symbol + side + event is allowed. |
| **L3** | Runtime Coverage | 服务器运行覆盖 | watcher/runtime coverage rows | Is the server actually watching that exact candidate scope. |
| **L4** | Event-Specific Facts | 事件事实快照 | PG fact snapshots and RequiredFacts | Are the side/event facts computed and fresh. |
| **L5** | Live Signal Event | 实时事件信号 | PG live signal events | Did the exact market event happen at a real event time. |
| **L6** | Promotion Candidate | 可升级候选 | PG promotion candidates / Candidate Pool | May this fresh event move toward action-time. |
| **L7** | Action-Time Lane And Ticket | 临近交易通道和正式票据 | PG lane, ticket, budget, protection refs | Which exact candidate trade is now being checked. |
| **L8** | FinalGate / Operation Layer / Protected Submit | 最终安全门和官方提交 | ticket-bound FinalGate and Operation Layer | Can this exact ticket submit through the official path. |
| **L9** | Protection / Reconciliation / Settlement / Review | 保护、对账、结算、复盘 | post-submit closure and review rows | What happened after submit and what should change next. |

## Executive Findings

### Positive System Direction

The current architecture direction is positive. The project has moved away from
artifact interpretation and toward a coherent PG-backed chain:

```text
strategy/event/scope/policy
-> watcher coverage
-> fact snapshots
-> live signal events
-> promotion candidates
-> action-time lane
-> Action-Time Ticket
-> FinalGate ticket check
-> Operation Layer ticket handoff
-> protected submit attempt
-> post-submit closure
-> review
```

The right optimization is not another packet or report. The right optimization
is to finish removing old semantic paths, strengthen event-specific constraints,
make terminology easier for the Owner to understand, and harden multi-candidate
arbitration.

### Highest-Value Concerns

| Priority | Concern | Why It Matters |
| --- | --- | --- |
| **P0** | SOR long/short semantics need event-level separation in code and tests | Broad bidirectional support without two first-class events can produce ambiguous candidates. |
| **P0** | Legacy code naming still embeds `owner_console` / `trading_console` even after frontend cleanup | Future frontend work may inherit stale mental models from backend names. |
| **P0** | Multi-candidate arbitration must be explicit enough for multiple fresh events | The system will soon face several symbols/sides satisfying facts at the same time. |
| **P0** | Action-Time Ticket explanations must be Owner-readable | The Owner repeatedly asks "which trade is this" because internal ticket terminology is not translated. |
| **P1** | Strategy semantics and RequiredFacts need one generated glossary / explanation layer | Without this, the Owner will keep asking what terms mean and agents will over-explain inconsistently. |

## Layer Review

### L1 Strategy Governance

| # | Problem Or Suggestion | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| **L1-1** | Strategy governance exists, but many users still cannot see a single "strategy meaning" summary. | Registry contract, handoff packs, tier review, temporary L2-L7 draft are separate. | Owner must mentally join several documents. | Create a strategy semantics review document with one row per active StrategyGroup: what it eats, allowed symbols, allowed side, event, invalidation, and current concern. |
| **L1-2** | Strategy handoff JSON/MD still exists as reviewed input. | `docs/current/strategy-group-handoffs/*/handoff.json`. | If code reads handoff files after PG cutover, old source authority returns. | Keep handoffs as seed/provenance only; production readers must use PG strategy/event/version rows. |
| **L1-3** | Tier labels such as `L4` are easy to misread as order permission. | Registry and tier docs state L4 is not direct order authority. | Owner or agents may confuse eligibility with live submit. | Add glossary entries and status wording that separate "eligible", "action-time", and "submit allowed". |
| **L1-4** | Strategy review state and runtime state can look similar in generated summaries. | Strategy Governance Pipeline design uses both `pipeline_state` and `contract_stage`. | Review decisions may be mistaken for runtime readiness. | Enforce dual fields: `pipeline_state` for governance and `runtime_chain_stage` for trading path. |
| **L1-5** | New strategy intake is defined, but not yet operationally tied to the active WIP limit. | `STRATEGY_GOVERNANCE_PIPELINE_DB_DESIGN.md` says pipeline is P1 after DB/source boundary. | New strategies can distract from five active StrategyGroups. | Pipeline intake should create review cases only; admission to runtime requires explicit WIP replacement or support-only status. |

### L2 Candidate Universe

| # | Problem Or Suggestion | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| **L2-1** | Candidate universe still has historical constants in scripts/docs. | `DEFAULT_CANDIDATE_UNIVERSE` is documented as a migration target; code contains default scope patterns. | Constants can re-expand scope after Owner narrows it. | Delete or rewrite constants into PG seed/import tests; runtime builders must fail if PG candidate scope is absent. |
| **L2-2** | Side support must be event-bound, not just `supported_sides`. | L2-L7 draft confirms no mechanical mirroring. | A `long/short` list alone cannot prove different events exist. | Candidate scope rows must bind to `brc_strategy_side_event_specs`, not only side strings. |
| **L2-3** | Unsupported side rejection needs negative tests across all active StrategyGroups. | DB design lists rejection cases. | Future refactors may reintroduce broad side fallback. | Keep negative tests for `CPM short`, `MPG short`, `MI short`, `BRF2 long`, and generic SOR signal. |
| **L2-4** | Candidate symbols are correct in docs, but symbol/instrument mapping needs runtime precision. | DB design includes `brc_symbols`, instruments, mappings. | A canonical symbol can map incorrectly to exchange instrument. | Final candidate scope must bind canonical symbol to exchange instrument before runtime coverage. |
| **L2-5** | Candidate scope and live-submit scope are different but easy to collapse. | Pre-Trade Runtime says candidate symbols do not mean order authorized. | Candidate list may be treated as trading authority. | Store separate fields: `candidate_scope_status`, `runtime_observation_scope`, `live_submit_allowed`, and `lane_scope`. |

### L3 Runtime Coverage

| # | Problem Or Suggestion | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| **L3-1** | Runtime coverage is now PG-backed, but coverage still needs side/event visibility. | Repository validates candidate-event bindings; watcher coverage rows are separate. | Server may watch symbol but not the intended side/event. | Require coverage rows to include `strategy_group_id`, `symbol`, `side`, `event_spec_id`, `detector_id`, and freshness. |
| **L3-2** | Oneshot systemd state can be misread as unhealthy. | Server monitor treats inactive successful watcher service as OK. | False runtime blockers create noise. | Keep monitor one-shot rules and explain them in terminology docs. |
| **L3-3** | Local monitor/caches should remain non-production. | Server monitor contract and current monitor script are server-side PG-only. | Local facts can become stale and confuse Owner. | Production status must use Tokyo server monitor and PG rows only. |
| **L3-4** | Runtime coverage history can grow quickly. | Retention job targets watcher coverage and fact snapshots. | Storage bloat and slow queries over time. | Keep retention allowlist and extend it with partition/index review before high-frequency facts expand. |
| **L3-5** | Coverage must fail closed when PG state is missing. | `PgBackedRuntimeControlStateRepository` requires tables and ownership. | Missing PG state must not silently fall back to JSON. | Keep PG-required command flags and tests that reject non-PG production DSNs. |

### L4 Event-Specific Facts

| # | Problem Or Suggestion | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| **L4-1** | RequiredFacts must be machine-evaluable, not prose. | DB design replaces `expected_condition` with operator/value. | Free text cannot safely drive promotion. | Store `operator`, `expected_value`, `value_source`, disable flags, and fact freshness in PG. |
| **L4-2** | Fact snapshots must carry event side semantics. | SOR long/short and BRF2 short require side-specific facts. | A short fact can accidentally satisfy a long candidate. | Fact snapshot rows should include `event_spec_id`, `side`, and `fact_surface`. |
| **L4-3** | MI relative strength is a hard fact in current target, but older drafts treated it as optional. | L2-L7 draft rejects `explicit_not_required_for_v0`. | MI may promote on raw impulse without relative strength. | PG seed must make `relative_strength_confirmed=true` required for `MI-LONG`. |
| **L4-4** | Account-safe facts are distinct from public pretrade facts. | Action-Time Ticket binds account-safe and account-mode snapshots. | Public facts alone could appear enough. | Candidate Pool can promote on public facts, but ticket/FinalGate must require action-time/account facts. |
| **L4-5** | Fact retention must not delete lineage used by signals/tickets. | Retention script protects fact refs from signal, promotion, lane, ticket. | Review and audit would lose proof. | Keep retention foreign-ref guards and add coverage for post-submit closure fact refs if new fact surfaces appear. |

### L5 Live Signal Event

| # | Problem Or Suggestion | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| **L5-1** | Fresh signal must be real event time, not generated time. | L2-L7 draft repeatedly rejects `generated_at`. | Artifact refresh can manufacture fake freshness. | Store `event_time_ms`, `trigger_candle_close_time_ms`, and enforce equality for current event specs. |
| **L5-2** | Signal events must reference event specs. | PG design includes `brc_strategy_side_event_specs` and `brc_live_signal_events`. | Generic signal labels cannot prove side/event identity. | Reject live signal rows without `event_spec_id`, `candidate_scope_id`, and fact refs. |
| **L5-3** | Replay events must not become live signals. | Blocker and DB docs state replay is diagnostic only. | Historical opportunities could enter live path. | Keep negative tests for replay-as-live and block rows whose source mode is not live/current detector. |
| **L5-4** | Freshness windows differ by event. | 1h events use 1h; SOR events use 15m same-session. | A stale signal can be overused. | Freshness should come from event spec, not a global constant. |
| **L5-5** | Multiple simultaneous signals need deterministic identity. | Promotion materializer selects a winner among bundles. | Duplicate signal IDs or unclear events can create duplicate lanes. | Signal ID should be deterministic from event spec + symbol + side + event time + fact snapshot. |

### L6 Promotion Candidate

| # | Problem Or Suggestion | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| **L6-1** | Promotion is non-executing but the name still sounds action-like. | Candidate Pool and promotion materializer preserve no-authority boundary. | Owner may think "promotion candidate" means order candidate. | Glossary must define promotion as "can approach action-time checks, not submit". |
| **L6-2** | Candidate Pool still contains compatibility rows and summary exports. | Builder generates JSON/MD exports. | Generated views can be mistaken as sources. | Keep `source_mode=db_backed`, `projection_target=production_current`, and explicit `legacy_file_authority=false`. |
| **L6-3** | Promotion needs clean blocker mapping for no-trade explanation. | Blocker contract requires exact first blocker. | Owner must not keep asking "is it market or engineering". | Each candidate row should expose `first_blocker`, failed facts, and `plain_language_reason`. |
| **L6-4** | Multiple promotion candidates require arbitration policy that is visible and test-covered. | Current materializer selects by WIP priority and open lane constraints. | Candidate selection can look arbitrary. | Create an arbitration policy doc/table with priority, freshness, quality, budget fit, conflict, and deterministic tie-break. |
| **L6-5** | Promotion must not bypass active position/open order conflicts. | Active position is an action-time blocker class. | Duplicate exposure risk. | Promotion may exist, but action-time lane creation must block or lose arbitration when conflict exists. |

### L7 Action-Time Lane And Ticket

| # | Problem Or Suggestion | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| **L7-1** | The Action-Time Ticket is the key missing mental model for the Owner. | User repeatedly asked why there is no "this trade" record. | Internal terms remain opaque. | Every status explanation should say: "ticket = this exact trade being checked". |
| **L7-2** | Lane and ticket must stay separate. | Pre-Trade Runtime distinguishes lane input and ticket identity. | Lane can become too loose as trade identity. | FinalGate must accept `ticket_id`, not lane/candidate JSON. |
| **L7-3** | Budget reservation circularity is partially solved but must remain explicit. | Pre-Trade contract allows reservation before ticket then backfill. | FinalGate may inspect incomplete budget lineage. | Before FinalGate, ticket must bind active budget reservation with matching scope. |
| **L7-4** | Ticket expiration/invalidation needs clear owner and transition graph. | DB design defines ticket status and events. | Expired tickets can accidentally re-enter later. | Implement legal transition tests: created -> finalgate_ready -> submitted/expired/rejected/superseded. |
| **L7-5** | Ticket fields are long and technical. | Ticket binds many refs. | Owner cannot understand what was blocked. | Add `plain_language_trade_summary` export derived from ticket fields, never used as authority. |

### L8 FinalGate / Operation Layer / Protected Submit

| # | Problem Or Suggestion | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| **L8-1** | FinalGate ticket-only rule must remain enforced in APIs. | API raises errors for ticket-bound FinalGate requiring PG DSN. | Loose parameter paths can reappear. | Review and test all FinalGate entrypoints for `ticket_id`-only production path. |
| **L8-2** | Operation Layer must consume `ticket_id + finalgate_pass_id`. | Pre-Trade Runtime defines this boundary. | Operation Layer can otherwise choose trade details. | Protected submit command must persist lineage and reject loose strategy/symbol/side. |
| **L8-3** | Legacy API names still say trading console. | `src/interfaces/api_trading_console.py` remains. | Naming may pull new frontend toward old mental model. | Plan backend route/name cleanup after runtime compatibility audit, not during trading safety changes. |
| **L8-4** | Decimal normalization and exchange filters are execution-critical. | Engineering constraints require Decimal. | Rounding or filter errors can block or distort small trades. | Operation submit command should persist raw and normalized quantity/price plus filter checks. |
| **L8-5** | Protection must be submitted or verified as part of protected submit, not afterthought. | DB design has `protection_ref_id` and submit/closure tables. | Entry without protection is not a complete success. | Operation Layer should create or verify protective order lineage before marking attempt complete. |

### L9 Protection / Reconciliation / Settlement / Review

| # | Problem Or Suggestion | Evidence | Impact | Recommendation |
| --- | --- | --- | --- | --- |
| **L9-1** | Real post-submit closure is not fully proven until real order exists. | Goal audit says real post-submit close/reconcile/settle is market/order-dependent. | Simulation proof is not live outcome proof. | Keep simulator, but mark real closure proof as pending until first accepted order. |
| **L9-2** | Review must update strategy governance, not current submit authority. | Registry contract and DB design separate review from policy. | Review could accidentally expand runtime scope. | Review outcomes may recommend policy requests; only policy events change future scope. |
| **L9-3** | Active position and historical exchange state need reconciliation logic. | Prior user noted old PG order/position mismatch. | Phantom active positions can block valid trades. | Reconciliation should compare PG orders/positions to exchange state and resolve stale local records through official recovery. |
| **L9-4** | Retention must preserve all ticket/order/review lineage. | Retention script deletes only allowlisted runtime noise. | Over-cleaning would destroy audit. | Retention must never delete signal, promotion, lane, ticket, submit, notification, policy, scope, or review rows. |
| **L9-5** | Strategy learning loop needs structured outcome fields. | DB design includes strategy review outcome fields. | Without structured learning, future strategy changes become subjective. | Review rows must store stage reached, first blocker, market-after-event, execution outcome, learning, and governance recommendation. |

## Cross-Layer Summary

### What Is Already Strong

| Area | Positive Finding |
| --- | --- |
| **PG direction** | The current architecture is converging on DB-backed runtime truth instead of JSON/MD interpretation. |
| **Ticket path** | Action-Time Ticket and ticket-bound submit concepts are now present in design and code. |
| **No forced mirroring** | Active StrategyGroup side scope is documented and mostly reflected in current code. |
| **Server monitor** | Production monitor is moving to Tokyo server-side PG-backed quiet/notify. |
| **Retention** | Fact/coverage/monitor cleanup is scoped and avoids deleting signal/ticket/order lineage. |

### Main Risks

| Risk | Layer | Fix Direction |
| --- | --- | --- |
| SOR long/short is conceptually accepted but code is still short-oriented in one reference path | L1-L5 | Build separate SOR-LONG and SOR-SHORT event specs/evaluators/tests. |
| Legacy backend names can infect new frontend/product direction | L8 | Schedule route/readmodel naming cleanup after compatibility inventory. |
| Multi-candidate arbitration is not yet a first-class policy object | L6-L7 | Add explicit PG arbitration policy and tests. |
| Owner-readable explanations are inconsistent | L1-L9 | Add terminology glossary and require `plain_language_reason` / `plain_language_stage`. |
| Real post-submit closure remains unproven by live order | L9 | Keep as pending live proof; do not overstate readiness. |

## Recommended Optimization Direction

The recommended direction is positive and should be pursued:

```text
finish PG-backed event-driven chain
-> delete or rewrite legacy semantic sources
-> add owner-readable terminology/explanation layer
-> harden strategy-specific event specs
-> add deterministic multi-candidate arbitration
-> keep one real-submit ticket path through FinalGate and Operation Layer
```

Do not add a new packet layer. Do not reintroduce local JSON fallback. Do not
solve Owner understanding by showing more raw artifacts. The product-quality
answer is a terminology and explanation projection on top of PG truth.

## Chain Position

```text
chain_position: l1_l9_system_optimization_review
strategy_group_id: active WIP StrategyGroups
symbol: active candidate universe
stage: architecture_review
first_blocker: remaining semantic and explanation gaps are not yet fully converted into executable task batches
evidence: current docs/code files listed in Evidence Basis
next_action: execute the design and execution documents created from this audit
stop_condition: each P0 issue has an implementation task with allowed files, tests, and fail-closed acceptance
owner_action_required: no
authority_boundary: review only; no FinalGate, Operation Layer, exchange write, profile mutation, or sizing mutation
```
