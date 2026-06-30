#!/usr/bin/env python3
"""Route live strategy signals into the next runtime planning action.

RTF-065 keeps the execution chain moving without faking readiness:

live strategy shelf selector
-> current runtime signal prepare route, or
-> non-runtime would-enter profile proposal, or
-> wait / no-signal diagnostic route

The script is read-only. It does not create runtimes, shadow candidates,
ExecutionIntents, orders, OrderLifecycle handoffs, exchange writes, positions,
withdrawals, transfers, or budget mutations.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
import json
from decimal import Decimal
from pathlib import Path
import sys
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_live_strategy_signal_selector as selector_script  # noqa: E402
from scripts import runtime_non_runtime_signal_profile_proposal as proposal_script  # noqa: E402


SelectorBuilder = Callable[[argparse.Namespace], Any]

READY_CURRENT_RUNTIME_STATUS = "ready_for_current_runtime_signal_prepare"
READY_PROFILE_STATUS = "ready_for_owner_runtime_profile_decision"
WAITING_STATUS = "waiting_for_runtime_compatible_signal"


def build_routing_artifact(
    *,
    selector_artifact: dict[str, Any],
    capital_base: Decimal,
    signal_index: int = 0,
) -> dict[str, Any]:
    selector_status = str(selector_artifact.get("status") or "")
    profile_proposal_artifact: dict[str, Any] | None = None

    if selector_status == "runtime_compatible_would_enter_selected":
        status = READY_CURRENT_RUNTIME_STATUS
        blockers: list[str] = []
        next_step = "run_runtime_next_attempt_prepare_after_operator_review"
    elif selector_status == "would_enter_available_but_not_runtime_compatible":
        profile_proposal_artifact = proposal_script.build_profile_proposal_artifact(
            selector_artifact=selector_artifact,
            capital_base=capital_base,
            signal_index=signal_index,
        )
        if profile_proposal_artifact.get("status") == READY_PROFILE_STATUS:
            status = READY_PROFILE_STATUS
            blockers = []
            next_step = "owner_codex_review_runtime_profile_proposal_before_runtime_creation"
        else:
            status = "blocked_non_runtime_profile_proposal"
            blockers = list(profile_proposal_artifact.get("blockers") or [])
            next_step = "resolve_non_runtime_profile_proposal_blocker"
    else:
        status = WAITING_STATUS
        blockers = list(selector_artifact.get("blockers") or [])
        next_step = "continue_live_signal_observation_without_forcing_entry"

    signal_input_json = selector_artifact.get("output_signal_input_json")
    return {
        "scope": "runtime_live_signal_routing_artifact",
        "status": status,
        "source_selector_status": selector_status,
        "runtime_instance_id": selector_artifact.get("runtime_instance_id"),
        "runtime_profile": selector_artifact.get("runtime_profile"),
        "selected_signal": selector_artifact.get("selected_signal"),
        "non_runtime_would_enter_signals": list(
            selector_artifact.get("non_runtime_would_enter_signals") or []
        ),
        "runtime_current_signal": selector_artifact.get("runtime_current_signal"),
        "signal_input_json": signal_input_json,
        "profile_proposal_artifact": profile_proposal_artifact,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(
            [
                *list(selector_artifact.get("warnings") or []),
                "routing_artifact_is_not_execution_authority",
                "unproven_alpha_is_not_semantic_admission_blocker",
            ]
        ),
        "signal_routing_plan": {
            "next_step": next_step,
            "signal_input_json": signal_input_json,
            "current_runtime_prepare_allowed": status == READY_CURRENT_RUNTIME_STATUS,
            "requires_owner_runtime_profile_confirmation": status == READY_PROFILE_STATUS,
            "creates_runtime": False,
            "mutates_runtime_profile": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_real_submit_gate": False,
        },
        "right_tail_objective_context": {
            "small_bounded_losses_allowed_after_runtime_gate": True,
            "forcing_entry_without_signal_forbidden": True,
            "automatic_compounding_assumed": False,
            "automatic_withdrawal_assumed": False,
        },
        "safety_invariants": _safety_invariants(
            selector_artifact=selector_artifact,
            profile_proposal_artifact=profile_proposal_artifact,
        ),
    }


async def _build_artifact(
    args: argparse.Namespace,
    *,
    selector_builder: SelectorBuilder | None = None,
) -> dict[str, Any]:
    builder = selector_builder or selector_script._build_artifact
    selector_args = argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        env_file=args.env_file,
        source=args.source,
        output_signal_input_json=args.output_signal_input_json,
        output_json=None,
    )
    selector_artifact = await builder(selector_args)
    return build_routing_artifact(
        selector_artifact=selector_artifact,
        capital_base=Decimal(str(args.capital_base)),
        signal_index=args.signal_index,
    )


def _safety_invariants(
    *,
    selector_artifact: dict[str, Any],
    profile_proposal_artifact: dict[str, Any] | None,
) -> dict[str, bool]:
    selector_safety = _as_dict(selector_artifact.get("safety_invariants"))
    proposal_safety = (
        _as_dict(profile_proposal_artifact.get("safety_invariants"))
        if isinstance(profile_proposal_artifact, dict)
        else {}
    )

    def forbidden(name: str) -> bool:
        return bool(selector_safety.get(name) or proposal_safety.get(name))

    return {
        "read_only_signal_routing": True,
        "uses_live_strategy_signal_selector": True,
        "uses_profile_proposal_only_when_non_runtime_signal_available": (
            profile_proposal_artifact is not None
        ),
        "database_write": forbidden("database_write"),
        "runtime_profile_mutated": forbidden("runtime_profile_mutated"),
        "runtime_created": forbidden("runtime_created"),
        "runtime_enabled": forbidden("runtime_enabled"),
        "signal_evaluation_created": forbidden("signal_evaluation_created"),
        "order_candidate_created": forbidden("order_candidate_created"),
        "execution_intent_created": forbidden("execution_intent_created"),
        "executable_execution_intent_created": forbidden(
            "executable_execution_intent_created"
        ),
        "order_created": forbidden("order_created"),
        "order_lifecycle_called": forbidden("order_lifecycle_called"),
        "exchange_write_called": forbidden("exchange_write_called"),
        "attempt_counter_mutated": forbidden("attempt_counter_mutated"),
        "runtime_budget_mutated": forbidden("runtime_budget_mutated"),
        "position_opened": forbidden("position_opened"),
        "position_closed": forbidden("position_closed"),
        "withdrawal_or_transfer_created": forbidden("withdrawal_or_transfer_created"),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a read-only runtime live-signal routing artifact.",
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--env-file")
    parser.add_argument(
        "--source",
        choices=["sample", "local_sqlite_read_only", "live_market"],
        default="live_market",
    )
    parser.add_argument("--output-signal-input-json")
    parser.add_argument("--capital-base", default="30")
    parser.add_argument("--signal-index", type=int, default=0)
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def _main(
    argv: list[str] | None = None,
    *,
    selector_builder: SelectorBuilder | None = None,
) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        artifact = asyncio.run(_build_artifact(args, selector_builder=selector_builder))
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if artifact["status"] in {
        READY_CURRENT_RUNTIME_STATUS,
        READY_PROFILE_STATUS,
        WAITING_STATUS,
    } else 2


def main(argv: list[str] | None = None) -> int:
    return _main(argv)


def main_with_selector_for_test(selector_builder: SelectorBuilder) -> int:
    return _main(selector_builder=selector_builder)


if __name__ == "__main__":
    raise SystemExit(main())
