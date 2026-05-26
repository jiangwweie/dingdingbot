# ADR-0012: Bounded Risk Campaign System

Date: 2026-05-25
Status: ACCEPTED

## Context

The prior PLC roadmap was written around a future reliable personal strategy
execution platform. The current evidence state does not support that as the
active product model: there is no runtime-eligible strategy candidate, and the
Owner may still choose to run bounded, discretionary, testnet-only rehearsals
or future small risk-capital campaigns.

The real business need is not to pretend a stable alpha exists. It is to allow
finite experimentation with isolated risk capital while preventing risk
spillover, loss-counter reset through playbook switching, post-loss risk
escalation, and uncontrolled profit giveback.

## Decision

The active model is renamed to:

`Bounded Risk Campaign System`

The system is an outer campaign governance layer for:

- isolated risk capital bucket;
- Owner-selected playbook;
- bounded attempts;
- hard risk envelope;
- playbook switch decision log;
- mock or observed campaign PnL state;
- profit-protect state;
- loss-lock state;
- final campaign outcome evidence.

`Playbook` is not `Strategy`.

- A Strategy Contract is a frozen, validated, reproducible rule set that may
  eventually be consumed by runtime.
- A Playbook is a human-selected operating frame. It can be observe-only,
  paper-only, discretionary, or controlled testnet rehearsal without claiming
  stable alpha.

## Consequences

- Playbook Governance becomes a BRC sub-capability, not a separate replacement
  for campaign risk.
- Strategy Contract/runtime execution work is downgraded to a future branch
  until a governed playbook and promoted strategy justify it.
- BRC may proceed on Binance testnet after explicit Owner authorization and
  scoped verification.
- Mock PnL may be injected only as BRC business-state evidence. It must not
  alter exchange fills, actual balances, daily risk accounting, or realized
  order PnL.
- Withdrawal remains manual Owner action. The program must not implement
  transfer or withdrawal endpoints in BRC-R0/R1.

## BRC-R0/R1 Acceptance Boundary

The first implemented acceptance path is:

1. Create BRC campaign under `brc_btc_eth_testnet_runtime`.
2. Start from `PB-000-OBSERVE-ONLY`.
3. Switch to `PB-004-BRC-CONTROLLED-TESTNET`.
4. Execute controlled ETH entry and runtime-managed close.
5. Inject mock profit PnL to trigger BRC `profit_protect`.
6. Execute controlled BTC entry and runtime-managed close.
7. Inject mock loss PnL to trigger BRC `loss_locked`.
8. Prove third attempt is blocked and playbook switch does not reset PnL.
9. Finalize evidence with outcome
   `ended_testnet_rehearsal_complete_loss_locked`.

## Non-Goals

- No real live/mainnet trading.
- No program withdrawal or transfer.
- No automatic sizing.
- No LLM/agent trading decision.
- No stable-alpha claim.
- No simultaneous BTC/ETH exposure.
- No Strategy Contract promotion from this rehearsal alone.
- No LLM or workflow checkpoint state may become the audit fact source.

## Implementation Notes

- Runtime profile: `brc_btc_eth_testnet_runtime`, readonly inactive by default.
- Fixed caps: ETH `0.01` / `25 USDT`, BTC `0.002` / `250 USDT`, leverage `1x`.
- Max simultaneous positions: `1`.
- Max attempts: `2`.
- Runtime campaign state remains the single-exposure gate; BRC is the outer
  campaign envelope and does not reset after symbol changes.
- BRC-R3 may use a LangGraph-shaped workflow for Owner text classification,
  policy validation, confirmation pause/resume, and result persistence. It may
  normalize Owner text into one of the allowed BRC operator actions, but it may
  not make trading decisions, generate executable order parameters, replace
  Owner confirmation, or store secrets.
- OpenAI-compatible LLM configuration is environment-only:
  `BRC_LLM_ENABLED`, `BRC_LLM_BASE_URL`, `BRC_LLM_API_KEY`,
  `BRC_LLM_MODEL`, and `BRC_LLM_TIMEOUT_SECONDS`. Secrets must not be
  persisted in BRC tables, result packets, or logs.
