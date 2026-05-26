# BRC Owner Console v0 Acceptance Review

Date: 2026-05-26

## Verdict

`APPROVE_UI_AND_API_WITH_TESTNET_RERUN_BLOCKED`

The v0 console docs, backend readiness contract, and frontend P0 pages are
implemented and locally verified. A new fixed BRC ETH/BTC testnet rehearsal was
not executed in this acceptance pass because the campaign gate correctly
blocked the confirmation: an active BRC campaign already exists.

## Implemented Scope

- P0 pages: `Command Center`, `LLM Copilot`, `Strategy / Playbook`,
  `Risk & Account`, `Runtime Control`.
- Old primary entries are no longer primary UI:
  `/summary` redirects to `/command-center`;
  `/markets-orders` and `/parameters` redirect to `/risk-account`.
- `/api/brc/readiness` is the v0 console SSOT for environment boundary,
  runtime state, risk decision, risk/account summary, strategy/playbook
  summary, application-owned action cards, cut-off controls, and latest audit.
- `live` is shown as unavailable boundary, not a switch.
- v0 runtime states exclude bare `trade`.
- LLM is advisory; confirm belongs to the application Action Card panel.
- Frontend copy was simplified for Owner use, with technical IDs folded under
  expandable technical data.

## Verification

- `xmllint --noout docs/ops/brc-owner-console-product-design-v0/wireframes/*.svg`
- `python3 -m py_compile src/interfaces/api_brc_console.py`
- `pytest -q tests/unit/test_brc_console_api_surface.py`
- `pytest -q tests/unit/test_brc_operator_workflow.py`
- `pytest -q tests/unit/test_brc_controlled_testnet_endpoints.py`
- `pytest -q tests/unit/test_brc_console_api_surface.py tests/unit/test_brc_operator_workflow.py tests/unit/test_brc_controlled_testnet_endpoints.py`
- `npm run lint`
- `npm run build`
- Browser smoke on local console:
  `/command-center`, `/llm-copilot`, `/strategy-playbook`,
  `/risk-account`, `/runtime-control`.

## Local Testnet Startup

Started local console with:

```bash
BRC_BACKEND_PORT=8011 BRC_FRONTEND_PORT=3011 scripts/start_brc_local_testnet.sh
```

Observed:

- profile: `brc_btc_eth_testnet_runtime`;
- `EXCHANGE_TESTNET=true`;
- backend ready on `127.0.0.1:8011`;
- frontend ready on `127.0.0.1:3011`;
- runtime reported `SYSTEM READY`;
- GKS restored active and Startup Guard remained protective after startup.

## Testnet Rehearsal Attempt

Through `LLM Copilot`:

- Owner text: `帮我准备下一轮 testnet 演练`;
- workflow id: `brc-wf-5b07c9a504a8`;
- detected action: `request_testnet_rehearsal`;
- confirmation phrase entered: `CONFIRM_BRC_TESTNET_REHEARSAL`;
- result: blocked/failed by campaign gate;
- blocked reason:
  `active BRC campaign already exists: brc-267d6efee3b0`;
- `mutation_executed=false`;
- `withdrawal_executed=false`;
- `live_ready=false`.

This is the expected fail-closed behavior. No reset, force-finalize, or
database override was performed.

## Current Campaign Blocker

Current active campaign:

- campaign id: `brc-267d6efee3b0`;
- status: `active`;
- playbook: `PB-004-BRC-CONTROLLED-TESTNET`;
- attempt count: `1 / 2`;
- attempt state: ETH attempt is `armed`;
- realized/mock PnL: `0`;
- mock PnL events: none;
- local active orders: `0`;
- local active positions: `0`;
- local flat proof: `all_flat=true`;
- latest review: `brc-review-989fa242bf9b`, decision `accepted`,
  `real_live_authorized=false`, `withdrawal_authorized=false`,
  `strategy_execution_authorized=false`.

Because the active campaign is not ended, a fresh fixed rehearsal cannot create
a new BRC campaign.

## Prior Full-Chain Evidence Available

A previous completed fixed BRC ETH/BTC rehearsal remains available as evidence:

- workflow id: `brc-wf-8e3155486b24`;
- campaign id: `brc-4e83f98ccb4a`;
- status: `completed`;
- ETH attempt: entry and close completed;
- BTC attempt: entry and close completed;
- mock PnL: profit branch and loss-lock branch completed;
- outcome: `ended_testnet_rehearsal_complete_loss_locked`;
- review id: `brc-review-dff0efa77cf0`;
- `mutation_executed=true` for testnet only;
- `withdrawal_executed=false`;
- `live_ready=false`.

## Review Decision

Do not rerun the testnet rehearsal until the active campaign
`brc-267d6efee3b0` is intentionally closed or otherwise resolved through an
Owner-approved campaign cleanup task.

Recommended next Owner decision:

```text
Resolve active campaign brc-267d6efee3b0 before BRC Owner Console v0 final
testnet rerun.
```

