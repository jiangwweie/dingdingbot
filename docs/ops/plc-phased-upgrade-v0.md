# PLC Phased Upgrade v0

Date: 2026-05-25
Status: Phase 1 implemented for review

## Boundary

PLC promotion remains staged. This document does not authorize real live
trading, mainnet order placement, runtime profile changes, or credential
changes.

## Phase 0 - Local Sandbox

Status: REVIEW

Scope:

- Local deterministic objects and sandbox trace only.
- `ModeAdvice -> HumanArmDecision -> StrategyContract -> FeatureSnapshot ->
  TradeIntent -> RiskOrderPlan -> ExecutionReceipt -> PositionLifecycleState ->
  CampaignState`.
- Disabled by default.

Evidence:

- `src/domain/personal_campaign.py`
- `src/application/personal_campaign_sandbox.py`
- `tests/unit/test_personal_campaign_sandbox.py`

## Phase 1 - Read-Only Runtime Adapter

Status: REVIEW

Scope:

- Add a pure adapter from `FeatureSnapshot + StrategyContract` to a read-only
  `TradeIntent` preview.
- Require frozen contract semantics and closed/prior feature timestamps.
- Return explicit `read_only_no_order_authority`.
- No execution, exchange, order, account, repository, config, or profile
  authority.

Implemented artifacts:

- `src/application/personal_campaign_runtime_adapter.py`
- `ReadOnlyRuntimeAdapterPreview`
- `docs/schemas/personal_campaign/read_only_runtime_adapter_preview.schema.json`
- `docs/schemas/personal_campaign/examples/read_only_runtime_adapter_preview_sq02.example.json`
- `tests/unit/test_personal_campaign_runtime_adapter.py`

Acceptance:

- Closed/prior snapshot plus frozen contract returns one read-only preview.
- Future/current snapshot is rejected.
- Non-frozen contract is rejected.
- Adapter output contains no order id or exchange order id.
- Domain and adapter code do not import I/O frameworks.

## Phase 2 - Paper Observation Packet

Status: TODO

Scope:

- Persist or export read-only previews as observation packets.
- Add review status and operator notes.
- No paper orders, no exchange mutations, and no account authority.

Entry requirements:

- Phase 1 review accepted.
- Observation packet schema defined.
- Redaction/secret-free structured logs ready.

## Phase 3 - Testnet Rehearsal Design

Status: TODO

Scope:

- Define a bounded testnet rehearsal for PLC intent-to-plan validation.
- Must pass through ADR-0009 scoped action review.
- Must remain separate from real live/mainnet.

Entry requirements:

- Runtime-managed close smoke implemented.
- Campaign risk state machine specified.
- Account risk/liquidation safety checks at least designed.

## Phase 4 - Tiny-Live-Style Review

Status: BLOCKED

Scope:

- Review only. No real funds activation from this document.

Entry requirements:

- Phase 3 evidence accepted.
- Owner explicitly requests a separate real-live readiness review.
- Real live authorization remains separate and explicit.
