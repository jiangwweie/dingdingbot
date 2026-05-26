# BRC Pre-Deploy Audit Backlog

Date: 2026-05-26
Status: ACTIVE_BACKLOG

This backlog records external audit findings and architecture gaps that are
not required for the current local BRC operation-governance loop, but must be
closed before Feishu callback integration, cloud deployment, public Web
control, or any future strategy-pool execution path.

The current boundary remains:

- testnet-only for controlled BRC rehearsal;
- no real live/mainnet;
- no transfer or withdrawal endpoint;
- no autonomous strategy execution;
- no automatic sizing/leverage/side decision;
- no broader multi-symbol runtime expansion.

## Already Fixed From External Audit

| Item | Status | Evidence |
| --- | --- | --- |
| `CRITICAL-1` Campaign transition owner-review / flat-proof flags were metadata-only | FIXED | `bc7e2ad fix(brc): enforce audit safety gates` now enforces `requires_owner_review` and `requires_flat_proof`. |
| `CRITICAL-2` GKS constructor initially allowed entries before initialize | FIXED | `bc7e2ad` makes constructor default fail-closed with `GKS_NOT_INITIALIZED`. |
| `HIGH-3` LLM could upgrade generic text to testnet rehearsal intent | FIXED | `bc7e2ad` requires Owner source text to explicitly mention testnet/rehearsal semantics. |
| `MEDIUM-1` mock PnL could be injected into ended campaign depending on repo behavior | FIXED | `bc7e2ad` rejects ended BRC campaign mock PnL. |
| `MEDIUM-2` testnet rehearsal executor result had no schema validation | FIXED | `bc7e2ad` validates fixed rehearsal result before persisting workflow `result_json`. |
| `MEDIUM-3` next-campaign eligibility was advisory only | FIXED | `bc7e2ad` gates new campaign creation after loss-locked ended campaign on Owner review. |
| `MEDIUM-4` implicit trigger inference could map manual close/profit/loss states to runtime triggers | FIXED | `bc7e2ad` requires explicit trigger for `closed`, `profit_protect`, and `loss_locked`. |

## Deferred Before Feishu / Cloud / Web Deployment

| ID | Severity | Required Before | Status | Required Closure |
| --- | --- | --- | --- | --- |
| `BRC-AUDIT-HIGH-1` | HIGH | Any cloud deployment or shared repo handoff | DEFERRED | Rotate testnet exchange keys and Feishu webhook if exposed outside local private machine. Confirm `.env` / `.env.local` remain ignored and untracked. Move cloud secrets to environment/secret manager, not repo files. |
| `BRC-AUDIT-HIGH-2` | HIGH | Feishu cards, Web callbacks, cloud API mutation endpoints | DEFERRED | Add request signing/timestamp window, nonce or idempotency key, and replay protection. Bind confirmation to `workflow_run_id` and reject duplicate callback execution. |
| `BRC-AUDIT-MEDIUM-5` | MEDIUM | Cloud-exposed runtime control or Web control | DEFERRED | Replace localhost-only trust with authenticated operator sessions, CSRF/callback protection, role-scoped permissions, and explicit audit logging for mutations. |
| `BRC-AUDIT-MEDIUM-6` | MEDIUM | Cloud deployment | DEFERRED | Add deployment preflight: effective profile, `EXCHANGE_TESTNET`, runtime-control env, DB migration head, GKS active, startup guard blocked, final inventory flat, open order zero. |
| `BRC-AUDIT-MEDIUM-7` | MEDIUM | Public/internal Web console | DEFERRED | Add web control permission boundary: read-only pages by default, mutation controls hidden/disabled unless runtime gates pass, confirmation phrase never auto-filled. |
| `BRC-AUDIT-MEDIUM-8` | MEDIUM | Long-running server process | DEFERRED | Add server runbook for process supervision, graceful shutdown, port release, startup reconciliation, and fail-closed startup if dependencies are missing. |

## Deferred Strategy Pool Track

Strategy pool work is intentionally separate from the BRC operator gateway.
BRC may govern a playbook or campaign without claiming a strategy is valid.

| ID | Required Before | Status | Required Closure |
| --- | --- | --- | --- |
| `STRAT-POOL-001` Strategy pool domain model | Any strategy catalog UI/API | DEFERRED | Define `StrategyPoolEntry`, evidence status, applicability boundary status, allowed environments, owner review state, and no-order authority flags. |
| `STRAT-POOL-002` Research-to-pool promotion gate | Any paper/testnet strategy candidate | DEFERRED | Convert research artifacts into strategy-pool entries only through Owner-reviewed evidence gates. No direct research-to-runtime path. |
| `STRAT-POOL-003` Strategy Contract bridge | Any runtime strategy execution | DEFERRED | A strategy-pool entry may reference a Strategy Contract only after a separate promotion decision. BRC and LLM workflows must not create executable strategy contracts. |
| `STRAT-POOL-004` Pool-to-playbook relation | Playbook catalog expansion | DEFERRED | A playbook may cite one or more strategy-pool entries as evidence, but switching playbooks must not reset campaign PnL, cooldown, loss-lock, or risk envelope. |

## Current High-Priority Capability Recommendation

The next high-priority local capability is:

`BRC-R4-001 Local Operator Console`

Goal:

`Owner text -> LLM/operator plan -> visible confirmation gate -> action/result ledger -> review decision -> next-campaign gate`

Why this is next:

- The current backend capability exists, but the operation medium is still too
  CLI/API-oriented for day-to-day Owner use.
- A local Web console can reduce friction without adding new trading authority.
- It directly reuses existing BRC APIs, ledgers, and workflow gates.
- It prepares the UI/control model needed later for Feishu cards and cloud
  deployment, while keeping those deployment risks deferred.

Strict scope:

- local-only web surface;
- read-heavy by default;
- no new order path;
- no withdrawal/transfer;
- no real live/mainnet;
- no strategy execution;
- no auto-filled confirmation phrase;
- testnet rehearsal only through the existing fixed BRC workflow and Owner
  confirmation.

