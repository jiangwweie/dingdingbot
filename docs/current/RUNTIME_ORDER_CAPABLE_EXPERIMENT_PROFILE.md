# Runtime Order-Capable Experiment Profile

Last updated: 2026-06-20

## Purpose

This profile records the current Owner decision for the StrategyGroup runtime
pilot:

```text
Tokyo is an experimental bounded-capital server.
Within the selected StrategyGroup and Owner-allocated subaccount risk budget,
trading permission is not itself a risk blocker.
```

The system must therefore avoid internal read-only defaults that prevent a
fresh signal from reaching the official real-order path after all runtime
evidence is ready.

The allocated subaccount capital is loss-capable experiment capital. This
profile is not a request to reduce leverage, notional, exposure, or submit speed
for caution after the Owner has selected the official runtime profile. It is a
permission profile for fast in-boundary opportunity capture.

## Rehearsal Boundary

Order-capable permission does not mean engineering must wait for live submit to
close lifecycle branches.

Before a fresh signal appears, the system should use non-executing dry-run,
paper/simulator Operation Layer, synthetic fixtures, and post-submit lifecycle
simulation to close:

- submit accepted / rejected branches;
- timeout and retry/stop branches;
- partial-fill handling;
- protection acceptance and protection-failure handling;
- rough fee, funding, slippage, and PnL calculation;
- reconciliation, settlement, and Review Ledger shape.

These rehearsal outputs may unlock engineering readiness. They must not set
`actionable_now=true`, fabricate live RequiredFacts, bypass FinalGate or
Operation Layer, or create exchange writes.

## Required Server Overlay

The Tokyo watcher should keep the existing base credential file and load this
optional overlay after it:

```text
/home/ubuntu/brc-deploy/env/runtime-order-capable.env
```

Recommended values:

```bash
TRADING_ENV=live
EXCHANGE_TESTNET=false
BRC_EXECUTION_PERMISSION_MAX=order_allowed
RUNTIME_CONTROL_API_ENABLED=false
RUNTIME_TEST_SIGNAL_INJECTION_ENABLED=false
RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED=true
BRC_RUNTIME_ORDER_CAPABLE_EXPERIMENT=true
```

The tracked template is:

```text
.env.tokyo.experimental-live-order-capable.example
```

## What This Enables

When a fresh StrategyGroup signal appears, the system may continue through:

```text
fresh signal
-> RequiredFacts
-> candidate / authorization evidence
-> action-time FinalGate
-> official Operation Layer
-> real_gateway_action
-> post-submit finalize / reconciliation / budget settlement
```

## What This Does Not Change

This profile does not authorize:

- FinalGate bypass.
- Operation Layer bypass.
- withdrawal or transfer actions.
- secret, credential, live profile, or order-sizing mutation.
- symbol, side, notional, leverage, or selected StrategyGroup expansion.
- stale-fact execution.
- missing protection execution.
- duplicate submit risk.
- conflicting active position or open-order execution.

## Required Runtime Proof

The official Operation Layer may request real gateway action only when:

```text
exchange_submit_execution_enabled=true
exchange_submit_execution_mode=real_gateway_action
```

The runtime exchange gateway binding also requires:

```text
RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED=true
```

The credential preflight must report the environment as order-capable without
printing key or secret values.
