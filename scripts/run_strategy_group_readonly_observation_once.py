#!/usr/bin/env python3
"""Run one cron-ready read-only MI/CPM strategy-group observation cycle.

The command reads only closed market candles, writes observe-only evidence to
PG, and never starts runtime, creates execution intents, grants permissions, or
touches order paths.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except (ImportError, ModuleNotFoundError):
        return
    load_dotenv(REPO_ROOT / ".env")
    load_dotenv(REPO_ROOT / ".env.local", override=True)


async def _run(args: argparse.Namespace) -> int:
    from src.application.strategy_group_readonly_observation_scheduler import (
        run_scheduled_readonly_observation_once,
    )

    if args.allow_shadow_candidate_creation and not args.shadow_plan:
        print(
            "--allow-shadow-candidate-creation requires --shadow-plan",
            file=sys.stderr,
        )
        return 2

    run_kwargs: dict[str, Any] = {"source_name": args.source}
    closeables: list[Any] = []
    if args.shadow_plan:
        resolver, planning_service, closeables = await _build_shadow_planning_dependencies(args)
        run_kwargs.update(
            {
                "runtime_resolver": resolver,
                "runtime_signal_planning_service": planning_service,
                "allow_shadow_candidate_creation": args.allow_shadow_candidate_creation,
            }
        )

    try:
        result = await run_scheduled_readonly_observation_once(**run_kwargs)
    finally:
        await _close_dependencies(closeables)

    payload = result.model_dump(mode="json")
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "scheduled_readonly_strategy_group_observation_v0 "
            f"source={result.market_source} sink={result.sink} "
            f"inserted={result.inserted_count} skipped_duplicate={result.skipped_duplicate_count} "
            f"failed={result.failed_count} "
            f"shadow_plan={'enabled' if args.shadow_plan else 'disabled'}"
        )
        for item in result.candidate_results:
            runtime_fragment = (
                f" runtime={item.runtime_instance_id}"
                if item.runtime_instance_id
                else ""
            )
            print(
                f"- {item.candidate_id} {item.symbol} {item.side} "
                f"signal={item.signal_type} bar={item.market_bar_timestamp_ms} "
                f"action={item.action} record={item.record_id} "
                f"shadow={item.shadow_planning_action}{runtime_fragment}"
            )
    return 1 if result.failed_count else 0


async def _build_shadow_planning_dependencies(
    args: argparse.Namespace,
) -> tuple[Any, Any, list[Any]]:
    from src.application.runtime_execution_planning_service import (
        RuntimeExecutionPlanningService,
    )
    from src.application.runtime_final_gate_preview_service import (
        RuntimeFinalGatePreviewService,
    )
    from src.application.runtime_strategy_signal_scheduler_assembly import (
        RuntimeStrategySignalSchedulerFactSources,
    )
    from src.application.runtime_strategy_signal_scheduler_planning_service import (
        RuntimeStrategySignalSchedulerPlanningService,
    )
    from src.application.runtime_strategy_signal_planning_service import (
        RuntimeStrategySignalPlanningService,
    )
    from src.application.signal_evaluation_shadow_service import (
        SignalEvaluationShadowService,
    )
    from src.application.strategy_group_readonly_observation_scheduler import (
        StrategyRuntimeObservationResolver,
    )
    from src.application.strategy_runtime_fact_overlay_service import (
        StrategyRuntimeFactOverlayService,
    )
    from src.application.strategy_runtime_service import StrategyRuntimeInstanceService
    from src.application.strategy_semantics_shadow_binding_service import (
        StrategySemanticsShadowBindingService,
    )
    from src.infrastructure.pg_brc_admission_repository import PgBrcAdmissionRepository
    from src.infrastructure.pg_position_repository import PgPositionRepository
    from src.infrastructure.pg_runtime_execution_intent_draft_repository import (
        PgRuntimeExecutionIntentDraftRepository,
    )
    from src.infrastructure.pg_signal_evaluation_repository import (
        PgSignalEvaluationRepository,
    )
    from src.infrastructure.pg_strategy_runtime_repository import (
        PgStrategyRuntimeRepository,
    )

    closeables: list[Any] = []
    runtime_service = StrategyRuntimeInstanceService(
        runtime_repository=PgStrategyRuntimeRepository(),
        admission_repository=PgBrcAdmissionRepository(),
    )
    await runtime_service.initialize()

    signal_shadow_service = SignalEvaluationShadowService(
        repository=PgSignalEvaluationRepository(),
    )
    await signal_shadow_service.initialize()

    position_source = PgPositionRepository()
    account_facts_source = _build_account_facts_source(args)
    if account_facts_source is not None:
        closeables.append(account_facts_source)
    market_fact_source = (
        _build_public_market_fact_source()
        if args.public_market_facts
        else None
    )

    final_gate_preview_service = RuntimeFinalGatePreviewService(
        runtime_service=runtime_service,
        signal_evaluation_service=signal_shadow_service,
        active_position_source=position_source,
    )
    runtime_execution_planning_service = RuntimeExecutionPlanningService(
        runtime_service=runtime_service,
        signal_evaluation_service=signal_shadow_service,
        final_gate_preview_service=final_gate_preview_service,
        intent_draft_repository=PgRuntimeExecutionIntentDraftRepository(),
    )
    signal_planning_service = RuntimeStrategySignalPlanningService(
        semantics_binding_service=StrategySemanticsShadowBindingService(
            shadow_service=signal_shadow_service,
        ),
        runtime_execution_planning_service=runtime_execution_planning_service,
        runtime_fact_overlay_service=StrategyRuntimeFactOverlayService(
            active_position_source=position_source,
            account_facts_source=account_facts_source,
            market_fact_source=market_fact_source,
        ),
    )
    scheduler_planning_service = RuntimeStrategySignalSchedulerPlanningService(
        planner=signal_planning_service,
        fact_sources=RuntimeStrategySignalSchedulerFactSources(
            trusted_runtime_fact_overlay_configured=True,
            trusted_active_position_source_available=True,
            trusted_account_facts_source_available=account_facts_source is not None,
            trusted_market_fact_source_available=market_fact_source is not None,
            source_scope="scheduled_observation_cli_non_endpoint_sources",
            metadata={
                "pg_position_source_configured": True,
                "account_facts_source": args.account_facts_source,
                "public_market_fact_source_configured": market_fact_source is not None,
                "non_executing": True,
                "cli_shadow_plan": True,
            },
        ),
    )
    return (
        StrategyRuntimeObservationResolver(runtime_service=runtime_service),
        scheduler_planning_service,
        closeables,
    )


def _build_account_facts_source(args: argparse.Namespace) -> Any | None:
    if args.account_facts_source == "none":
        return None
    from src.application.binance_usdt_futures_account_facts import (
        BinanceUsdtFuturesAccountFactsSource,
        CcxtBinanceUsdtFuturesBalanceClient,
    )

    api_key = os.environ.get("EXCHANGE_API_KEY", "").strip()
    api_secret = os.environ.get("EXCHANGE_API_SECRET", "").strip()
    if not api_key or not api_secret:
        raise RuntimeError(
            "EXCHANGE_API_KEY and EXCHANGE_API_SECRET are required for "
            "--account-facts-source binance_readonly"
        )
    client = CcxtBinanceUsdtFuturesBalanceClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=_parse_bool_env(os.environ.get("EXCHANGE_TESTNET")),
    )
    return BinanceUsdtFuturesAccountFactsSource(balance_client=client)


def _build_public_market_fact_source() -> Any:
    from src.infrastructure.binance_usdm_derivative_market_fact_source import (
        BinanceUsdmDerivativeMarketFactSource,
    )

    return BinanceUsdmDerivativeMarketFactSource()


async def _close_dependencies(items: list[Any]) -> None:
    for item in reversed(items):
        close = getattr(item, "close", None)
        if close is None:
            continue
        result = close()
        if asyncio.iscoroutine(result):
            await result


def _parse_bool_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=["live_market", "local_sqlite_read_only"],
        default="live_market",
        help="Closed-candle read-only market source.",
    )
    parser.add_argument(
        "--shadow-plan",
        action="store_true",
        help=(
            "Explicitly inject runtime resolver and non-executing shadow planner. "
            "Without --allow-shadow-candidate-creation this remains readiness-only."
        ),
    )
    parser.add_argument(
        "--allow-shadow-candidate-creation",
        action="store_true",
        help=(
            "Allow shadow SignalEvaluation / OrderCandidate creation when all "
            "non-executing gates pass. Requires --shadow-plan."
        ),
    )
    parser.add_argument(
        "--account-facts-source",
        choices=["none", "binance_readonly"],
        default="none",
        help=(
            "Trusted account facts source for shadow planning. 'none' causes "
            "candidate planning to block on missing account facts."
        ),
    )
    parser.add_argument(
        "--public-market-facts",
        action="store_true",
        help="Enable public/read-only Binance USD-M funding/OI/crowding facts.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON for cron/log capture.")
    args = parser.parse_args()
    _load_env()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
