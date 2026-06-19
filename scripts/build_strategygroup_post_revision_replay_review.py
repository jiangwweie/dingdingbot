#!/usr/bin/env python3
"""Build the local LSR/VCB post-revision replay review packet.

This review executes deterministic local evaluator fixtures after the LSR/VCB
classifier revisions. It proves the revised classifiers can distinguish
would-enter observation cases from disable/no-action cases. It is not L2
promotion authority, L4 scope authority, FinalGate input, Operation Layer input,
or real-order authority.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.domain.reference_price_action_evaluators import (  # noqa: E402
    LSR001PriceActionEvaluator,
    VCB001PriceActionEvaluator,
)
from src.domain.strategy_family_signal import (  # noqa: E402
    AccountFactsSnapshot,
    MarketSnapshot,
    SignalSide,
    SignalType,
    StrategyFamilySignalInput,
)


DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-post-revision-replay-review.json"
)
DEFAULT_OWNER_PROGRESS = (
    REPO_ROOT / "output/runtime-monitor/latest-post-revision-replay-review.md"
)
NOW_MS = 1781869000000


def build_post_revision_replay_review() -> dict[str, Any]:
    rows = [
        _review_case(
            strategy_group_id="LSR-001",
            version_id="LSR-001-v0",
            fixture_case="short_revival_short_would_enter",
            evaluator=LSR001PriceActionEvaluator(),
            one_hour=_lsr_short_revival_1h(),
            expected_signal_type=SignalType.WOULD_ENTER,
            expected_side=SignalSide.SHORT,
            expected_reason_codes={
                "lsr_upper_range_liquidity_sweep_detected",
                "lsr_short_revival_confirmation_present",
                "lsr_lookahead_proxy_absent",
            },
        ),
        _review_case(
            strategy_group_id="LSR-001",
            version_id="LSR-001-v0",
            fixture_case="old_long_preview_disabled",
            evaluator=LSR001PriceActionEvaluator(),
            one_hour=_lsr_old_long_preview_1h(),
            expected_signal_type=SignalType.NO_ACTION,
            expected_side=SignalSide.NONE,
            expected_reason_codes={
                "lsr_disable_long_preview_conflicts_with_short_revival_lead"
            },
        ),
        _review_case(
            strategy_group_id="VCB-001",
            version_id="VCB-001-v0",
            fixture_case="true_breakout_with_volume_would_enter",
            evaluator=VCB001PriceActionEvaluator(),
            one_hour=_vcb_true_breakout_1h(),
            expected_signal_type=SignalType.WOULD_ENTER,
            expected_side=SignalSide.LONG,
            expected_reason_codes={
                "vcb_compression_window_present",
                "vcb_breakout_close_confirmed",
                "vcb_volume_expansion_confirmed",
                "vcb_post_entry_edge_proxy_without_lookahead",
            },
        ),
        _review_case(
            strategy_group_id="VCB-001",
            version_id="VCB-001-v0",
            fixture_case="false_breakout_reversal_disabled",
            evaluator=VCB001PriceActionEvaluator(),
            one_hour=_vcb_false_breakout_1h(),
            expected_signal_type=SignalType.NO_ACTION,
            expected_side=SignalSide.NONE,
            expected_reason_codes={"vcb_disable_false_breakout_reversal_detected"},
        ),
        _review_case(
            strategy_group_id="VCB-001",
            version_id="VCB-001-v0",
            fixture_case="volume_expansion_missing_disabled",
            evaluator=VCB001PriceActionEvaluator(),
            one_hour=_vcb_missing_volume_expansion_1h(),
            expected_signal_type=SignalType.NO_ACTION,
            expected_side=SignalSide.NONE,
            expected_reason_codes={"vcb_no_action_volume_expansion_missing"},
        ),
    ]
    failed_rows = [row for row in rows if row["passed"] is not True]
    status = "passed" if not failed_rows else "blocked"
    lsr_rows = [row for row in rows if row["strategy_group_id"] == "LSR-001"]
    vcb_rows = [row for row in rows if row["strategy_group_id"] == "VCB-001"]
    return {
        "schema": "brc.strategygroup_post_revision_replay_review.v1",
        "scope": "strategygroup_post_revision_replay_review",
        "status": status,
        "interaction": {
            "level": "L0_local_post_revision_replay_review",
            "remote_interaction_count": 0,
            "mutates_remote_files": False,
            "approaches_real_order": False,
            "calls_finalgate": False,
            "calls_operation_layer": False,
            "calls_exchange_write": False,
            "places_order": False,
        },
        "counts": {
            "review_case_count": len(rows),
            "passed_case_count": len(rows) - len(failed_rows),
            "failed_case_count": len(failed_rows),
            "lsr_case_count": len(lsr_rows),
            "vcb_case_count": len(vcb_rows),
            "would_enter_case_count": sum(
                1 for row in rows if row["observed_signal_type"] == "would_enter"
            ),
            "disable_or_no_action_case_count": sum(
                1 for row in rows if row["observed_signal_type"] == "no_action"
            ),
            "real_order_authorized_count": 0,
            "l4_scope_change_recommended_count": 0,
        },
        "checks": {
            "lsr_short_revival_would_enter": _case_passed(
                rows, "LSR-001", "short_revival_short_would_enter"
            ),
            "lsr_old_long_preview_disabled": _case_passed(
                rows, "LSR-001", "old_long_preview_disabled"
            ),
            "vcb_true_breakout_with_volume_would_enter": _case_passed(
                rows, "VCB-001", "true_breakout_with_volume_would_enter"
            ),
            "vcb_false_breakout_reversal_disabled": _case_passed(
                rows, "VCB-001", "false_breakout_reversal_disabled"
            ),
            "vcb_volume_expansion_missing_disabled": _case_passed(
                rows, "VCB-001", "volume_expansion_missing_disabled"
            ),
            "no_case_authorizes_execution": all(
                row["real_order_authority"] is False
                and row["candidate_or_finalgate_authority"] is False
                and row["operation_layer_authority"] is False
                for row in rows
            ),
        },
        "review_rows": rows,
        "decision": {
            "post_revision_replay_review_passed": status == "passed",
            "l2_promotion_recommended_now": False,
            "l4_scope_change_recommended": False,
            "real_order_scope_change_recommended": False,
            "default_next_step": (
                "record_lsr001_vcb001_post_revision_quality_before_l2"
                if status == "passed"
                else "repair_lsr001_vcb001_post_revision_replay_failures"
            ),
        },
        "safety_invariants": {
            "local_post_revision_review_only": True,
            "server_interaction": False,
            "server_files_mutated": False,
            "strategy_parameters_changed": False,
            "tier_policy_changed": False,
            "l2_promotion_authorized": False,
            "l4_real_order_scope_expanded": False,
            "shadow_candidate_created": False,
            "execution_intent_created": False,
            "final_gate_called": False,
            "operation_layer_called": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_write_called": False,
            "withdrawal_or_transfer_created": False,
        },
    }


def build_owner_progress_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# LSR/VCB Post-Revision Replay Review",
        "",
        "## Summary",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Review cases: `{_as_dict(packet.get('counts')).get('review_case_count', 0)}`",
        f"- Passed: `{_as_dict(packet.get('counts')).get('passed_case_count', 0)}`",
        "- L2 promotion authority: `false`",
        "- L4 scope change: `false`",
        "- Real order authority: `false`",
        "",
        "## Review Rows",
        "",
        _review_table(_dict_rows(packet.get("review_rows"))),
        "",
        "## Next",
        "",
        f"- `{_as_dict(packet.get('decision')).get('default_next_step')}`",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _review_case(
    *,
    strategy_group_id: str,
    version_id: str,
    fixture_case: str,
    evaluator: Any,
    one_hour: list[dict[str, Any]],
    expected_signal_type: SignalType,
    expected_side: SignalSide,
    expected_reason_codes: set[str],
) -> dict[str, Any]:
    signal_input = _signal_input(
        family_id=strategy_group_id,
        version_id=version_id,
        one_hour=one_hour,
    )
    output = evaluator.evaluate(signal_input)
    observed_reason_codes = {str(item) for item in output.reason_codes}
    evidence = output.evidence_payload
    passed = (
        output.signal_type == expected_signal_type
        and output.side == expected_side
        and expected_reason_codes.issubset(observed_reason_codes)
        and output.not_order is True
        and output.not_execution_intent is True
    )
    return {
        "strategy_group_id": strategy_group_id,
        "fixture_case": fixture_case,
        "logic_version": str(evidence.get("logic_version") or ""),
        "observed_signal_type": output.signal_type.value,
        "expected_signal_type": expected_signal_type.value,
        "observed_side": output.side.value,
        "expected_side": expected_side.value,
        "reason_codes": sorted(observed_reason_codes),
        "expected_reason_codes": sorted(expected_reason_codes),
        "entry_states": _as_dict(evidence.get("entry_states")),
        "disable_states": _as_dict(evidence.get("disable_states")),
        "classifier_revision": _as_dict(evidence.get("classifier_revision")),
        "passed": passed,
        "real_order_authority": False,
        "candidate_or_finalgate_authority": False,
        "operation_layer_authority": False,
        "l2_promotion_authority": False,
        "l4_scope_change_recommended": False,
    }


def _case_passed(rows: list[dict[str, Any]], group: str, fixture_case: str) -> bool:
    return any(
        row["strategy_group_id"] == group
        and row["fixture_case"] == fixture_case
        and row["passed"] is True
        for row in rows
    )


def _signal_input(
    *,
    family_id: str,
    version_id: str,
    one_hour: list[dict[str, Any]],
) -> StrategyFamilySignalInput:
    return StrategyFamilySignalInput(
        evaluation_id=f"post-revision-{family_id}",
        strategy_family_id=family_id,
        strategy_family_version_id=version_id,
        symbol="ETH/USDT:USDT",
        timestamp_ms=NOW_MS,
        primary_timeframe="1h",
        context_timeframes=["4h"],
        market_snapshot=MarketSnapshot(
            symbol="ETH/USDT:USDT",
            timestamp_ms=NOW_MS,
            source="local_post_revision_replay",
            freshness="fresh",
            last_price=Decimal("106"),
            mark_price=Decimal("106"),
            funding_rate=Decimal("0.0001"),
            volatility=Decimal("0.18"),
            atr=Decimal("4"),
            timeframe="1h",
            candle_context={
                "windows": {"1h": one_hour, "4h": _mixed_context_4h()},
                "closed_bar": True,
            },
        ),
        account_facts_snapshot=AccountFactsSnapshot(
            source="local_post_revision_replay",
            truth_level="exchange_read",
            timestamp_ms=NOW_MS,
            freshness="fresh",
            account_status="normal",
            available_balance=Decimal("30"),
            positions=[],
            open_orders=[],
            position_count=0,
            open_order_count=0,
            unknown_unmanaged_counts={"orders": 0, "positions": 0},
            reconciliation_status={"status": "clean"},
            read_only_provider="local_post_revision_replay",
            limitations=[],
        ),
        position_open_order_summary={"position_count": 0, "open_order_count": 0},
        reconciliation_status={"status": "clean"},
        runtime_safety_snapshot={"runtime_state": "shadow", "live_ready": False},
        trial_constraints_snapshot={
            "max_attempts": 3,
            "max_loss_budget": "10",
            "max_notional_per_attempt": "10",
            "max_active_positions": 1,
            "max_leverage": "1",
            "allowed_symbols": ["ETH/USDT:USDT"],
        },
        source="local_post_revision_replay",
        freshness="fresh",
    )


def _candle(
    index: int,
    open_: str,
    high: str,
    low: str,
    close: str,
    *,
    volume: str = "100",
) -> dict[str, Any]:
    return {
        "open_time_ms": NOW_MS - (30 - index) * 3_600_000,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _mixed_context_4h() -> list[dict[str, Any]]:
    return [
        _candle(0, "100", "103", "98", "101"),
        _candle(1, "101", "104", "99", "102"),
        _candle(2, "102", "105", "100", "101"),
        _candle(3, "101", "104", "99", "102"),
    ]


def _lsr_old_long_preview_1h() -> list[dict[str, Any]]:
    candles = [_candle(index, "104", "110", "100", "105") for index in range(13)]
    candles.append(_candle(13, "101", "106", "98", "103"))
    return candles


def _lsr_short_revival_1h() -> list[dict[str, Any]]:
    candles = [_candle(index, "104", "110", "100", "105") for index in range(13)]
    candles.append(_candle(13, "109", "112", "104", "108"))
    return candles


def _vcb_true_breakout_1h() -> list[dict[str, Any]]:
    return [
        _candle(0, "100", "103", "99", "102"),
        _candle(1, "101", "105", "99", "103"),
        _candle(2, "102", "106", "100", "104"),
        _candle(3, "103", "107", "101", "105"),
        _candle(4, "104", "108", "102", "106"),
        _candle(5, "105", "109", "103", "107"),
        _candle(6, "106", "110", "104", "108"),
        _candle(7, "107.0", "107.8", "106.8", "107.2"),
        _candle(8, "107.2", "108.0", "107.0", "107.4"),
        _candle(9, "107.4", "108.2", "107.2", "107.6"),
        _candle(10, "107.6", "108.4", "107.4", "107.8"),
        _candle(11, "107.8", "108.5", "107.5", "108.0"),
        _candle(12, "108.0", "108.6", "107.6", "108.2"),
        _candle(13, "108.4", "111", "108.2", "110", volume="180"),
    ]


def _vcb_false_breakout_1h() -> list[dict[str, Any]]:
    candles = _vcb_true_breakout_1h()
    candles[-1] = _candle(13, "108.4", "111", "107.9", "108.3", volume="180")
    return candles


def _vcb_missing_volume_expansion_1h() -> list[dict[str, Any]]:
    candles = _vcb_true_breakout_1h()
    candles[-1] = _candle(13, "108.4", "111", "108.2", "110", volume="100")
    return candles


def _review_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "| StrategyGroup | Case | Signal | Side | Passed |\n| --- | --- | --- | --- | --- |\n| none | - | - | - | - |"
    output = [
        "| StrategyGroup | Case | Signal | Side | Passed |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        output.append(
            "| `{}` | `{}` | `{}` | `{}` | `{}` |".format(
                row.get("strategy_group_id"),
                row.get("fixture_case"),
                row.get("observed_signal_type"),
                row.get("observed_side"),
                str(row.get("passed")).lower(),
            )
        )
    return "\n".join(output)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OWNER_PROGRESS))
    args = parser.parse_args(argv)

    packet = build_post_revision_replay_review()
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    if args.output_owner_progress:
        owner_path = Path(args.output_owner_progress).expanduser()
        owner_path.parent.mkdir(parents=True, exist_ok=True)
        owner_path.write_text(build_owner_progress_markdown(packet), encoding="utf-8")
    print(payload)
    return 0 if packet["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
