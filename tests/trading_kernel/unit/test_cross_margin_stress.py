from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.trading_kernel.domain.cross_margin_stress import (
    AccountRiskPosition,
    AccountRiskSnapshot,
    CrossMarginStressRequest,
    CrossMarginStressStatus,
    MaintenanceMarginBracket,
    StressPosition,
    evaluate_cross_margin_stress,
)


@pytest.mark.parametrize(
    ("side", "stop_price", "expected_stress", "expected_minimum"),
    [
        ("long", Decimal(90), Decimal(70), Decimal("969.30")),
        ("short", Decimal(110), Decimal(130), Decimal("968.70")),
    ],
)
def test_passes_symmetric_single_position_stop_stress(
    side: str,
    stop_price: Decimal,
    expected_stress: Decimal,
    expected_minimum: Decimal,
) -> None:
    evidence = evaluate_cross_margin_stress(
        _request(
            evaluated_side=side,
            initial_stop_price=stop_price,
            projected_instrument_positions=(
                StressPosition(
                    position_side=side,
                    quantity=Decimal(1),
                    average_entry_price=Decimal(100),
                ),
            ),
        )
    )

    assert evidence.proof.status is CrossMarginStressStatus.PASSED
    assert evidence.proof.stress_price == expected_stress
    assert evidence.proof.minimum_margin_surplus == expected_minimum
    assert evidence.proof.minimum_margin_surplus_price == expected_stress
    assert evidence.proof.evaluated_point_count == 3
    assert evidence.proof.model_id == "cross-margin-stop-stress-v1"
    assert evidence.proof.proof_digest.startswith("sha256:")


@pytest.mark.parametrize(
    ("margin_balance", "expected_minimum"),
    [
        (Decimal(15), Decimal("-15.70")),
        (Decimal("30.70"), Decimal("0.00")),
    ],
)
def test_fails_when_stress_surplus_is_negative_or_zero(
    margin_balance: Decimal,
    expected_minimum: Decimal,
) -> None:
    evidence = evaluate_cross_margin_stress(
        _request(
            account_snapshot=_snapshot(total_margin_balance=margin_balance),
        )
    )

    assert evidence.proof.status is CrossMarginStressStatus.FAILED
    assert evidence.proof.minimum_margin_surplus == expected_minimum
    assert evidence.proof.minimum_margin_surplus_price == Decimal(70)


@pytest.mark.parametrize(
    ("side", "mark_price", "stop_price"),
    [
        ("long", Decimal(89), Decimal(90)),
        ("short", Decimal(111), Decimal(110)),
    ],
)
def test_fails_when_mark_is_already_beyond_initial_stop(
    side: str,
    mark_price: Decimal,
    stop_price: Decimal,
) -> None:
    evidence = evaluate_cross_margin_stress(
        _request(
            evaluated_side=side,
            initial_stop_price=stop_price,
            account_snapshot=_snapshot(mark_price=mark_price),
            projected_instrument_positions=(
                StressPosition(
                    position_side=side,
                    quantity=Decimal(1),
                    average_entry_price=Decimal(100),
                ),
            ),
        )
    )

    assert evidence.proof.status is CrossMarginStressStatus.FAILED


def test_clamps_long_stress_boundary_to_natural_zero() -> None:
    evidence = evaluate_cross_margin_stress(
        _request(
            reference_entry_price=Decimal(10),
            initial_stop_price=Decimal(1),
            account_snapshot=_snapshot(mark_price=Decimal(10)),
            projected_instrument_positions=(
                StressPosition(
                    position_side="long",
                    quantity=Decimal(1),
                    average_entry_price=Decimal(10),
                ),
            ),
        )
    )

    assert evidence.proof.stress_price == 0
    assert evidence.proof.stress_boundary_clamped_to_zero is True


def test_evaluates_same_instrument_long_and_short_without_netting_sides() -> None:
    evidence = evaluate_cross_margin_stress(
        _request(
            projected_instrument_positions=(
                StressPosition(
                    position_side="short",
                    quantity=Decimal(2),
                    average_entry_price=Decimal(100),
                ),
                StressPosition(
                    position_side="long",
                    quantity=Decimal(1),
                    average_entry_price=Decimal(100),
                ),
            ),
        )
    )

    assert tuple(
        position.position_side
        for position in evidence.request.projected_instrument_positions
    ) == ("long", "short")
    assert evidence.proof.minimum_margin_surplus == Decimal("997.00")
    assert evidence.proof.minimum_margin_surplus_price == Decimal(100)


def test_subtracts_current_exact_instrument_values_before_projection() -> None:
    current_long = AccountRiskPosition(
        exchange_instrument_id="ETHUSDT",
        position_side="long",
        quantity=Decimal(1),
        average_entry_price=Decimal(110),
        current_unrealized_pnl=Decimal(-10),
        current_maintenance_margin=Decimal(1),
    )
    evidence = evaluate_cross_margin_stress(
        _request(
            account_snapshot=_snapshot(
                total_margin_balance=Decimal(990),
                total_maintenance_margin=Decimal(1),
                current_instrument_positions=(current_long,),
            ),
            projected_instrument_positions=(
                StressPosition(
                    position_side="long",
                    quantity=Decimal(1),
                    average_entry_price=Decimal(110),
                ),
            ),
        )
    )

    assert evidence.proof.status is CrossMarginStressStatus.PASSED
    assert evidence.proof.minimum_margin_surplus == Decimal("959.30")


def test_marks_negative_base_maintenance_as_contradictory() -> None:
    current_long = AccountRiskPosition(
        exchange_instrument_id="ETHUSDT",
        position_side="long",
        quantity=Decimal(1),
        average_entry_price=Decimal(100),
        current_unrealized_pnl=Decimal(0),
        current_maintenance_margin=Decimal(2),
    )

    evidence = evaluate_cross_margin_stress(
        _request(
            account_snapshot=_snapshot(
                total_maintenance_margin=Decimal(1),
                current_instrument_positions=(current_long,),
            )
        )
    )

    assert evidence.proof.status is CrossMarginStressStatus.FACTS_CONTRADICTORY
    assert evidence.proof.contradiction_reason == (
        "instrument maintenance margin exceeds account total"
    )
    assert evidence.proof.minimum_margin_surplus is None
    assert evidence.proof.minimum_margin_surplus_price is None
    assert evidence.proof.evaluated_point_count == 0


def test_evaluates_each_bracket_boundary_once() -> None:
    evidence = evaluate_cross_margin_stress(
        _request(
            maintenance_margin_brackets=(
                MaintenanceMarginBracket(
                    bracket_id="tier-1",
                    notional_floor=Decimal(0),
                    notional_cap=Decimal(80),
                    maintenance_margin_rate=Decimal("0.01"),
                    maintenance_amount=Decimal(0),
                ),
                MaintenanceMarginBracket(
                    bracket_id="tier-2",
                    notional_floor=Decimal(80),
                    notional_cap=None,
                    maintenance_margin_rate=Decimal("0.02"),
                    maintenance_amount=Decimal("0.8"),
                ),
            ),
        )
    )

    assert evidence.proof.status is CrossMarginStressStatus.PASSED
    assert evidence.proof.evaluated_point_count == 4
    assert evidence.proof.minimum_margin_surplus == Decimal("969.30")
    assert evidence.proof.minimum_margin_surplus_price == Decimal(70)


@pytest.mark.parametrize(
    "brackets",
    [
        (
            MaintenanceMarginBracket(
                bracket_id="tier-1",
                notional_floor=Decimal(0),
                notional_cap=Decimal(80),
                maintenance_margin_rate=Decimal("0.01"),
                maintenance_amount=Decimal(0),
            ),
            MaintenanceMarginBracket(
                bracket_id="tier-2",
                notional_floor=Decimal(81),
                notional_cap=None,
                maintenance_margin_rate=Decimal("0.02"),
                maintenance_amount=Decimal("0.8"),
            ),
        ),
        (
            MaintenanceMarginBracket(
                bracket_id="tier-2",
                notional_floor=Decimal(80),
                notional_cap=None,
                maintenance_margin_rate=Decimal("0.02"),
                maintenance_amount=Decimal("0.8"),
            ),
            MaintenanceMarginBracket(
                bracket_id="tier-1",
                notional_floor=Decimal(0),
                notional_cap=Decimal(80),
                maintenance_margin_rate=Decimal("0.01"),
                maintenance_amount=Decimal(0),
            ),
        ),
        (
            MaintenanceMarginBracket(
                bracket_id="duplicate",
                notional_floor=Decimal(0),
                notional_cap=Decimal(80),
                maintenance_margin_rate=Decimal("0.01"),
                maintenance_amount=Decimal(0),
            ),
            MaintenanceMarginBracket(
                bracket_id="duplicate",
                notional_floor=Decimal(80),
                notional_cap=None,
                maintenance_margin_rate=Decimal("0.02"),
                maintenance_amount=Decimal("0.8"),
            ),
        ),
    ],
)
def test_marks_invalid_bracket_schedule_as_contradictory(
    brackets: tuple[MaintenanceMarginBracket, ...],
) -> None:
    evidence = evaluate_cross_margin_stress(
        _request(maintenance_margin_brackets=brackets)
    )

    assert evidence.proof.status is CrossMarginStressStatus.FACTS_CONTRADICTORY
    assert evidence.proof.contradiction_reason == "maintenance bracket schedule invalid"


def test_marks_uncertified_coefficient_as_contradictory() -> None:
    evidence = evaluate_cross_margin_stress(
        _request(notional_coefficient_certified=False)
    )

    assert evidence.proof.status is CrossMarginStressStatus.FACTS_CONTRADICTORY
    assert evidence.proof.contradiction_reason == (
        "notional coefficient is not certified"
    )


def test_snapshot_and_proof_digests_are_canonical_and_value_sensitive() -> None:
    long_position = AccountRiskPosition(
        exchange_instrument_id="ETHUSDT",
        position_side="long",
        quantity=Decimal(1),
        average_entry_price=Decimal(100),
        current_unrealized_pnl=Decimal(0),
        current_maintenance_margin=Decimal(1),
    )
    short_position = AccountRiskPosition(
        exchange_instrument_id="ETHUSDT",
        position_side="short",
        quantity=Decimal(2),
        average_entry_price=Decimal(100),
        current_unrealized_pnl=Decimal(0),
        current_maintenance_margin=Decimal(2),
    )
    first = _snapshot(
        total_maintenance_margin=Decimal(3),
        current_instrument_positions=(short_position, long_position),
    )
    reordered = _snapshot(
        total_maintenance_margin=Decimal("3.0"),
        current_instrument_positions=(long_position, short_position),
    )
    changed = _snapshot(
        total_margin_balance=Decimal("1000.01"),
        total_maintenance_margin=Decimal(3),
        current_instrument_positions=(long_position, short_position),
    )

    assert first.snapshot_digest == reordered.snapshot_digest
    assert first.snapshot_digest != changed.snapshot_digest

    first_proof = evaluate_cross_margin_stress(
        _request(account_snapshot=first)
    ).proof.proof_digest
    reordered_proof = evaluate_cross_margin_stress(
        _request(account_snapshot=reordered)
    ).proof.proof_digest
    changed_proof = evaluate_cross_margin_stress(
        _request(account_snapshot=changed)
    ).proof.proof_digest

    assert first_proof == reordered_proof
    assert first_proof != changed_proof


@pytest.mark.parametrize(
    ("model", "changes", "message"),
    [
        (
            AccountRiskPosition,
            {"quantity": Decimal("NaN")},
            "finite number",
        ),
        (
            AccountRiskPosition,
            {"current_unrealized_pnl": Decimal("Infinity")},
            "finite number",
        ),
        (
            AccountRiskPosition,
            {"current_maintenance_margin": Decimal(-1)},
            "maintenance margin must be finite and nonnegative",
        ),
        (
            StressPosition,
            {"average_entry_price": Decimal("NaN")},
            "finite number",
        ),
    ],
)
def test_financial_models_reject_nonfinite_or_invalid_values(
    model: type[AccountRiskPosition | StressPosition],
    changes: dict[str, object],
    message: str,
) -> None:
    payload: dict[str, object]
    if model is AccountRiskPosition:
        payload = {
            "exchange_instrument_id": "ETHUSDT",
            "position_side": "long",
            "quantity": Decimal(1),
            "average_entry_price": Decimal(100),
            "current_unrealized_pnl": Decimal(0),
            "current_maintenance_margin": Decimal(1),
        }
    else:
        payload = {
            "position_side": "long",
            "quantity": Decimal(1),
            "average_entry_price": Decimal(100),
        }
    payload.update(changes)

    with pytest.raises(ValidationError, match=message):
        model.model_validate(payload)


def test_snapshot_rejects_duplicate_side_identity() -> None:
    position = AccountRiskPosition(
        exchange_instrument_id="ETHUSDT",
        position_side="long",
        quantity=Decimal(1),
        average_entry_price=Decimal(100),
        current_unrealized_pnl=Decimal(0),
        current_maintenance_margin=Decimal(1),
    )

    with pytest.raises(ValidationError, match="position sides must be unique"):
        _snapshot(
            total_maintenance_margin=Decimal(2),
            current_instrument_positions=(position, position),
        )


def _request(**changes: object) -> CrossMarginStressRequest:
    payload: dict[str, object] = {
        "account_snapshot": _snapshot(),
        "maintenance_margin_brackets": (
            MaintenanceMarginBracket(
                bracket_id="tier-1",
                notional_floor=Decimal(0),
                notional_cap=None,
                maintenance_margin_rate=Decimal("0.01"),
                maintenance_amount=Decimal(0),
            ),
        ),
        "maintenance_margin_brackets_digest": (
            "sha256:1111111111111111111111111111111111111111111111111111111111111111"
        ),
        "notional_coefficient": Decimal(1),
        "notional_coefficient_certified": True,
        "evaluated_side": "long",
        "reference_entry_price": Decimal(100),
        "initial_stop_price": Decimal(90),
        "post_stop_stress_multiple": Decimal(2),
        "projected_instrument_positions": (
            StressPosition(
                position_side="long",
                quantity=Decimal(1),
                average_entry_price=Decimal(100),
            ),
        ),
    }
    payload.update(changes)
    return CrossMarginStressRequest.model_validate(payload)


def _snapshot(**changes: object) -> AccountRiskSnapshot:
    payload: dict[str, object] = {
        "venue_id": "binance-usdm",
        "account_id": "subaccount-main",
        "account_risk_mode": "standard_usdm_single_asset",
        "settlement_asset": "USDT",
        "position_mode": "independent_sides",
        "margin_mode": "cross",
        "exchange_instrument_id": "ETHUSDT",
        "mark_price": Decimal(100),
        "total_margin_balance": Decimal(1000),
        "total_maintenance_margin": Decimal(0),
        "current_instrument_positions": (),
        "observed_at_ms": 1_800_000_000_000,
        "valid_until_ms": 1_800_000_005_000,
    }
    payload.update(changes)
    return AccountRiskSnapshot.create(**payload)
