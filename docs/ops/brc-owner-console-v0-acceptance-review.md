> [!NOTE]
> **HISTORICAL_EVIDENCE** — This document is a historical operational, governance, sprint, product, or live-trial artifact from an earlier project phase.
>
> It may be useful for context, auditing, or traceability, but it does **not** represent current project state, constraints, product direction, or agent instructions.
>
> Current authoritative sources:
> - `docs/canon/PROJECT_BASELINE_CURRENT.md`
> - `docs/canon/BRC_TARGET_SEMANTICS.md`
> - `docs/canon/AGENT_WORKSPACE_RULES.md`
> - `docs/canon/RUNTIME_SAFETY_BOUNDARY.md`
> - `docs/canon/TECH_DEBT_BASELINE.md`
> - `docs/canon/DOCUMENT_GOVERNANCE.md`

# BRC Owner Console v0 Acceptance Review

Date: 2026-05-26

## Verdict

`APPROVE_UI_AND_API_WITH_TESTNET_BLOCKER_RECORDED`

The v0 console docs, backend readiness contract, and frontend P0 pages are
implemented and locally verified. The Owner-authorized fixed BRC ETH/BTC
testnet rehearsal rerun reached the ETH entry step, then stopped fail-closed
because Binance testnet returned `-1007` with execution status unknown. The
workflow did not continue to close or BTC, marked the attempt blocked, restored
safe controls, verified flat inventory, and wrote review evidence.

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

## Testnet Rehearsal Rerun

Through `LLM Copilot`:

- Owner text: `帮我准备下一轮固定 ETH BTC testnet rehearsal，按 Owner 确认流程执行`;
- workflow id: `brc-wf-59ad10e73dd7`;
- detected action: `request_testnet_rehearsal`;
- confirmation phrase entered: `CONFIRM_BRC_TESTNET_REHEARSAL`;
- result: failed at ETH entry before any close/BTC branch;
- blocked reason:
  `BRC controlled entry for eth did not lock attempt: ... binance {"code":-1007,"msg":"Timeout waiting for response from backend server. Send status unknown; execution status unknown."}`;
- `withdrawal_executed=false`;
- `live_ready=false`.

This is the expected fail-closed behavior for unknown exchange execution
status. No database override was performed.

## Cleanup And Review Evidence

Latest rerun campaign:

- campaign id: `brc-9167363bf771`;
- status: `ended`;
- outcome: `ended_manual_stop`;
- playbook: `PB-004-BRC-CONTROLLED-TESTNET`;
- attempt count: `1 / 2`;
- attempt state: ETH attempt is `blocked`;
- realized/mock PnL: `0`;
- mock PnL events: none;
- current active campaign endpoint: `404` / no active BRC campaign;
- final inventory: `all_flat=true`;
- invariant checks: all passed, including `ended_campaign_has_no_active_attempt`;
- review id: `brc-review-970ba0da4197`, decision `needs_followup`,
  `real_live_authorized=false`, `withdrawal_authorized=false`,
  `strategy_execution_authorized=false`.

During this acceptance pass, earlier stale local campaigns left by old workflow
behavior were also closed only through the testnet finalize/review APIs. The
code now prevents that drift by:

- stopping the workflow immediately when `attempt_locked=false`;
- closing stale runtime gates only with flat proof;
- marking entry-not-locked attempts as `blocked` before manual-stop finalize.

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

Do not treat this as a completed ETH/BTC full-chain rehearsal. The console and
workflow boundary passed review, but the current live testnet rerun is blocked
by Binance testnet `-1007` timeout / unknown execution status at ETH entry.

Recommended next Owner decision:

```text
Review Binance testnet timeout / reconciliation handling, then rerun the fixed
ETH/BTC rehearsal.
```
