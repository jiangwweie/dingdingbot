#!/usr/bin/env python3
"""Build a non-mutating runtime profile decision packet from RTF-035 output.

RTF-036 freezes an ``ExperimentalRuntimeProfileProposal`` into an
Owner/Codex-confirmable promotion record template. The script does not post to
the API, write PG, create a StrategyRuntimeInstance, create candidates or
intents, call OrderLifecycle, or touch exchange.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.strategy_runtime_promotion_gate_service import (  # noqa: E402
    StrategyRuntimePromotionGateService,
)
from src.domain.experimental_runtime_profile_proposal import (  # noqa: E402
    ExperimentalRuntimeProfileProposal,
    ExperimentalRuntimeProfileProposalStatus,
)
from src.domain.strategy_runtime_promotion_gate import (  # noqa: E402
    FirstRealSubmitConfirmationFacts,
    RuntimeExecutionConfirmationFacts,
    StrategyRuntimePromotionGateConfirmationRecord,
    StrategyRuntimePromotionGateStatus,
    StrategySemanticsConfirmationFacts,
)


READY_STATUS = "ready_for_owner_codex_runtime_profile_confirmation"
BLOCKED_STATUS = "blocked_runtime_profile_decision_packet"


def _load_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _slug(value: str, *, max_length: int = 96) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    text = re.sub(r"-+", "-", text).strip("-").lower()
    return (text or "runtime-profile")[:max_length].strip("-")


def _proposal_from_packet(packet: dict[str, Any]) -> ExperimentalRuntimeProfileProposal | None:
    raw = packet.get("experimental_runtime_profile_proposal")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("experimental_runtime_profile_proposal must be an object")
    proposal = ExperimentalRuntimeProfileProposal.model_validate(raw)
    keys = list(proposal.owner_confirmation_keys)
    if (
        proposal.side.lower() == "short"
        or proposal.profile_kind.value == "small_capital_conservative_short"
    ) and "short_side_conservative_profile_confirmed" not in keys:
        keys.append("short_side_conservative_profile_confirmed")
        proposal = proposal.model_copy(update={"owner_confirmation_keys": keys})
    return proposal


def _semantic_confirmations() -> StrategySemanticsConfirmationFacts:
    return StrategySemanticsConfirmationFacts(
        strategy_family_confirmed=True,
        implementation_source_confirmed=True,
        required_facts_confirmed=True,
        entry_policy_confirmed=True,
        exit_policy_confirmed=True,
        protection_policy_confirmed=True,
        eligible_for_runtime_execution_confirmed=True,
        right_tail_review_metrics_confirmed=True,
    )


def _runtime_confirmations(
    proposal: ExperimentalRuntimeProfileProposal,
) -> RuntimeExecutionConfirmationFacts:
    return RuntimeExecutionConfirmationFacts(
        runtime_profile_confirmed=True,
        owner_confirmation_mode_confirmed=True,
        symbol_side_boundary_confirmed=True,
        max_loss_budget_confirmed=True,
        max_notional_boundary_confirmed=True,
        max_active_positions_boundary_confirmed=True,
        max_leverage_boundary_confirmed=True,
        margin_usage_boundary_confirmed=True,
        liquidation_buffer_boundary_confirmed=True,
        protection_readiness_source_confirmed=True,
        stale_fact_behavior_confirmed=True,
        attempt_consumption_rule_confirmed=True,
        budget_reservation_rule_confirmed=True,
        trusted_active_position_source_confirmed=True,
        trusted_account_fact_source_confirmed=True,
        short_side_conservative_profile_confirmed=(
            proposal.side.lower() == "short"
            or proposal.profile_kind.value == "small_capital_conservative_short"
        ),
    )


def _safety_invariants() -> dict[str, bool]:
    return {
        "proposal_replay_only": True,
        "database_write": False,
        "promotion_confirmation_record_created": False,
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


def _blocked_packet(
    *,
    source_packet: dict[str, Any],
    blockers: list[str],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "scope": "runtime_profile_decision_packet",
        "status": BLOCKED_STATUS,
        "source_status": source_packet.get("status"),
        "proposal_id": None,
        "promotion_gate_preview": None,
        "promotion_confirmation_request_template": None,
        "runtime_draft_request_template": None,
        "checks": {
            "ready_for_owner_codex_runtime_profile_confirmation": False,
            "blockers": sorted(set(blockers)),
        },
        "blockers": sorted(set(blockers)),
        "warnings": list(warnings or []),
        "safety_invariants": _safety_invariants(),
    }


def build_packet(
    *,
    proposal_packet: dict[str, Any],
    confirmation_id: str | None = None,
    runtime_instance_id: str | None = None,
    trial_binding_id: str | None = None,
    evidence_refs: list[str] | None = None,
    created_at_ms: int | None = None,
) -> dict[str, Any]:
    proposal = _proposal_from_packet(proposal_packet)
    if proposal is None:
        return _blocked_packet(
            source_packet=proposal_packet,
            blockers=["runtime_profile_proposal_missing"],
        )
    blockers: list[str] = []
    warnings = [
        *list(proposal_packet.get("warnings") or []),
        "decision_packet_is_not_owner_confirmation_record",
        "decision_packet_is_not_runtime_creation",
        "decision_packet_is_not_execution_authority",
    ]
    if proposal_packet.get("status") != "ready_for_owner_runtime_profile_decision":
        blockers.append("source_profile_packet_not_ready")
    if (
        proposal.status
        != ExperimentalRuntimeProfileProposalStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
    ):
        blockers.append("runtime_profile_proposal_not_ready")
    if proposal.blockers:
        blockers.extend(proposal.blockers)
    if (
        not proposal.not_execution_authority
        or proposal.creates_runtime
        or proposal.creates_execution_intent
        or proposal.order_created
        or proposal.exchange_called
    ):
        blockers.append("runtime_profile_proposal_contains_action_authority")
    if blockers:
        return _blocked_packet(
            source_packet=proposal_packet,
            blockers=blockers,
            warnings=warnings,
        )

    slug = _slug(
        f"{proposal.strategy_family_id}-{proposal.strategy_family_version_id}-"
        f"{proposal.symbol}-{proposal.side}"
    )
    created_at_ms = created_at_ms or int(time.time() * 1000)
    confirmation_id = confirmation_id or f"promotion-confirmation-{slug}"
    runtime_instance_id = runtime_instance_id or f"strategy-runtime-{slug}"
    evidence_refs = evidence_refs or [
        f"runtime-profile-proposal://{proposal.proposal_id}",
    ]
    record = StrategyRuntimePromotionGateConfirmationRecord(
        confirmation_id=confirmation_id,
        runtime_instance_id=runtime_instance_id,
        strategy_family_id=proposal.strategy_family_id,
        strategy_family_version_id=proposal.strategy_family_version_id,
        semantic_confirmations=_semantic_confirmations(),
        runtime_confirmations=_runtime_confirmations(proposal),
        first_real_submit_confirmations=FirstRealSubmitConfirmationFacts(),
        runtime_profile_proposal_snapshot=proposal,
        reason=(
            "Owner/Codex confirms bounded small-capital runtime profile proposal "
            "for strategy-runtime draft creation review."
        ),
        evidence_refs=evidence_refs,
        created_at_ms=created_at_ms,
        metadata={
            "source": "rtf036_runtime_profile_decision_packet",
            "proposal_packet_status": proposal_packet.get("status"),
            "selected_signal_candidate_id": (
                proposal_packet.get("selected_non_runtime_signal") or {}
            ).get("candidate_id"),
            "approval_not_recorded_by_this_packet": True,
            "runtime_creation_requires_api_submit_after_owner_confirmation": True,
            "non_executing_record_template": True,
        },
    )
    record = StrategyRuntimePromotionGateService().with_result_snapshot(record)
    gate = record.promotion_gate_result_snapshot
    gate_ready = (
        gate is not None
        and gate.status
        == StrategyRuntimePromotionGateStatus.READY_FOR_CONTROLLED_RUNTIME_EXECUTION_DESIGN
    )
    ready = gate_ready and not record.runtime_mutation_created
    confirmation_payload = {
        "confirmation_id": record.confirmation_id,
        "runtime_instance_id": record.runtime_instance_id,
        "strategy_family_id": record.strategy_family_id,
        "strategy_family_version_id": record.strategy_family_version_id,
        "scope": record.scope.value,
        "semantic_confirmations": record.semantic_confirmations.model_dump(mode="json"),
        "runtime_confirmations": record.runtime_confirmations.model_dump(mode="json"),
        "first_real_submit_confirmations": (
            record.first_real_submit_confirmations.model_dump(mode="json")
        ),
        "runtime_profile_proposal_snapshot": proposal.model_dump(mode="json"),
        "reason": record.reason,
        "evidence_refs": list(record.evidence_refs),
        "created_at_ms": record.created_at_ms,
        "metadata": dict(record.metadata),
    }
    return {
        "scope": "runtime_profile_decision_packet",
        "status": READY_STATUS if ready else BLOCKED_STATUS,
        "source_status": proposal_packet.get("status"),
        "proposal_id": proposal.proposal_id,
        "strategy_family_id": proposal.strategy_family_id,
        "strategy_family_version_id": proposal.strategy_family_version_id,
        "symbol": proposal.symbol,
        "side": proposal.side,
        "runtime_instance_id": runtime_instance_id,
        "trial_binding_id_required": True,
        "trial_binding_id": trial_binding_id,
        "owner_confirmation_keys": list(proposal.owner_confirmation_keys),
        "promotion_gate_preview": gate.model_dump(mode="json") if gate else None,
        "promotion_confirmation_request_template": confirmation_payload,
        "runtime_draft_request_template": {
            "api_path": (
                "/api/brc/strategy-runtime-promotion-confirmations/"
                f"{record.confirmation_id}/runtime-drafts"
            ),
            "method": "POST",
            "body": {
                "trial_binding_id": trial_binding_id or "<required_trial_binding_id>",
                "carrier_id": None,
                "expires_at_ms": None,
                "metadata": {
                    "source": "rtf036_runtime_profile_decision_packet",
                    "proposal_id": proposal.proposal_id,
                    "requires_post_creation_full_cycle_probe": True,
                },
            },
            "ready_to_submit": trial_binding_id is not None,
            "creates_runtime_draft_only": True,
            "execution_enabled": False,
            "shadow_mode": True,
        },
        "operator_command_plan": {
            "next_step": "owner_codex_submit_promotion_confirmation_then_create_shadow_runtime_draft",
            "requires_owner_runtime_profile_confirmation": True,
            "requires_trial_binding_before_runtime_creation": True,
            "creates_runtime_when_api_template_is_submitted": False,
            "this_packet_creates_runtime": False,
            "this_packet_places_order": False,
            "post_creation_full_cycle_probe_required": True,
        },
        "checks": {
            "ready_for_owner_codex_runtime_profile_confirmation": ready,
            "promotion_gate_ready_for_controlled_runtime_execution_design": gate_ready,
            "runtime_profile_proposal_attached": True,
            "short_side_conservative_profile_confirmed_in_template": (
                record.runtime_confirmations.short_side_conservative_profile_confirmed
            ),
            "trial_binding_id_supplied": trial_binding_id is not None,
            "blockers": [] if ready else ["promotion_gate_preview_not_ready"],
        },
        "blockers": [] if ready else ["promotion_gate_preview_not_ready"],
        "warnings": warnings,
        "safety_invariants": _safety_invariants(),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build RTF-036 runtime profile decision packet from RTF-035 proposal output.",
    )
    parser.add_argument("--proposal-json", required=True)
    parser.add_argument("--confirmation-id")
    parser.add_argument("--runtime-instance-id")
    parser.add_argument("--trial-binding-id")
    parser.add_argument("--evidence-ref", action="append", default=[])
    parser.add_argument("--created-at-ms", type=int)
    parser.add_argument("--output-json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    packet = build_packet(
        proposal_packet=_load_json(args.proposal_json),
        confirmation_id=args.confirmation_id,
        runtime_instance_id=args.runtime_instance_id,
        trial_binding_id=args.trial_binding_id,
        evidence_refs=args.evidence_ref or None,
        created_at_ms=args.created_at_ms,
    )
    payload = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if packet["status"] == READY_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
