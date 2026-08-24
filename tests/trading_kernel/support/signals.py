from __future__ import annotations

from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
    build_signal_fact_digest,
)


def make_signal(
    *,
    signal_event_id: str = "signal-1",
    runtime_scope_version: int = 1,
    occurred_at_ms: int = 1_000,
    observed_at_ms: int = 1_001,
    expires_at_ms: int = 2_000,
    facts: tuple[SignalFactSnapshot, ...] | None = None,
    fact_digest: str | None = None,
    universe_version_id: str = "universe:SOR-SHORT:3",
    universe_semantic_digest: str = "sha256:" + "a" * 64,
    exposure_episode_id: str = "episode:" + "b" * 64,
    selection_authority_id: str | None = None,
) -> StrategySignal:
    selected_facts = make_signal_facts() if facts is None else facts
    return StrategySignal(
        signal_event_id=signal_event_id,
        exposure_episode_id=exposure_episode_id,
        runtime_scope_id="scope-sor-btc-short",
        runtime_scope_version=runtime_scope_version,
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v3",
        event_spec_id="event_spec:SOR-001:SOR-SHORT:v3",
        universe_version_id=universe_version_id,
        universe_semantic_digest=universe_semantic_digest,
        selection_authority_id=selection_authority_id,
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="short",
        fact_digest=fact_digest or build_signal_fact_digest(selected_facts),
        occurred_at_ms=occurred_at_ms,
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
        facts=selected_facts,
    )


def make_signal_facts() -> tuple[SignalFactSnapshot, ...]:
    return (
        SignalFactSnapshot(
            fact_definition_id="fact:breakdown_confirmed:v1",
            role="condition",
            value=True,
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=1,
        ),
        SignalFactSnapshot(
            fact_definition_id="fact:session_start_ms_v3:v3",
            role="identity_reference",
            value="1000",
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=1,
        ),
        SignalFactSnapshot(
            fact_definition_id="fact:session_end_ms_v3:v3",
            role="lifecycle_reference",
            value="86401000",
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=1,
        ),
        SignalFactSnapshot(
            fact_definition_id="fact:opening_range_high_reference_v3:v3",
            role="protection_reference",
            value="10100.0",
            satisfied=True,
            observed_at_ms=1_000,
            valid_until_ms=2_000,
            projection_version=1,
        ),
    )
