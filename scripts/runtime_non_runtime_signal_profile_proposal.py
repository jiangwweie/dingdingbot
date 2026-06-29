#!/usr/bin/env python3
"""Build a non-executing runtime profile proposal from a non-runtime signal.

RTF-035 consumes the RTF-034 selector output when live market has a
``would_enter`` signal that does not match the current runtime. It translates
that signal into an ``ExperimentalRuntimeProfileProposal`` for Owner/Codex
review without creating a runtime, mutating any profile, creating candidates,
creating ExecutionIntents, placing orders, calling OrderLifecycle, or writing
to exchange.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.experimental_runtime_profile_proposal import (  # noqa: E402
    ExperimentalRuntimeProfileProposalStatus,
    build_experimental_runtime_profile_proposal,
)


READY_STATUS = "ready_for_owner_runtime_profile_decision"
BLOCKED_STATUS = "blocked_no_non_runtime_would_enter_signal"


def _load_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _non_runtime_would_enter(selector_artifact: dict[str, Any], index: int) -> dict[str, Any] | None:
    signals = selector_artifact.get("non_runtime_would_enter_signals") or []
    if not isinstance(signals, list) or not signals:
        return None
    if index < 0 or index >= len(signals):
        raise ValueError("--signal-index outside non_runtime_would_enter_signals")
    signal = signals[index]
    if not isinstance(signal, dict):
        raise ValueError("selected non-runtime signal must be an object")
    return signal


def _signal_field(signal: dict[str, Any], *names: str) -> str:
    for name in names:
        value = signal.get(name)
        if isinstance(value, str) and value:
            return value
    raise ValueError(f"non-runtime signal missing required field: {'/'.join(names)}")


def _safety_invariants() -> dict[str, bool]:
    return {
        "selector_replay_only": True,
        "database_write": False,
        "runtime_profile_mutated": False,
        "runtime_created": False,
        "runtime_enabled": False,
        "signal_evaluation_created": False,
        "order_candidate_created": False,
        "execution_intent_created": False,
        "executable_execution_intent_created": False,
        "order_created": False,
        "order_lifecycle_called": False,
        "exchange_write_called": False,
        "attempt_counter_mutated": False,
        "runtime_budget_mutated": False,
        "position_opened": False,
        "position_closed": False,
        "withdrawal_or_transfer_created": False,
    }


def _operator_next_step(status: str) -> str:
    if status == READY_STATUS:
        return "owner_codex_review_runtime_profile_proposal_before_runtime_creation"
    return "run_live_selector_until_non_runtime_would_enter_available"


def build_profile_proposal_artifact(
    *,
    selector_artifact: dict[str, Any],
    capital_base: Decimal,
    signal_index: int = 0,
) -> dict[str, Any]:
    signal = _non_runtime_would_enter(selector_artifact, signal_index)
    if signal is None:
        return {
            "scope": "runtime_non_runtime_signal_profile_proposal",
            "status": BLOCKED_STATUS,
            "source_selector_status": selector_artifact.get("status"),
            "source_selector_blockers": list(selector_artifact.get("blockers") or []),
            "selected_non_runtime_signal": None,
            "experimental_runtime_profile_proposal": None,
            "blockers": ["non_runtime_would_enter_signal_missing"],
            "warnings": [],
            "profile_proposal_plan": {
                "next_step": _operator_next_step(BLOCKED_STATUS),
                "creates_runtime": False,
                "mutates_runtime_profile": False,
                "creates_execution_intent": False,
                "places_order": False,
                "calls_order_lifecycle": False,
            },
            "safety_invariants": _safety_invariants(),
        }

    strategy_family_id = _signal_field(signal, "strategy_family_id", "strategy_group_id")
    strategy_family_version_id = _signal_field(signal, "strategy_family_version_id")
    symbol = _signal_field(signal, "symbol")
    side = _signal_field(signal, "side").lower()
    proposal = build_experimental_runtime_profile_proposal(
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        symbol=symbol,
        side=side,
        capital_base=capital_base,
    )
    proposal_json = proposal.model_dump(mode="json")
    ready = (
        proposal.status
        == ExperimentalRuntimeProfileProposalStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    )
    blockers = list(proposal.blockers)
    if not ready and not blockers:
        blockers.append("experimental_runtime_profile_proposal_not_ready")

    return {
        "scope": "runtime_non_runtime_signal_profile_proposal",
        "status": READY_STATUS if ready else "blocked_profile_proposal_not_ready",
        "source_selector_status": selector_artifact.get("status"),
        "source_selector_blockers": list(selector_artifact.get("blockers") or []),
        "selected_non_runtime_signal": signal,
        "experimental_runtime_profile_proposal": proposal_json,
        "runtime_boundary_preview": proposal.boundary.model_dump(mode="json"),
        "owner_confirmation_keys": list(proposal.owner_confirmation_keys),
        "blockers": blockers,
        "warnings": [
            *list(proposal.warnings),
            "proposal_is_not_runtime_creation",
            "proposal_is_not_execution_authority",
            "owner_must_confirm_runtime_profile_before_use",
        ],
        "profile_proposal_plan": {
            "next_step": _operator_next_step(READY_STATUS if ready else "blocked"),
            "creates_runtime": False,
            "mutates_runtime_profile": False,
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "requires_owner_runtime_profile_confirmation": ready,
            "requires_trial_binding_before_runtime_creation": ready,
            "requires_post_creation_full_cycle_probe": ready,
        },
        "safety_invariants": _safety_invariants(),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a non-executing runtime profile proposal from RTF-034 selector output.",
    )
    parser.add_argument("--selector-json", required=True)
    parser.add_argument("--capital-base", default="30")
    parser.add_argument("--signal-index", type=int, default=0)
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    artifact = build_profile_proposal_artifact(
        selector_artifact=_load_json(args.selector_json),
        capital_base=Decimal(str(args.capital_base)),
        signal_index=args.signal_index,
    )
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if artifact["status"] == READY_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
