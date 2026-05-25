# BRC-R0/R1: Bounded Risk Campaign + Mock PnL Testnet Plan

Date: 2026-05-25
Status: ACCEPTANCE_SMOKE_PASSED

## Summary

PLC is reframed as `Bounded Risk Campaign System`.

The system allows an Owner-authorized, testnet-only campaign to use a finite
risk capital bucket and fixed ETH/BTC controlled attempts while the program
hard-blocks risk spillover, third attempts, simultaneous exposure, loss-lock
reset through playbook switching, and programmatic withdrawal.

## Core Objects

- `RiskCapitalBucket`
- `BoundedRiskCampaign`
- `PlaybookEntry`
- `PlaybookSwitchDecision`
- `RiskEnvelope`
- `CampaignAttempt`
- `MockPnlEvent`
- `CampaignOutcome`

## Initial Playbook Catalog

- `PB-000-OBSERVE-ONLY`
- `PB-001-DIRECTION-A-PAPER`
- `PB-002-SQ02-DOWNSIDE-PAPER`
- `PB-003-MANUAL-DISCRETIONARY`
- `PB-004-BRC-CONTROLLED-TESTNET`

Only `PB-004-BRC-CONTROLLED-TESTNET` is allowed to enter the controlled
testnet entry/close endpoints in this implementation.

## Runtime Boundary

- Profile: `brc_btc_eth_testnet_runtime`
- Exchange: Binance testnet only
- Program withdrawal: disabled / not implemented
- Mainnet/live: unauthorized
- LLM trading decision: unauthorized
- Automatic sizing: unauthorized

Fixed caps:

| Symbol | Amount | Max notional | Leverage |
| --- | ---: | ---: | ---: |
| `ETH/USDT:USDT` | `0.01` | `25 USDT` | `1x` |
| `BTC/USDT:USDT` | `0.002` | `250 USDT` | `1x` |

Campaign envelope:

- max attempts: `2`
- max simultaneous positions: `1`
- runtime daily trade cap in this BRC testnet profile: `20`, so prior same-day
  testnet rehearsal fills do not block the ETH/BTC acceptance flow;
- symbol sequence: ETH then BTC
- final inventory requirement: exchange and PG flat

## API Surface

All endpoints are local/internal and require:

- `RUNTIME_CONTROL_API_ENABLED=true`
- `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true` for mutation endpoints
- `EXCHANGE_TESTNET=true`
- `RUNTIME_PROFILE=brc_btc_eth_testnet_runtime`

Endpoints:

- `POST /api/runtime/test/brc/campaigns`
- `GET /api/runtime/test/brc/campaigns/current`
- `POST /api/runtime/test/brc/switch-playbook`
- `POST /api/runtime/test/brc/{eth|btc}/arm-attempt`
- `POST /api/runtime/test/brc/{eth|btc}/execute-controlled-entry`
- `POST /api/runtime/test/brc/{eth|btc}/execute-controlled-close`
- `POST /api/runtime/test/brc/mock-pnl`
- `GET /api/runtime/test/brc/evidence`
- `POST /api/runtime/test/brc/finalize`

## Acceptance Flow

1. Preflight verifies BRC profile, testnet, ETH/BTC exchange inventory flat,
   and PG active positions/orders flat.
2. Create BRC campaign with fixed bucket and risk envelope.
3. Switch from `PB-000-OBSERVE-ONLY` to
   `PB-004-BRC-CONTROLLED-TESTNET`.
4. Arm ETH attempt, execute fixed controlled entry, then runtime-managed close.
5. Inject mock `+120 USDT` PnL. BRC records `profit_protect`; no withdrawal or
   transfer is executed.
6. Arm BTC attempt under the same BRC campaign, execute fixed controlled entry,
   then runtime-managed close.
7. Inject mock loss that brings cumulative BRC PnL to `-max_campaign_loss`.
   BRC records `loss_locked`.
8. Third attempt is blocked.
9. Playbook switch while loss-locked is blocked and does not reset campaign PnL.
10. Finalize outcome:
    `ended_testnet_rehearsal_complete_loss_locked`.

## Evidence Requirements

Evidence packet must include:

- campaign id;
- risk bucket;
- risk envelope;
- playbook catalog;
- switch decision log;
- two attempts;
- mock PnL events;
- profit-protect record;
- loss-lock record;
- final inventory;
- final outcome;
- invariants showing no exchange balance mutation, no daily risk mutation, no
  program withdrawal, and no real-live authority.

## Implementation Map

- Domain: `src/domain/bounded_risk_campaign.py`
- Service: `src/application/bounded_risk_campaign_service.py`
- Repository: `src/infrastructure/pg_brc_campaign_repository.py`
- Migration: `migrations/versions/2026-05-25-012_create_brc_campaign_tables.py`
- API: `src/interfaces/api_console_runtime.py`
- Profile seed: `scripts/seed_brc_profile.py`
- Tests:
  - `tests/unit/test_brc_campaign_service.py`
  - `tests/unit/test_brc_controlled_testnet_endpoints.py`

## Acceptance Result

2026-05-25 BRC-R0/R1 Binance testnet smoke passed.

Observed result:

- runtime profile resolved as `brc_btc_eth_testnet_runtime` version `2`;
- BTC/ETH warmup completed and two order-watch tasks started;
- ETH controlled entry completed, runtime-managed close filled, and protection
  orders were terminalized/canceled;
- mock `+120 USDT` PnL triggered BRC `profit_protect`;
- BTC controlled entry completed, runtime-managed close filled, and protection
  orders were terminalized/canceled;
- mock loss brought BRC cumulative PnL to `-120 USDT` and triggered
  `loss_locked`;
- third attempt was blocked;
- loss-locked playbook switch was logged as `blocked` and campaign PnL stayed
  `-120 USDT`;
- evidence packet reported `all_flat=true`, two attempts, and two mock PnL
  events before finalize;
- final outcome:
  `ended_testnet_rehearsal_complete_loss_locked`;
- GKS was restored active, startup guard was blocked, runtime campaign state
  was closed-safe, runtime stopped, and port `8001` was released.

Noted implementation repair during smoke:

- the first BTC retry was correctly blocked by daily trade count because the
  profile still used `daily_max_trades=10` and the account-level runtime count
  was already `10`;
- BRC entry handling was repaired so blocked/failed execution intents do not
  get recorded as attempt entries;
- the BRC testnet profile daily trade cap was set to `20` for the acceptance
  profile while BRC attempt count remains hard-capped at `2`.
