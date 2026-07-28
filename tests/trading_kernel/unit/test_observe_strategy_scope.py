from __future__ import annotations

from hashlib import sha256

import pytest

from src.trading_kernel.application import observe_strategy_scope as observation
from src.trading_kernel.application.ports import RuntimeScopeSnapshot
from src.trading_kernel.domain.signal import SignalFactSnapshot

NOW_MS = 1_800_000_000_000
UNIVERSE_DIGEST = f"sha256:{sha256(b'universe-a').hexdigest()}"
OTHER_UNIVERSE_DIGEST = f"sha256:{sha256(b'universe-b').hexdigest()}"
FACT_IDS = (
    "fact:breakout_confirmed:v1",
    "fact:opening_range_defined:v1",
    "fact:opening_range_low_reference:v1",
)


def test_warm_readiness_digest_is_bound_to_universe_version_and_digest() -> None:
    assert hasattr(observation, "build_warm_readiness")
    build_warm_readiness = observation.build_warm_readiness
    facts = _facts()

    first = build_warm_readiness(
        scope=_scope(),
        facts=facts,
        expected_fact_definition_ids=FACT_IDS,
        ready_at_ms=NOW_MS,
    )
    changed_version = build_warm_readiness(
        scope=_scope(universe_version_id="universe-version-b"),
        facts=facts,
        expected_fact_definition_ids=FACT_IDS,
        ready_at_ms=NOW_MS,
    )
    changed_digest = build_warm_readiness(
        scope=_scope(universe_semantic_digest=OTHER_UNIVERSE_DIGEST),
        facts=facts,
        expected_fact_definition_ids=FACT_IDS,
        ready_at_ms=NOW_MS,
    )

    assert first.runtime_scope_id == "scope-warming-btc"
    assert first.universe_version_id == "universe-version-a"
    assert first.universe_semantic_digest == UNIVERSE_DIGEST
    assert first.ready_at_ms == NOW_MS
    assert first.valid_until_ms == NOW_MS + 900_000
    assert first.readiness_digest.startswith("sha256:")
    assert len(first.readiness_digest) == 71
    assert changed_version.readiness_digest != first.readiness_digest
    assert changed_digest.readiness_digest != first.readiness_digest


@pytest.mark.parametrize(
    "facts",
    [
        pytest.param(
            lambda: _facts()[:-1],
            id="missing-required-fact",
        ),
        pytest.param(
            lambda: (
                *_facts(),
                _facts()[0],
            ),
            id="duplicate-fact",
        ),
        pytest.param(
            lambda: (
                _facts()[0].model_copy(
                    update={
                        "observed_at_ms": NOW_MS - 900_000,
                        "valid_until_ms": NOW_MS,
                    }
                ),
                *_facts()[1:],
            ),
            id="stale-fact",
        ),
        pytest.param(
            lambda: (
                _facts()[0].model_copy(
                    update={
                        "observed_at_ms": NOW_MS + 1,
                        "valid_until_ms": NOW_MS + 900_001,
                    }
                ),
                *_facts()[1:],
            ),
            id="future-fact",
        ),
    ],
)
def test_warm_readiness_rejects_incomplete_stale_or_inconsistent_facts(
    facts,
) -> None:
    assert hasattr(observation, "build_warm_readiness")
    build_warm_readiness = observation.build_warm_readiness
    with pytest.raises(ValueError):
        build_warm_readiness(
            scope=_scope(),
            facts=facts(),
            expected_fact_definition_ids=FACT_IDS,
            ready_at_ms=NOW_MS,
        )


def _scope(
    *,
    universe_version_id: str = "universe-version-a",
    universe_semantic_digest: str = UNIVERSE_DIGEST,
) -> RuntimeScopeSnapshot:
    return RuntimeScopeSnapshot(
        runtime_scope_id="scope-warming-btc",
        strategy_group_id="SOR-001",
        strategy_version_id="sgv:SOR-001:v2",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        runtime_profile_id="profile-test",
        owner_policy_id="policy-test",
        exchange_instrument_id="binance-usdm:BTCUSDT:perpetual",
        position_side="long",
        universe_version_id=universe_version_id,
        universe_semantic_digest=universe_semantic_digest,
        lifecycle_state="warming",
        observation_enabled=True,
        entry_enabled=False,
        scope_version=1,
    )


def _facts() -> tuple[SignalFactSnapshot, ...]:
    return (
        SignalFactSnapshot(
            fact_definition_id="fact:opening_range_defined:v1",
            role="condition",
            value=True,
            satisfied=True,
            observed_at_ms=NOW_MS,
            valid_until_ms=NOW_MS + 900_000,
            projection_version=1,
        ),
        SignalFactSnapshot(
            fact_definition_id="fact:breakout_confirmed:v1",
            role="condition",
            value=True,
            satisfied=True,
            observed_at_ms=NOW_MS,
            valid_until_ms=NOW_MS + 900_000,
            projection_version=1,
        ),
        SignalFactSnapshot(
            fact_definition_id="fact:opening_range_low_reference:v1",
            role="protection_reference",
            value="98",
            satisfied=True,
            observed_at_ms=NOW_MS,
            valid_until_ms=NOW_MS + 900_000,
            projection_version=1,
        ),
    )
