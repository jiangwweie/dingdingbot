# BRC Testnet-First / Production-Blocked Operating Principle

Date: 2026-05-26
Status: ACCEPTED_BY_OWNER

## Purpose

This note aligns the Bounded Risk Campaign System operating posture after the
Owner clarified that the current system should not remain paper-only or be
blocked by production-grade approval friction during local testnet acceptance.

The active product direction is:

```text
testnet-first for local BRC validation;
production-blocked by explicit environment gates.
```

## Decision

BRC development and local Owner acceptance should default to the controlled
Binance testnet path, not to paper-only operation.

The system should allow the fixed BRC testnet rehearsal and future monitor-only
runtime-state workflows to proceed when the environment clearly says they are
non-production:

- `EXCHANGE_TESTNET=true`;
- `RUNTIME_PROFILE=brc_btc_eth_testnet_runtime`;
- `RUNTIME_CONTROL_API_ENABLED=true`;
- `RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=true` when running the controlled BRC
  rehearsal;
- final exchange and local inventory flatness checks pass.

The strict default block belongs at the production boundary:

- real live/mainnet order placement;
- withdrawal or transfer;
- automatic sizing/leverage/side override;
- autonomous strategy execution;
- strategy-pool execution;
- broader multi-symbol expansion beyond the fixed BRC rehearsal path.

## Environment Gate Model

Local/testnet defaults:

```text
BRC_EXECUTION_MODE=testnet
EXCHANGE_TESTNET=true
RUNTIME_PROFILE=brc_btc_eth_testnet_runtime
BRC_ALLOW_PRODUCTION=false
LIVE_TRADING_ENABLED=false
MAINNET_ORDER_ENABLED=false
WITHDRAWAL_ENABLED=false
AUTO_STRATEGY_EXECUTION_ENABLED=false
```

The exact variable names may evolve during implementation, but the semantics
must remain stable:

1. Testnet should be easy to enter for local acceptance.
2. Production/live must be impossible unless the Owner explicitly enables the
   production gates in a separate deployment task.
3. Withdrawal/transfer must remain separately gated from live trading.
4. LLM or natural-language input must never bypass the environment gates or
   Owner confirmation.

## Capability Levels

| Level | Default posture | Meaning |
| --- | --- | --- |
| `read_only` | Allowed | Status, evidence, review, ledger, safety summaries. |
| `testnet` | Allowed for local BRC acceptance | Fixed BRC controlled rehearsal under profile/caps/flatness checks. |
| `monitor_only` | Allowed after implementation | Runtime may observe a selected playbook/strategy profile without order authority. |
| `paper` | Optional | Useful for simulation, but not a required precondition for BRC testnet acceptance. |
| `production_live` | Blocked | Requires separate Owner production authorization and deployment/security gates. |
| `withdrawal_transfer` | Blocked | Requires separate explicit design and authorization; not bundled with live trading. |

## Product Implication

The Owner console should not present testnet as a suspicious or unavailable
path when local acceptance defaults are configured. It should instead say:

```text
Current mode: Testnet.
You can run the fixed BRC testnet rehearsal when profile, caps, and flatness
checks pass.
You cannot run production/live, withdrawal, transfer, autonomous strategy
execution, or automatic sizing because production gates are disabled.
```

Readiness and workflow UI should answer:

- whether the system is in testnet or production mode;
- whether the fixed BRC testnet path is available;
- which exact gate blocks it if unavailable;
- what state will change after Owner confirmation;
- which production actions remain impossible.

## Non-Goals

This principle does not authorize:

- real live/mainnet trading;
- production deployment;
- withdrawal or transfer endpoints;
- autonomous strategy execution;
- automatic sizing/leverage/side decisions;
- strategy-pool execution;
- arbitrary testnet orders outside the fixed BRC workflow.

## Follow-Up

The next backend/UI cleanup should align readiness and workflow gates with this
principle:

```text
testnet path: prove non-production + fixed profile/caps + flatness;
production path: fail closed unless explicit production gates are enabled.
```
