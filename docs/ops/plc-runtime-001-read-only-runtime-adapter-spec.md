# PLC-RUNTIME-001 Read-Only Runtime Adapter Spec

Date: 2026-05-25
Status: REVIEW

## Goal

Define the first runtime adapter for the personal leveraged campaign chain
without granting order authority. The adapter exposes inspection data for:

`FeatureSnapshot -> StrategyContract -> TradeIntent`

It is a read-only bridge from the local PLC sandbox into runtime observability.

## Non-Authority Boundary

The adapter must not:

- call `ExecutionOrchestrator`;
- call `ExchangeGateway`;
- place, cancel, amend, or size orders;
- read or mutate exchange credentials;
- alter runtime profiles or strategy parameters;
- promote any PLC output to paper/testnet/live execution.

## Inputs

- A closed/prior `FeatureSnapshot`.
- A frozen `StrategyContract`.
- A local runtime clock supplied by the caller.

All financial values remain `Decimal` or decimal strings. No `float` is allowed
in adapter contracts.

## Outputs

Return an inspection payload:

- source snapshot id and timestamp;
- strategy contract id/version;
- derived `TradeIntent` preview;
- explicit authority marker: `read_only=true`;
- rejection reasons if the snapshot is not closed/prior, contract is not
  frozen, or required fields are missing;
- no order id and no exchange id.

## First Tests

- Closed/prior snapshot plus frozen contract returns one read-only preview.
- Open/current snapshot is rejected.
- Non-frozen contract is rejected.
- Adapter output contains no exchange/order authority fields.
- Domain code remains free of I/O framework imports.

## Promotion Rule

Paper or testnet execution requires a separate ADR-0009 action request and a
new task that explicitly changes authority from read-only inspection to bounded
execution. This spec does not authorize that step.
