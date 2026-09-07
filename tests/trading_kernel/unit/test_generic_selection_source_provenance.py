from __future__ import annotations

import pytest

from src.trading_kernel.application.project_comparative_universe import (
    ComparativeMemberWindow,
    build_comparative_universe_projection,
)
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exposure_episode import advance_exposure_episode
from src.trading_kernel.domain.strategy_registry import strategy_contract_for
from src.trading_kernel.infrastructure.generic_selection_source_provenance import (
    SourceProvenanceInsufficient,
    StaticComparisonSourceEvidence,
    certify_static_comparison_source,
)
from tests.trading_kernel.unit.detectors.fixtures import NOW_MS, mpg_long_snapshot


@pytest.mark.parametrize(
    "group,event", [("MPG-001", "MPG-LONG"), ("MI-001", "MI-LONG")]
)
@pytest.mark.parametrize(
    "status", [DetectorStatus.TRIGGERED, DetectorStatus.NOT_TRIGGERED]
)
def test_source_requires_evidence_for_existing_static_episode(
    group: str, event: str, status: DetectorStatus
) -> None:
    contract = strategy_contract_for(f"event_spec:{group}:{event}:v3")
    episode = advance_exposure_episode(
        contract=contract,
        current=None,
        detector_status=status,
        occurred_at_ms=1000 if status is DetectorStatus.TRIGGERED else None,
        observed_at_ms=1000,
        exchange_instrument_id="binance-usdm:ETHUSDT:perpetual",
    ).current
    with pytest.raises(
        SourceProvenanceInsufficient, match="SOURCE_PROVENANCE_INSUFFICIENT"
    ):
        certify_static_comparison_source(
            StaticComparisonSourceEvidence(
                episode=episode,
                current_universe_version_id="u",
                current_universe_activated_at_ms=500,
                current_member_ids=(episode.exchange_instrument_id,),
                current_universe_digest="sha256:" + "a" * 64,
                scope_universe_version_id="u",
                scope_universe_digest="sha256:" + "a" * 64,
                scope_observed_close_ms=1000,
                comparison_projection=None,
                required_fact_observed_times=(1000, 1000, 1000),
                required_fact_satisfied=(
                    status is DetectorStatus.TRIGGERED,
                    True,
                    True,
                ),
            )
        )


@pytest.mark.parametrize(
    "group,event", [("MPG-001", "MPG-LONG"), ("MI-001", "MI-LONG")]
)
@pytest.mark.parametrize(
    "status", [DetectorStatus.TRIGGERED, DetectorStatus.NOT_TRIGGERED]
)
def test_exact_current_static_source_is_preserved_without_a_rebase(
    group: str, event: str, status: DetectorStatus
) -> None:
    evidence = complete_source(group, event, status)
    proof = certify_static_comparison_source(evidence)
    assert proof.episode_domain_key == evidence.episode.episode_domain_key
    assert proof.observed_close_ms == NOW_MS
    assert proof.episode_projection_version == evidence.episode.projection_version
    assert evidence.episode.state == (
        "triggered" if status is DetectorStatus.TRIGGERED else "armed"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"scope_observed_close_ms": NOW_MS - 3600000},
        {"scope_universe_version_id": "another"},
        {"required_fact_observed_times": (NOW_MS - 3600000,) * 3},
        {"required_fact_satisfied": (False, True, True)},
        {"current_member_ids": ()},
        {"current_universe_activated_at_ms": NOW_MS},
        {"current_universe_activated_at_ms": NOW_MS+1000},
    ],
)
def test_current_membership_alone_does_not_prove_episode_origin(
    change: dict[str, object],
) -> None:
    source = complete_source("MPG-001", "MPG-LONG", DetectorStatus.TRIGGERED)
    with pytest.raises(
        SourceProvenanceInsufficient, match="SOURCE_PROVENANCE_INSUFFICIENT"
    ):
        certify_static_comparison_source(source.model_copy(update=change))


def complete_source(
    group: str, event: str, status: DetectorStatus
) -> StaticComparisonSourceEvidence:
    contract = strategy_contract_for(f"event_spec:{group}:{event}:v3")
    member = "binance-usdm:ETHUSDT:perpetual"
    episode = advance_exposure_episode(
        contract=contract,
        current=None,
        detector_status=status,
        occurred_at_ms=NOW_MS if status is DetectorStatus.TRIGGERED else None,
        observed_at_ms=NOW_MS,
        exchange_instrument_id=member,
    ).current
    projection = build_comparative_universe_projection(
        event_spec_id=contract.event_spec_id,
        universe_version_id="u",
        strategy_group_id=group,
        exchange_instrument_ids=(member,),
        closed_bar_time_ms=NOW_MS,
        lookback_bars=8 if group == "MPG-001" else 12,
        freshness_window_ms=3600000,
        member_windows=(
            ComparativeMemberWindow(
                exchange_instrument_id=member, candles_1h=mpg_long_snapshot().candles_1h
            ),
        ),
    )
    digest = canonical_digest({"event_spec_id":contract.event_spec_id,"strategy_group_id":group,"exchange_instrument_ids":(member,)})
    return StaticComparisonSourceEvidence(
        episode=episode,
        current_universe_version_id="u",
        current_universe_activated_at_ms=NOW_MS-1000,
        current_member_ids=(member,),
        current_universe_digest=digest,
        scope_universe_version_id="u",
        scope_universe_digest=digest,
        scope_observed_close_ms=NOW_MS,
        comparison_projection=projection,
        required_fact_observed_times=(NOW_MS,) * 3,
        required_fact_satisfied=(status is DetectorStatus.TRIGGERED, True, True),
    )
