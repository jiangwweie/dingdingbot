#!/usr/bin/env python3
"""Build a local runtime post-submit finalize dry-run packet from JSON facts."""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.runtime_execution_exchange_submit_execution_result import (  # noqa: E402
    RuntimeExecutionExchangeSubmitExecutionResult,
)
from src.domain.runtime_execution_post_submit_budget_settlement import (  # noqa: E402
    RuntimeExecutionPostSubmitBudgetSettlement,
)
from src.domain.runtime_execution_submit_outcome_review import (  # noqa: E402
    RuntimeExecutionSubmitOutcomeReview,
)
from src.domain.runtime_post_submit_finalize import (  # noqa: E402
    build_runtime_post_submit_finalize_packet,
)
from src.domain.strategy_runtime import StrategyRuntimeInstance  # noqa: E402


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="python"))
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _load_payload(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError("fixture root must be a JSON object")
    return payload


def build_packet_from_fixture(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = (
        StrategyRuntimeInstance.model_validate(payload["runtime"])
        if payload.get("runtime") is not None
        else None
    )
    result = (
        RuntimeExecutionExchangeSubmitExecutionResult.model_validate(
            payload["exchange_submit_execution_result"]
        )
        if payload.get("exchange_submit_execution_result") is not None
        else None
    )
    review = (
        RuntimeExecutionSubmitOutcomeReview.model_validate(
            payload["submit_outcome_review"]
        )
        if payload.get("submit_outcome_review") is not None
        else None
    )
    settlement = (
        RuntimeExecutionPostSubmitBudgetSettlement.model_validate(
            payload["post_submit_budget_settlement"]
        )
        if payload.get("post_submit_budget_settlement") is not None
        else None
    )
    packet = build_runtime_post_submit_finalize_packet(
        authorization_id=str(payload["authorization_id"]),
        runtime=runtime,
        exchange_submit_execution_result=result,
        submit_outcome_review=review,
        post_submit_budget_settlement=settlement,
        active_positions_count=payload.get("active_positions_count"),
        closed_review_required=bool(payload.get("closed_review_required", False)),
        protection_blockers=[
            str(item) for item in payload.get("protection_blockers", [])
        ],
        now_ms=int(payload.get("now_ms", 0)),
    )
    return _json_value(packet)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a non-executing runtime post-submit finalize packet.",
    )
    parser.add_argument("--fixture", required=True)
    args = parser.parse_args()
    packet = build_packet_from_fixture(_load_payload(args.fixture))
    print(json.dumps(packet, ensure_ascii=False, indent=2))
    return 0 if packet["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
