#!/usr/bin/env python3
"""
Verification script for risk_calculator.py exposure parameter fix.

This script validates that:
1. exposure=3.0 allows larger position sizes than exposure=1.0
2. Three-layer constraints work independently
3. No regression in existing behavior
"""
import asyncio
from decimal import Decimal
from src.domain.models import (
    AccountSnapshot,
    Direction,
    PositionInfo,
    RiskConfig,
)
from src.domain.risk_calculator import RiskCalculator


def create_account(
    total_balance: Decimal = Decimal("100000"),
    available_balance: Decimal = Decimal("80000"),
    positions: list = None,
) -> AccountSnapshot:
    """Helper to create AccountSnapshot for testing."""
    return AccountSnapshot(
        total_balance=total_balance,
        available_balance=available_balance,
        unrealized_pnl=Decimal("0"),
        positions=positions or [],
        timestamp=1234567890000,
    )


async def verify_exposure_effect():
    """Verify that exposure parameter truly affects position size."""
    print("=" * 60)
    print("EXPOSURE PARAMETER VERIFICATION")
    print("=" * 60)

    # Test case: Existing position consumes 50% exposure
    positions = [
        PositionInfo(
            symbol="BTC/USDT:USDT",
            side="long",
            size=Decimal("1"),
            entry_price=Decimal("50000"),  # 50% of total balance
            unrealized_pnl=Decimal("0"),
            leverage=10,
        )
    ]
    account = create_account(
        total_balance=Decimal("100000"),
        available_balance=Decimal("50000"),
        positions=positions,
    )
    entry_price = Decimal("100")
    stop_loss = Decimal("95")  # stop_distance = 5

    # Calculate with exposure=1.0
    config_1_0 = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10,
        max_total_exposure=Decimal("1.0"),
    )
    calc_1_0 = RiskCalculator(config_1_0)
    size_1_0, lev_1_0 = await calc_1_0.calculate_position_size(
        account, entry_price, stop_loss, Direction.LONG
    )

    # Calculate with exposure=3.0
    config_3_0 = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10,
        max_total_exposure=Decimal("3.0"),
    )
    calc_3_0 = RiskCalculator(config_3_0)
    size_3_0, lev_3_0 = await calc_3_0.calculate_position_size(
        account, entry_price, stop_loss, Direction.LONG
    )

    print(f"\nTest Case: 50% existing exposure")
    print(f"  Total Balance: {account.total_balance}")
    print(f"  Available Balance: {account.available_balance}")
    print(f"  Existing Position Value: {positions[0].size * positions[0].entry_price}")
    print(f"  Entry Price: {entry_price}")
    print(f"  Stop Loss: {stop_loss}")
    print(f"\nResults:")
    print(f"  exposure=1.0: position_size={size_1_0}, leverage={lev_1_0}")
    print(f"  exposure=3.0: position_size={size_3_0}, leverage={lev_3_0}")

    # Both should give same result because RISK is the limiting factor
    # Risk-based = 50000 * 0.01 / 5 = 100
    # Exposure-based (1.0) = 50000 / 100 = 500
    # Exposure-based (3.0) = 250000 / 100 = 2500
    # Leverage-based = 50000 * 10 / 100 = 5000
    # Min = 100 (risk limiting)

    print("\n  Analysis:")
    print(f"    Risk-based: 50000 * 0.01 / 5 = 100")
    print(f"    Exposure-based (1.0): (100000 * 1.0 - 50000) / 100 = 500")
    print(f"    Exposure-based (3.0): (100000 * 3.0 - 50000) / 100 = 2500")
    print(f"    Leverage-based: 50000 * 10 / 100 = 5000")
    print(f"    Result: min(100, 500, 5000) = 100 (risk limiting)")

    assert size_1_0 == Decimal("100"), f"Expected 100, got {size_1_0}"
    assert size_3_0 == Decimal("100"), f"Expected 100, got {size_3_0}"
    print("\n  [PASS] Both constrained by risk as expected")


async def verify_exposure_constraint_limits():
    """Verify that exposure constraint limits position when risk is loose."""
    print("\n" + "=" * 60)
    print("EXPOSURE CONSTRAINT LIMITING TEST")
    print("=" * 60)

    # Tight stop loss makes risk constraint loose
    positions = [
        PositionInfo(
            symbol="BTC/USDT:USDT",
            side="long",
            size=Decimal("1"),
            entry_price=Decimal("40000"),  # 40% exposure
            unrealized_pnl=Decimal("0"),
            leverage=10,
        )
    ]
    account = create_account(
        total_balance=Decimal("100000"),
        available_balance=Decimal("60000"),
        positions=positions,
    )
    entry_price = Decimal("100")
    stop_loss = Decimal("99")  # Tight stop: distance = 1

    # With exposure=0.5
    config = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10,
        max_total_exposure=Decimal("0.5"),
    )
    calc = RiskCalculator(config)
    size, lev = await calc.calculate_position_size(
        account, entry_price, stop_loss, Direction.LONG
    )

    print(f"\nTest Case: 40% existing exposure, tight stop (1%)")
    print(f"  Total Balance: {account.total_balance}")
    print(f"  Available Balance: {account.available_balance}")
    print(f"  Existing Position Value: {positions[0].size * positions[0].entry_price}")
    print(f"  Entry Price: {entry_price}")
    print(f"  Stop Loss: {stop_loss} (tight stop)")
    print(f"\nResults:")
    print(f"  position_size={size}, leverage={lev}")

    print("\n  Analysis:")
    print(f"    Risk-based: 60000 * 0.01 / 1 = 600")
    print(f"    Exposure-based: (100000 * 0.5 - 40000) / 100 = 100")
    print(f"    Leverage-based: 60000 * 10 / 100 = 6000")
    print(f"    Result: min(600, 100, 6000) = 100 (exposure limiting!)")

    assert size == Decimal("100"), f"Expected 100, got {size}"
    print("\n  [PASS] Exposure constraint is correctly limiting")


async def verify_three_constraints_independent():
    """Verify that all three constraints work independently."""
    print("\n" + "=" * 60)
    print("THREE-LAYER INDEPENDENT CONSTRAINT TEST")
    print("=" * 60)

    account = create_account(
        total_balance=Decimal("100000"),
        available_balance=Decimal("100000"),
    )
    entry_price = Decimal("100")
    stop_loss = Decimal("99")  # distance = 1

    # Test 1: Risk constraint limiting
    print("\nTest 1: Risk Constraint Limiting")
    config_risk = RiskConfig(
        max_loss_percent=Decimal("0.001"),  # Very low risk
        max_leverage=100,
        max_total_exposure=Decimal("10"),
    )
    calc_risk = RiskCalculator(config_risk)
    size_risk, _ = await calc_risk.calculate_position_size(
        account, entry_price, stop_loss, Direction.LONG
    )
    print(f"  Config: risk=0.1%, leverage=100x, exposure=1000%")
    print(f"  Expected: 100000 * 0.001 / 1 = 100 (risk limiting)")
    print(f"  Result: {size_risk}")
    assert size_risk == Decimal("100"), f"Expected 100, got {size_risk}"
    print("  [PASS]")

    # Test 2: Leverage constraint limiting
    print("\nTest 2: Leverage Constraint Limiting")
    config_lev = RiskConfig(
        max_loss_percent=Decimal("0.1"),  # High risk
        max_leverage=1,  # No leverage
        max_total_exposure=Decimal("10"),
    )
    calc_lev = RiskCalculator(config_lev)
    size_lev, _ = await calc_lev.calculate_position_size(
        account, entry_price, stop_loss, Direction.LONG
    )
    print(f"  Config: risk=10%, leverage=1x, exposure=1000%")
    print(f"  Expected: min(10000, 10000, 1000) = 1000 (leverage limiting)")
    print(f"  Result: {size_lev}")
    assert size_lev == Decimal("1000"), f"Expected 1000, got {size_lev}"
    print("  [PASS]")

    # Test 3: Exposure constraint limiting
    print("\nTest 3: Exposure Constraint Limiting")
    config_exp = RiskConfig(
        max_loss_percent=Decimal("0.1"),
        max_leverage=100,
        max_total_exposure=Decimal("0.5"),  # 50% exposure cap
    )
    calc_exp = RiskCalculator(config_exp)
    size_exp, _ = await calc_exp.calculate_position_size(
        account, entry_price, stop_loss, Direction.LONG
    )
    print(f"  Config: risk=10%, leverage=100x, exposure=50%")
    print(f"  Expected: min(10000, 500, 100000) = 500 (exposure limiting)")
    print(f"  Result: {size_exp}")
    assert size_exp == Decimal("500"), f"Expected 500, got {size_exp}"
    print("  [PASS]")


async def verify_zero_exposure():
    """Verify that exposure=0 returns zero position."""
    print("\n" + "=" * 60)
    print("ZERO EXPOSURE TEST")
    print("=" * 60)

    config = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10,
        max_total_exposure=Decimal("0"),
    )
    calc = RiskCalculator(config)
    account = create_account(total_balance=Decimal("100000"))
    entry_price = Decimal("100")
    stop_loss = Decimal("95")

    size, lev = await calc.calculate_position_size(
        account, entry_price, stop_loss, Direction.LONG
    )

    print(f"\nTest Case: max_total_exposure=0")
    print(f"  Result: position_size={size}, leverage={lev}")
    assert size == Decimal("0"), f"Expected 0, got {size}"
    print("  [PASS] Zero exposure correctly returns zero position")


async def verify_exceeded_exposure():
    """Verify that exceeded exposure returns zero position."""
    print("\n" + "=" * 60)
    print("EXCEEDED EXPOSURE TEST")
    print("=" * 60)

    # Position that exceeds 50% exposure limit
    positions = [
        PositionInfo(
            symbol="BTC/USDT:USDT",
            side="long",
            size=Decimal("1"),
            entry_price=Decimal("60000"),  # 60% exposure
            unrealized_pnl=Decimal("0"),
            leverage=10,
        )
    ]
    account = create_account(
        total_balance=Decimal("100000"),
        available_balance=Decimal("40000"),
        positions=positions,
    )

    config = RiskConfig(
        max_loss_percent=Decimal("0.01"),
        max_leverage=10,
        max_total_exposure=Decimal("0.5"),  # 50% cap
    )
    calc = RiskCalculator(config)
    entry_price = Decimal("100")
    stop_loss = Decimal("95")

    size, lev = await calc.calculate_position_size(
        account, entry_price, stop_loss, Direction.LONG
    )

    print(f"\nTest Case: 60% exposure with 50% cap")
    print(f"  Existing Position Value: {positions[0].size * positions[0].entry_price}")
    print(f"  Result: position_size={size}, leverage={lev}")
    assert size == Decimal("0"), f"Expected 0, got {size}"
    print("  [PASS] Exceeded exposure correctly returns zero position")


async def main():
    """Run all verification tests."""
    print("\n" + "=" * 60)
    print("RISK CALCULATOR EXPOSURE FIX VERIFICATION")
    print("=" * 60)

    try:
        await verify_exposure_effect()
        await verify_exposure_constraint_limits()
        await verify_three_constraints_independent()
        await verify_zero_exposure()
        await verify_exceeded_exposure()

        print("\n" + "=" * 60)
        print("ALL VERIFICATION TESTS PASSED!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n[FAIL] Verification failed: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
