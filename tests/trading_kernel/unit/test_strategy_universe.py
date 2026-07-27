from __future__ import annotations

from pydantic import ValidationError
import pytest

from src.trading_kernel.domain.strategy_universe import (
    StrategyUniverseVersion,
    UniverseMember,
    UniverseMemberRole,
    registered_strategy_universes,
    universe_for_event_spec,
)


EXPECTED_CRYPTO_SYMBOLS = {
    "CPM-LONG": ("ETHUSDT", "SOLUSDT", "SUIUSDT", "BNBUSDT", "LINKUSDT", "XRPUSDT"),
    "MPG-LONG": ("OPUSDT", "SOLUSDT", "SUIUSDT", "ADAUSDT", "AAVEUSDT", "NEARUSDT"),
    "MI-LONG": ("ETHUSDT", "SOLUSDT", "DOGEUSDT", "SUIUSDT", "AAVEUSDT", "NEARUSDT"),
    "SOR-LONG": ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"),
    "SOR-SHORT": ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"),
    "BRF2-SHORT": ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LINKUSDT", "XRPUSDT"),
}

EXPECTED_US_CANDIDATES = (
    "MSTRUSDT",
    "COINUSDT",
    "CRCLUSDT",
    "HOODUSDT",
    "PLTRUSDT",
    "MUUSDT",
    "SNDKUSDT",
    "TSLAUSDT",
    "NVDAUSDT",
    "METAUSDT",
    "GOOGLUSDT",
    "AVGOUSDT",
    "SOXLUSDT",
)
EXPECTED_US_REFERENCES = ("QQQUSDT", "SPYUSDT")


def test_registered_universes_have_exact_owner_approved_membership() -> None:
    universes = {item.event_id: item for item in registered_strategy_universes()}

    assert set(universes) == {*EXPECTED_CRYPTO_SYMBOLS, "RSRVCB-LONG-15M"}
    for event_id, expected_symbols in EXPECTED_CRYPTO_SYMBOLS.items():
        universe = universes[event_id]
        assert universe.candidate_venue_symbols == expected_symbols
        assert universe.reference_venue_symbols == ()
        assert universe.asset_class == "crypto"

    us_universe = universes["RSRVCB-LONG-15M"]
    assert us_universe.candidate_venue_symbols == EXPECTED_US_CANDIDATES
    assert us_universe.reference_venue_symbols == EXPECTED_US_REFERENCES
    assert us_universe.asset_class == "us_equity"


def test_registered_universes_have_36_crypto_scopes_and_no_avax() -> None:
    universes = registered_strategy_universes()
    crypto_candidates = tuple(
        member
        for universe in universes
        if universe.asset_class == "crypto"
        for member in universe.candidate_members
    )

    assert len(crypto_candidates) == 36
    assert all(member.venue_symbol != "AVAXUSDT" for member in crypto_candidates)


def test_universe_digest_is_deterministic_and_membership_sensitive() -> None:
    universe = registered_strategy_universes()[0]
    restored = StrategyUniverseVersion.model_validate(
        universe.model_dump(mode="python")
    )

    assert restored.semantic_digest() == universe.semantic_digest()
    changed = universe.model_copy(
        update={
            "members": (
                *universe.members[:-1],
                UniverseMember(
                    exchange_instrument_id="binance-usdm:UNIUSDT:perpetual",
                    venue_symbol="UNIUSDT",
                    role=UniverseMemberRole.CANDIDATE,
                    priority_rank=len(universe.candidate_members),
                ),
            )
        }
    )
    assert changed.semantic_digest() != universe.semantic_digest()


def test_universe_rejects_duplicate_members_and_non_contiguous_candidates() -> None:
    universe = registered_strategy_universes()[0]
    payload = universe.model_dump(mode="python")
    with pytest.raises(ValidationError):
        StrategyUniverseVersion.model_validate(
            {**payload, "members": (*universe.members, universe.members[0])}
        )

    malformed = universe.members[0].model_copy(update={"priority_rank": 9})
    with pytest.raises(ValidationError):
        StrategyUniverseVersion.model_validate(
            {**payload, "members": (malformed, *universe.members[1:])}
        )


def test_universe_lookup_requires_exact_event_spec_identity() -> None:
    universe = registered_strategy_universes()[0]
    assert universe_for_event_spec(universe.event_spec_id) == universe
    with pytest.raises(KeyError, match="unknown Event Spec universe"):
        universe_for_event_spec("event_spec:unknown")
