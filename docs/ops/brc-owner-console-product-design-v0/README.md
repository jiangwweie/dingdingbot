# BRC Owner Console Product Design v0

Date: 2026-05-26
Status: APPROVE_WITH_REQUIRED_REVISIONS

## 1. Product Positioning

BRC Owner Console is the Owner-facing operating room for the Bounded Risk
Campaign System.

It is not a generic admin panel, not an exchange terminal, and not an
autonomous trading bot interface.

The console's product job is:

```text
show system truth
-> let Owner ask through LLM
-> classify intent and risk
-> produce an action card
-> require Owner confirmation
-> execute only allowed state changes in the current environment
-> preserve audit and review evidence
```

The console should make these questions answerable in plain Owner language:

1. Where is the system now?
2. What strategy/playbook is being observed, monitored, or rehearsed?
3. What is the account and risk state?
4. What can Owner do now?
5. Why is an action allowed, warned, or blocked?
6. What will happen if Owner confirms?
7. What will not happen?
8. How can Owner pause, stop, or flatten quickly?
9. What evidence exists for later review?

## 2. Fit With Current Project Planning

This design aligns with the current BRC / Owner-driven runtime-control
planning.

The console is allowed to become the main local product surface because BRC
requires Owner-readable state, confirmation, auditability, and fast cut-off
controls.

The console must not become:

- a direct LLM-to-order execution path;
- an automatic strategy pool or router;
- a live-ready trading terminal;
- a withdrawal or transfer console;
- a free-form parameter mutation screen;
- a way to bypass campaign review, risk gates, audit persistence, or Owner
  confirmation.

## 3. Target User

Primary user:

- Owner / PM / final decision maker.

Secondary user:

- Codex / engineering operator during local acceptance and diagnostics.

Non-target users for v0:

- external traders;
- public Web users;
- remote Feishu operators;
- unauthenticated users;
- strategy agents with direct execution authority.

## 4. Core Information Architecture

Recommended primary navigation:

| Page | Purpose | Current Priority |
| --- | --- | --- |
| Command Center | One-screen system, strategy, account, risk, and next-action summary | P0 |
| LLM Copilot | Natural-language input, intent recognition, risk advice, action card | P0 |
| Strategy / Playbook | Current playbook, mode, applicability, failure mode, campaign binding | P0 |
| Risk & Account | Account state, exposure/orders, flatness proof, risk decision, campaign risk envelope | P0 |
| Runtime Control | observe / monitor / testnet_rehearsal / paused / stopped / flattening / attention_required controls | P0 |
| Campaign Review | Outcome, evidence packet, review decision, next recommended task | P1 |
| Audit Trail | Operator actions, workflow runs, review decisions, safety events | P1 |
| Developer Detail | Raw readiness, runtime, repository and API details | P2 |

The first screen should be `Command Center`, not a technical dashboard.

`Positions & Orders` is not an independent P0 page. It is folded into `Risk &
Account` as `Exposure & Orders / Flatness Proof` to avoid making v0 feel like
an exchange trading terminal.

`Parameters` is not an independent v0 primary page. The v0 parameter view is a
readonly `Risk Envelope` section inside `Risk & Account`.

## 5. Command Center

Command Center is the first page after login.

It should show:

- current environment: `simulation` / `live`;
- actual exchange mode: local / mock / Binance testnet / mainnet;
- live authorization state;
- runtime state: `observe`, `monitor`, `testnet_rehearsal`, `paused`,
  `stopped`, `flattening`, `attention_required`;
- current playbook and strategy family;
- current campaign state;
- account and risk summary;
- exposure, open orders, and flatness proof;
- hard blocks and advisory warnings;
- risk decision;
- next recommended action;
- fast cut-off availability;
- latest audit event.

Design rule:

- Put safety and account truth above action buttons.
- Developer fields such as profile, GKS, and startup guard can appear only as
  explanatory detail unless they directly explain a blocked action.

Wireframe:

- [wireframes/01-command-center.svg](wireframes/01-command-center.svg)

## 6. LLM Copilot / Dialogue Flow

LLM Copilot is the main input surface.

Allowed Owner intents:

- ask current status;
- ask why blocked;
- ask market/risk advice;
- ask whether a playbook is suitable to monitor;
- prepare an action card;
- request monitor state;
- request controlled simulation/testnet rehearsal;
- request pause / stop / flatten;
- request campaign review explanation.

The LLM may:

- read controlled system facts;
- classify Owner intent;
- explain account, position, execution, strategy, market, behavior, and system
  risk;
- propose an action card;
- explain audit evidence.

The LLM may not:

- write database rows directly;
- mutate runtime state directly;
- place, cancel, close, resize, or leverage-adjust orders directly;
- confirm on behalf of Owner;
- bypass risk gates, audit persistence, `TRADING_ENV`, or confirmation.

LLM output should be visually separated into:

1. Recognized intent.
2. Facts read.
3. Risk advice.
4. Hard blocks.
5. Advisory warnings.
6. Proposed action card.
7. Required confirmation.

The confirmation control must be visually owned by an application-controlled
Action Card Execution Panel, not by the chat message itself. The LLM can
produce an action-card preview, but application preflight owns the executable
card, confirmation requirement, and execution authority.

Wireframe:

- [wireframes/02-llm-copilot.svg](wireframes/02-llm-copilot.svg)

## 7. Strategy / Playbook Page

This page explains what is being observed, monitored, or rehearsed.

It should show:

- strategy family;
- playbook id;
- current mode: research-only / observe / monitor / simulation-testnet /
  future-live-blocked;
- market behavior the playbook tries to capture;
- applicability conditions;
- disable conditions;
- known failure mode;
- current market fit summary;
- campaign risk envelope bound to this playbook;
- latest campaign outcome;
- whether strategy execution is enabled.

Current R5 carrier:

```text
StrategyFamily: Trend Following
Playbook: TF-001
Purpose: carrier validation, not alpha validation
Initial path: monitor -> simulation/testnet rehearsal
```

Do not use this page to build an automatic strategy pool in v0.

## 8. Risk & Account Page

This page is the risk desk.

It should show:

- account environment and exchange source;
- wallet/equity/margin summary when available;
- current exposure;
- current open orders;
- campaign risk bucket;
- max campaign loss;
- max attempts;
- loss-lock status;
- profit-protect status;
- daily realized PnL / trade count status;
- liquidation/margin safety status when available;
- global kill switch / pause status;
- whether new entries are allowed;
- whether flatten is available.
- exposure and orders;
- order source;
- unknown exposure flag;
- flatness proof timestamp;
- risk decision.

Risk decision vocabulary:

| Decision | Meaning |
| --- | --- |
| `ALLOW_READ` | Read-only status, evidence, and explanation are allowed. |
| `ALLOW_MONITOR` | A playbook can enter monitor mode with no order authority. |
| `BLOCK_TESTNET` | Controlled testnet rehearsal is blocked, but diagnostics may continue. |
| `ATTENTION_REQUIRED` | System cannot prove a safe state; block new state changes except stop/flatten/read-only diagnostics. |
| `BLOCK_ALL_STATE_CHANGE` | State-changing actions are blocked until the hard failure is repaired. |

Design rule:

- This is a risk explanation page, not a parameter editing page.
- Any future parameter mutation must be a separate gated workflow with
  confirmation and audit.

Wireframe:

- [wireframes/03-risk-account.svg](wireframes/03-risk-account.svg)

## 9. Runtime Control Page

Runtime control should expose a small number of high-clarity controls.

Owner-facing states:

| State | Meaning |
| --- | --- |
| observe | No trading; only observation. |
| monitor | A playbook is monitored; no order authority. |
| testnet_rehearsal | Controlled rehearsal can execute only in simulation/testnet after preflight and Owner confirmation. |
| paused | New entries are paused; existing exposure may still need management. |
| stopped | Runtime-driven activity is stopped. |
| flattening | Cancel/close flow is in progress. |
| attention_required | System cannot prove safe final state; state changes are blocked except stop, flatten, and read-only diagnostics. |

Required controls:

- enter monitor;
- allow controlled simulation/testnet rehearsal;
- pause new entries;
- emergency stop runtime;
- emergency flatten;
- future live environment boundary display.

Hard rule:

- `live` must be visible as a modeled future environment but unavailable until
  separate Owner production/deployment authorization.
- `live` must not appear as a normal switch in v0. It should appear as an
  `Environment Boundary`: current simulation, executable local/mock/testnet
  modes, future live unavailable, and reason.
- v0 must not use the bare state name `trade`; use `testnet_rehearsal` for the
  current executable path. Future live readiness may introduce `live_trade`.

Wireframe:

- [wireframes/04-runtime-control.svg](wireframes/04-runtime-control.svg)

## 10. Action Card Model

Every state-changing workflow should produce an action card before execution.

Required fields:

| Field | Meaning |
| --- | --- |
| action_card_id | Stable id for the proposed card. |
| owner_request | What Owner asked for. |
| recognized_intent | What system understood. |
| environment | `simulation` or future `live`. |
| exchange_mode | mock / testnet / mainnet. |
| action_type | read, monitor, testnet_rehearsal, pause, stop, flatten, future_live. |
| authority_source | Must be `application_preflight`, not `llm_text`. |
| fact_snapshot_id | The fact snapshot used to build the card. |
| preflight_result_id | The preflight result used to permit or block confirmation. |
| idempotency_key | Prevents duplicate confirmation or duplicate execution. |
| expiry_time | Card expiry time; stale cards cannot execute. |
| current_state | Runtime state when card was built. |
| allowed_next_states | States allowed if the card is confirmed. |
| blocked_next_states | States explicitly blocked by this card. |
| reversible | Whether the action can be reversed. |
| final_state_proof_required | Whether final flatness/order/runtime evidence must be collected. |
| will_change | What will change if confirmed. |
| will_not_change | Explicit non-effects. |
| account_impact | Whether real account can be affected. |
| hard_blocks | Blocking conditions. |
| advisory_warnings | Risk advice that does not block. |
| preflight_checks | Environment, audit, flatness, risk, permission checks. |
| confirmation_phrase | Required Owner phrase. |
| audit_destination | Where the action will be recorded. |

For v0, action cards must be generated by application code using LLM output as
advisory input, not by trusting the LLM as the source of execution truth.

## 11. Environment And Permission Boundary

Recommended product language:

| Layer | Meaning | v0 Status |
| --- | --- | --- |
| `TRADING_ENV=simulation` | local, mock, testnet, rehearsal | default |
| Binance testnet | current executable validation path | allowed after gates |
| `TRADING_ENV=live` | real account, mainnet, real funds | modeled, unauthorized, boundary display only |
| withdrawal / transfer | funds movement | out of scope |
| automatic strategy execution | agent/LLM decides and trades without Owner | out of scope |
| strategy pool execution | automatic multi-playbook routing | future |

Testnet hard gates:

1. `TRADING_ENV=simulation`.
2. The requested action proves non-production/testnet mode.
3. Audit persistence is writable.
4. Fast cut-off controls are available.
5. Preflight flatness / final-state observability exists.
6. Owner confirmation is provided.

Live hard gates:

- not available in v0;
- future separate Owner production authorization required;
- cloud/security/secret/replay/permission work required first.

## 12. R5 Full-Chain Mapping

R5 target chain:

```text
Owner text
-> LLM status/risk read
-> intent classification
-> action card
-> Owner confirmation
-> monitor or simulation/testnet workflow
-> pause / stop / flatten available
-> audit trace
-> campaign review
```

Recommended implementation sequence after this design is accepted:

1. Freeze console IA and page names.
2. Replace scattered console pages with Command Center-centered navigation.
3. Implement LLM Copilot as the primary input surface with read-only tools.
4. Add action-card model for monitor/testnet/pause/stop/flatten proposals.
5. Add runtime state vocabulary and read model.
6. Add controlled state transitions with audit hard-blocks.
7. Use `TF-001` as R5 carrier validation.

## 13. Out Of Scope For v0

- real live trading;
- mainnet order placement;
- withdrawal or transfer;
- automatic sizing;
- automatic leverage or side override;
- automatic strategy pool routing;
- production Web mutation controls;
- Feishu remote approval;
- cloud deployment;
- secret-manager migration;
- public-user RBAC;
- parameter optimization;
- strategy profitability validation.

## 14. Owner Review Decisions

The v0 review decisions are:

1. `Command Center` replaces `Summary` as the default first screen.
2. `LLM Copilot` is the only natural-language input entry.
3. Future `live` is shown as a disabled modeled boundary, not as a switch.
4. Required account/risk comfort fields are: environment, exchange mode,
   real-account impact, wallet/equity availability, available-margin
   availability, open exposure, open orders, order source, flatness proof
   timestamp, audit writable, cut-off available, loss lock, profit protect,
   daily realized PnL / trade count, and unknown exposure flag.
5. `Parameters` is removed from primary nav and folded into `Risk & Account`
   as readonly `Risk Envelope`.
6. `Markets & Orders` / `Positions & Orders` is merged into `Risk & Account`
   for v0.
7. AI risk advice is advisory-only in all simulation/testnet paths.
8. `pause_new_entries`, `emergency_stop_runtime`, and `emergency_flatten` are
   all globally visible, with increasing confirmation strength.

## 15. Required Revisions Accepted

The review verdict is `APPROVE_WITH_REQUIRED_REVISIONS`. These changes are now
part of the v0 design baseline:

1. v0 does not use bare `trade`; it uses `testnet_rehearsal` /
   simulation-scoped wording.
2. `live` is not a switch; it is a disabled future environment boundary.
3. Confirmation belongs to an application-controlled action card, not to the
   LLM chat message.
4. `Positions & Orders` is folded into `Risk & Account`.
5. Action Card includes authority, snapshot, preflight, idempotency, expiry,
   and allowed/blocked next-state fields.
6. Runtime state includes `attention_required`.
7. `Risk & Account` includes a single `Risk Decision` summary.
