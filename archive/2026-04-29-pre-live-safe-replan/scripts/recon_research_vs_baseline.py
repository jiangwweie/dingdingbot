#!/usr/bin/env python3
"""
Reconciliation: Research Control Plane path vs old baseline script.

Runs a small 2-week window via both paths and compares effective parameters + results.
Does NOT modify any production code, runtime profiles, or DB data.
"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    OrderStrategy,
    RiskConfig,
)
from src.application.backtester import Backtester, resolve_backtest_params
from src.application.research_control_plane import (
    LocalBacktestResearchRunner,
    BASELINE_RUNTIME_OVERRIDES,
)
from src.domain.research_models import ResearchSpec, ResearchEngineCostSpec
from src.application.research_specs import BacktestJobSpec, EngineCostSpec, TimeWindowMs
from src.infrastructure.exchange_gateway import ExchangeGateway
from src.infrastructure.historical_data_repository import HistoricalDataRepository
from src.infrastructure.config_entry_repository import ConfigEntryRepository
from src.application.config_manager import ConfigManager


# ── Shared window: 2025-01-01 to 2025-01-14 (2 weeks) ──────────────

START_MS = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
END_MS = int(datetime(2025, 1, 14, tzinfo=timezone.utc).timestamp() * 1000)
SYMBOL = "ETH/USDT:USDT"
TIMEFRAME = "1h"
LIMIT = 9000


def print_section(title: str):
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


async def run_old_baseline_path(data_repo, cm):
    """Old script path: explicit BacktestRequest + runtime_overrides + order_strategy."""
    print_section("PATH A: Old Baseline Script")

    request = BacktestRequest(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time=START_MS,
        end_time=END_MS,
        limit=LIMIT,
        mode="v3_pms",
        slippage_rate=Decimal("0.0001"),
        tp_slippage_rate=Decimal("0"),
        fee_rate=Decimal("0.000405"),
        initial_balance=Decimal("10000"),
    )

    runtime_overrides = BacktestRuntimeOverrides(
        ema_period=50,
        min_distance_pct=Decimal("0.005"),
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        breakeven_enabled=False,
        allowed_directions=["LONG"],
    )

    request.order_strategy = OrderStrategy(
        id="baseline_recon",
        name="Baseline Recon",
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
        trailing_stop_enabled=False,
        oco_enabled=True,
    )

    backtester = Backtester(None, data_repository=data_repo, config_manager=cm)
    report = await backtester.run_backtest(request, runtime_overrides=runtime_overrides)

    # Resolve params for comparison
    kv_configs = await cm.get_backtest_configs() if cm else {}
    resolved = resolve_backtest_params(runtime_overrides, request, kv_configs)

    print(f"  start_time:       {START_MS} ({datetime.fromtimestamp(START_MS/1000, tz=timezone.utc).isoformat()})")
    print(f"  end_time:         {END_MS} ({datetime.fromtimestamp(END_MS/1000, tz=timezone.utc).isoformat()})")
    print(f"  slippage_rate:    {request.slippage_rate}")
    print(f"  tp_slippage_rate: {request.tp_slippage_rate}")
    print(f"  fee_rate:         {request.fee_rate}")
    print(f"  initial_balance:  {request.initial_balance}")
    print(f"  ema_period:       {resolved.ema_period}")
    print(f"  tp_ratios:        {resolved.tp_ratios}")
    print(f"  tp_targets:       {resolved.tp_targets}")
    print(f"  allowed_dirs:     {resolved.allowed_directions}")
    print(f"  breakeven:        {resolved.breakeven_enabled}")
    print(f"  order_strategy:   {request.order_strategy is not None}")
    print(f"  risk_overrides:   {request.risk_overrides}")
    print(f"  funding_enabled:  {request.funding_rate_enabled}")

    print(f"\n  --- Results ---")
    print(f"  total_trades:     {report.total_trades}")
    print(f"  total_pnl:        {report.total_pnl}")
    print(f"  final_balance:    {report.final_balance}")
    print(f"  win_rate:         {report.win_rate}")
    print(f"  max_drawdown:     {report.max_drawdown}")
    print(f"  sharpe_ratio:     {report.sharpe_ratio}")

    return {
        "resolved": resolved,
        "report": report,
        "request": request,
        "runtime_overrides": runtime_overrides,
    }


async def run_research_path(data_repo, cm):
    """Research Control Plane path: ResearchSpec → BacktestJobSpec → BacktestRequest."""
    print_section("PATH B: Research Control Plane")

    spec = ResearchSpec(
        name="recon-test",
        profile_name="backtest_eth_baseline",
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        start_time_ms=START_MS,
        end_time_ms=END_MS,
        limit=LIMIT,
        mode="v3_pms",
        costs=ResearchEngineCostSpec(
            initial_balance=Decimal("10000"),
            slippage_rate=Decimal("0.0001"),
            tp_slippage_rate=Decimal("0"),
            fee_rate=Decimal("0.000405"),
        ),
    )

    # Simulate what LocalBacktestResearchRunner does
    runner = LocalBacktestResearchRunner(
        artifact_root="/tmp/research_recon",
        backtest_executor=None,  # We'll call backtester directly
    )

    resolved_overrides = runner._resolve_runtime_overrides(spec)
    request = runner._to_backtest_request(spec)

    print(f"  resolved_overrides: {resolved_overrides}")
    print(f"  request.mode:       {request.mode}")
    print(f"  request.limit:      {request.limit}")
    print(f"  request.start_time: {request.start_time}")
    print(f"  request.end_time:   {request.end_time}")
    print(f"  request.slippage:   {request.slippage_rate}")
    print(f"  request.tp_slip:    {request.tp_slippage_rate}")
    print(f"  request.fee:        {request.fee_rate}")
    print(f"  request.order_strategy: {request.order_strategy}")
    print(f"  request.risk_overrides: {request.risk_overrides}")
    print(f"  request.funding_rate_enabled: {request.funding_rate_enabled}")

    # Resolve params for comparison
    kv_configs = await cm.get_backtest_configs() if cm else {}
    resolved = resolve_backtest_params(resolved_overrides, request, kv_configs)

    print(f"\n  --- Resolved Params ---")
    print(f"  ema_period:       {resolved.ema_period}")
    print(f"  tp_ratios:        {resolved.tp_ratios}")
    print(f"  tp_targets:       {resolved.tp_targets}")
    print(f"  allowed_dirs:     {resolved.allowed_directions}")
    print(f"  breakeven:        {resolved.breakeven_enabled}")
    print(f"  slippage_rate:    {resolved.slippage_rate}")
    print(f"  tp_slippage_rate: {resolved.tp_slippage_rate}")
    print(f"  fee_rate:         {resolved.fee_rate}")
    print(f"  initial_balance:  {resolved.initial_balance}")

    # Run backtest
    backtester = Backtester(None, data_repository=data_repo, config_manager=cm)
    report = await backtester.run_backtest(request, runtime_overrides=resolved_overrides)

    print(f"\n  --- Results ---")
    print(f"  total_trades:     {report.total_trades}")
    print(f"  total_pnl:        {report.total_pnl}")
    print(f"  final_balance:    {report.final_balance}")
    print(f"  win_rate:         {report.win_rate}")
    print(f"  max_drawdown:     {report.max_drawdown}")
    print(f"  sharpe_ratio:     {report.sharpe_ratio}")

    return {
        "resolved": resolved,
        "report": report,
        "request": request,
        "resolved_overrides": resolved_overrides,
    }


async def main():
    print_section("Reconciliation: Research vs Old Baseline")
    print(f"  Window: 2025-01-01 to 2025-01-14 (2 weeks)")
    print(f"  Symbol: {SYMBOL}, Timeframe: {TIMEFRAME}")

    data_repo = HistoricalDataRepository()
    await data_repo.initialize()

    try:
        cm = ConfigManager()
        entry_repo = ConfigEntryRepository()
        await entry_repo.initialize()
        cm.set_config_entry_repository(entry_repo)
        await cm.initialize_from_db()

        result_a = await run_old_baseline_path(data_repo, cm)
        result_b = await run_research_path(data_repo, cm)

        # ── Parameter comparison ──────────────────────────────────────
        print_section("PARAMETER COMPARISON")

        ra = result_a["resolved"]
        rb = result_b["resolved"]

        comparisons = [
            ("ema_period",       ra.ema_period,       rb.ema_period),
            ("tp_ratios",        ra.tp_ratios,        rb.tp_ratios),
            ("tp_targets",       ra.tp_targets,        rb.tp_targets),
            ("allowed_dirs",     ra.allowed_directions, rb.allowed_directions),
            ("breakeven",        ra.breakeven_enabled, rb.breakeven_enabled),
            ("slippage_rate",    ra.slippage_rate,    rb.slippage_rate),
            ("tp_slippage_rate", ra.tp_slippage_rate, rb.tp_slippage_rate),
            ("fee_rate",         ra.fee_rate,         rb.fee_rate),
            ("initial_balance",  ra.initial_balance,  rb.initial_balance),
            ("min_distance_pct", ra.min_distance_pct, rb.min_distance_pct),
            ("max_atr_ratio",    ra.max_atr_ratio,    rb.max_atr_ratio),
            ("same_bar_policy",  ra.same_bar_policy,  rb.same_bar_policy),
        ]

        mismatches = 0
        for name, va, vb in comparisons:
            match = "✓" if va == vb else "✗ MISMATCH"
            if va != vb:
                mismatches += 1
            print(f"  {name:<20} A={va!s:<30} B={vb!s:<30} {match}")

        # ── Extra fields in old path ──────────────────────────────────
        print(f"\n  --- Fields only in old path ---")
        req_a = result_a["request"]
        print(f"  order_strategy:   {req_a.order_strategy is not None}  (Research: {result_b['request'].order_strategy is not None})")
        print(f"  risk_overrides:   {req_a.risk_overrides}  (Research: {result_b['request'].risk_overrides})")
        print(f"  funding_rate_enabled: {req_a.funding_rate_enabled}  (Research: {result_b['request'].funding_rate_enabled})")

        # ── Result comparison ─────────────────────────────────────────
        print_section("RESULT COMPARISON")

        rep_a = result_a["report"]
        rep_b = result_b["report"]

        result_comparisons = [
            ("total_trades",  rep_a.total_trades,  rep_b.total_trades),
            ("total_pnl",     rep_a.total_pnl,     rep_b.total_pnl),
            ("final_balance", rep_a.final_balance, rep_b.final_balance),
            ("win_rate",      rep_a.win_rate,      rep_b.win_rate),
            ("max_drawdown",  rep_a.max_drawdown,  rep_b.max_drawdown),
            ("sharpe_ratio",  rep_a.sharpe_ratio,  rep_b.sharpe_ratio),
        ]

        for name, va, vb in result_comparisons:
            match = "✓" if va == vb else "✗ DIFF"
            print(f"  {name:<16} A={va!s:<30} B={vb!s:<30} {match}")

        # ── Summary ──────────────────────────────────────────────────
        print_section("SUMMARY")
        print(f"  Parameter mismatches: {mismatches}")
        if mismatches == 0:
            print(f"  All resolved parameters MATCH between paths.")
        else:
            print(f"  Some resolved parameters DIFFER — see above.")

        pnl_diff = rep_a.total_pnl - rep_b.total_pnl
        trades_diff = rep_a.total_trades - rep_b.total_trades
        print(f"  PnL diff (A-B):      {pnl_diff}")
        print(f"  Trades diff (A-B):   {trades_diff}")

        if req_a.order_strategy and result_b["request"].order_strategy is None:
            print(f"\n  REMAINING GAP: Old path has explicit order_strategy, Research path does not.")
            print(f"  Old order_strategy: tp_levels={req_a.order_strategy.tp_levels}, "
                  f"tp_ratios={req_a.order_strategy.tp_ratios}, "
                  f"tp_targets={req_a.order_strategy.tp_targets}, "
      f"initial_stop_loss_rr={req_a.order_strategy.initial_stop_loss_rr}")

        if req_a.risk_overrides and result_b["request"].risk_overrides is None:
            print(f"\n  REMAINING GAP: Old path has risk_overrides, Research path does not.")
            print(f"  Old risk_overrides: max_loss_percent={req_a.risk_overrides.max_loss_percent}, "
                  f"max_leverage={req_a.risk_overrides.max_leverage}, "
                  f"max_total_exposure={req_a.risk_overrides.max_total_exposure}")

    finally:
        await data_repo.close()
        await entry_repo.close()


if __name__ == "__main__":
    asyncio.run(main())