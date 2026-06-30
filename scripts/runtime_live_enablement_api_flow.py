#!/usr/bin/env python3
"""Guarded API flow for live StrategyRuntimeInstance enablement.

The default mode is inspect-only: collect the current runtime view and the
official live-enablement preview. It does not mutate runtime state, create
ExecutionIntent records, create orders, call OrderLifecycle, call exchange, or
move funds.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any, Protocol

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    DEFAULT_API_BASE,
    UrlLibApiClient,
    _load_env_file,
)


APPLY_CONFIRMATION_PHRASE = "OWNER_APPROVES_RUNTIME_LIVE_ENABLEMENT_MUTATION"


class ApiClient(Protocol):
    def request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _load_env_file(args.env_file)
    client = UrlLibApiClient(api_base=args.api_base)
    artifact = build_runtime_live_enablement_api_flow_artifact(
        client=client,
        runtime_instance_id=args.runtime_instance_id,
        query=_query_from_args(args),
        apply_mutation=args.apply_mutation,
        confirmation_phrase=args.confirmation_phrase,
        owner_live_runtime_enablement_authorization_id=(
            args.owner_live_runtime_enablement_authorization_id
        ),
        owner_real_submit_authorization_id=args.owner_real_submit_authorization_id,
        actor=args.actor,
    )
    if args.json:
        print(json.dumps(artifact, indent=2, sort_keys=True))
    else:
        _print_human(artifact)
    return 0 if not artifact["checks"]["blockers"] else 2


def build_runtime_live_enablement_api_flow_artifact(
    *,
    client: ApiClient,
    runtime_instance_id: str,
    query: dict[str, Any],
    apply_mutation: bool = False,
    confirmation_phrase: str | None = None,
    owner_live_runtime_enablement_authorization_id: str | None = None,
    owner_real_submit_authorization_id: str | None = None,
    actor: str = "owner",
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    blockers: list[str] = []
    warnings: list[str] = []

    runtime_response = _step(
        client,
        steps,
        "get_strategy_runtime",
        "GET",
        f"/api/trading-console/strategy-runtimes/{runtime_instance_id}",
    )
    runtime_body = _body(runtime_response)
    if runtime_response.get("http_status") != 200:
        blockers.append("runtime_view_unavailable")

    preview_response = _step(
        client,
        steps,
        "get_live_enablement_preview",
        "GET",
        (
            "/api/trading-console/strategy-runtimes/"
            f"{runtime_instance_id}/live-enablement-preview"
        ),
        query=query,
    )
    preview_body = _body(preview_response)
    if preview_response.get("http_status") != 200:
        blockers.append("live_enablement_preview_unavailable")

    preview_status = str(preview_body.get("status") or "")
    preview_blockers = list(preview_body.get("blockers") or [])
    preview_warnings = list(preview_body.get("warnings") or [])
    blockers.extend(f"preview_{item}" for item in preview_blockers)
    warnings.extend(f"preview_{item}" for item in preview_warnings)
    preview_ready = (
        preview_status == "ready_for_live_runtime_enablement_mutation_design"
    )

    mutation_response: dict[str, Any] | None = None
    mutation_body: dict[str, Any] = {}
    mutation_applied = False
    if apply_mutation:
        if confirmation_phrase != APPLY_CONFIRMATION_PHRASE:
            blockers.append("apply_confirmation_phrase_missing_or_invalid")
        if not preview_ready:
            blockers.append("preview_not_ready_for_apply")
        if not owner_live_runtime_enablement_authorization_id:
            blockers.append("owner_live_runtime_enablement_authorization_id_missing")
        if not owner_real_submit_authorization_id:
            blockers.append("owner_real_submit_authorization_id_missing")
        if not blockers:
            mutation_response = _step(
                client,
                steps,
                "apply_live_enablement_mutation",
                "POST",
                (
                    "/api/trading-console/strategy-runtimes/"
                    f"{runtime_instance_id}/live-enablement-mutations"
                ),
                body={
                    "preview": preview_body,
                    "owner_live_runtime_enablement_authorization_id": (
                        owner_live_runtime_enablement_authorization_id
                    ),
                    "owner_real_submit_authorization_id": (
                        owner_real_submit_authorization_id
                    ),
                    "actor": actor,
                },
            )
            mutation_body = _body(mutation_response)
            if mutation_response.get("http_status") != 200:
                blockers.append("live_enablement_mutation_http_not_ok")
            mutation_applied = mutation_body.get("status") == "applied"
            if not mutation_applied:
                blockers.append("live_enablement_mutation_not_applied")

    status = "blocked_before_live_runtime_enablement_preview"
    if preview_ready and not apply_mutation:
        status = "ready_for_live_runtime_enablement_mutation_review"
    elif preview_ready and mutation_applied:
        status = "live_runtime_enablement_mutation_applied"
    elif apply_mutation:
        status = "blocked_before_live_runtime_enablement_mutation"

    artifact = {
        "status": status,
        "scope": "runtime_live_enablement_api_flow",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_instance_id": runtime_instance_id,
        "checks": {
            "preview_ready": preview_ready,
            "apply_requested": apply_mutation,
            "mutation_applied": mutation_applied,
            "blockers": _dedupe(blockers),
            "warnings": _dedupe(warnings),
        },
        "query": dict(query),
        "runtime_view": runtime_body,
        "live_enablement_preview": preview_body,
        "mutation_result": mutation_body if mutation_response is not None else None,
        "steps": steps,
        "safety_invariants": {
            "execution_intent_created": False,
            "order_created": False,
            "exchange_called": False,
            "owner_bounded_execution_called": False,
            "order_lifecycle_called": False,
            "withdrawal_instruction_created": False,
            "transfer_instruction_created": False,
            "runtime_state_mutated": mutation_applied,
        },
    }
    return artifact


def _step(
    client: ApiClient,
    steps: list[dict[str, Any]],
    name: str,
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.request_json(method, path, query=query, body=body)
    body_value = _body(response)
    steps.append(
        {
            "name": name,
            "method": method,
            "path": path,
            "http_status": response.get("http_status"),
            "status": body_value.get("status"),
            "blockers": list(body_value.get("blockers") or []),
            "warnings": list(body_value.get("warnings") or []),
        }
    )
    return response


def _body(response: dict[str, Any]) -> dict[str, Any]:
    body = response.get("body")
    return body if isinstance(body, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _query_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return _clean_query(
        {
        "strategy_family_confirmed": args.strategy_family_confirmed,
        "implementation_source_confirmed": args.implementation_source_confirmed,
        "required_facts_confirmed": args.required_facts_confirmed,
        "entry_policy_confirmed": args.entry_policy_confirmed,
        "exit_policy_confirmed": args.exit_policy_confirmed,
        "protection_policy_confirmed": args.protection_policy_confirmed,
        "eligible_for_runtime_execution_confirmed": (
            args.eligible_for_runtime_execution_confirmed
        ),
        "right_tail_review_metrics_confirmed": (
            args.right_tail_review_metrics_confirmed
        ),
        "runtime_profile_confirmed": args.runtime_profile_confirmed,
        "owner_confirmation_mode_confirmed": args.owner_confirmation_mode_confirmed,
        "symbol_side_boundary_confirmed": args.symbol_side_boundary_confirmed,
        "max_loss_budget_confirmed": args.max_loss_budget_confirmed,
        "max_notional_boundary_confirmed": args.max_notional_boundary_confirmed,
        "max_active_positions_boundary_confirmed": (
            args.max_active_positions_boundary_confirmed
        ),
        "max_leverage_boundary_confirmed": args.max_leverage_boundary_confirmed,
        "margin_usage_boundary_confirmed": args.margin_usage_boundary_confirmed,
        "liquidation_buffer_boundary_confirmed": (
            args.liquidation_buffer_boundary_confirmed
        ),
        "protection_readiness_source_confirmed": (
            args.protection_readiness_source_confirmed
        ),
        "stale_fact_behavior_confirmed": args.stale_fact_behavior_confirmed,
        "attempt_consumption_rule_confirmed": (
            args.attempt_consumption_rule_confirmed
        ),
        "budget_reservation_rule_confirmed": (
            args.budget_reservation_rule_confirmed
        ),
        "trusted_active_position_source_confirmed": (
            args.trusted_active_position_source_confirmed
        ),
        "trusted_account_fact_source_confirmed": (
            args.trusted_account_fact_source_confirmed
        ),
        "short_side_conservative_profile_confirmed": (
            args.short_side_conservative_profile_confirmed
        ),
        "budget_release_or_consume_rule_confirmed": (
            args.budget_release_or_consume_rule_confirmed
        ),
        "post_submit_budget_settlement_persistence_evidence_id": (
            args.post_submit_budget_settlement_persistence_evidence_id
        ),
        "attempt_outcome_policy_id": args.attempt_outcome_policy_id,
        "protection_creation_failure_policy_confirmed": (
            args.protection_creation_failure_policy_confirmed
        ),
        "protection_creation_failure_policy_id": (
            args.protection_creation_failure_policy_id
        ),
        "duplicate_submit_policy_confirmed": args.duplicate_submit_policy_confirmed,
        "submit_idempotency_policy_id": args.submit_idempotency_policy_id,
        "trusted_submit_fact_snapshot_id": args.trusted_submit_fact_snapshot_id,
        "local_registration_enablement_decision_id": (
            args.local_registration_enablement_decision_id
        ),
        "exchange_submit_enablement_decision_id": (
            args.exchange_submit_enablement_decision_id
        ),
        "exchange_submit_execution_result_id": (
            args.exchange_submit_execution_result_id
        ),
        "runtime_submit_rehearsal_id": args.runtime_submit_rehearsal_id,
        "deployment_readiness_evidence_id": args.deployment_readiness_evidence_id,
        "owner_real_submit_authorization_id": args.owner_real_submit_authorization_id,
        "deployment_readiness_confirmed": args.deployment_readiness_confirmed,
        "explicit_owner_real_submit_authorization": (
            args.explicit_owner_real_submit_authorization
        ),
        "current_head_deployed": args.current_head_deployed,
        "owner_live_runtime_enablement_authorized": (
            args.owner_live_runtime_enablement_authorized
        ),
        "owner_real_submit_authorization_present": (
            args.owner_real_submit_authorization_present
        ),
        "submit_technical_rehearsal_passed": args.submit_technical_rehearsal_passed,
        "submit_adapter_implemented": args.submit_adapter_implemented,
        "staged_submit_chain_available": args.staged_submit_chain_available,
        "forbidden_execution_flags": args.forbidden_execution_flags,
        }
    )


def _clean_query(query: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in query.items():
        if isinstance(value, str):
            text = value.strip()
            cleaned[key] = text or None
        elif isinstance(value, list):
            cleaned[key] = [item for item in value if str(item).strip()]
        else:
            cleaned[key] = value
    return cleaned


def _add_confirmation_flags(parser: argparse.ArgumentParser) -> None:
    names = [
        "strategy-family-confirmed",
        "implementation-source-confirmed",
        "required-facts-confirmed",
        "entry-policy-confirmed",
        "exit-policy-confirmed",
        "protection-policy-confirmed",
        "eligible-for-runtime-execution-confirmed",
        "right-tail-review-metrics-confirmed",
        "runtime-profile-confirmed",
        "owner-confirmation-mode-confirmed",
        "symbol-side-boundary-confirmed",
        "max-loss-budget-confirmed",
        "max-notional-boundary-confirmed",
        "max-active-positions-boundary-confirmed",
        "max-leverage-boundary-confirmed",
        "margin-usage-boundary-confirmed",
        "liquidation-buffer-boundary-confirmed",
        "protection-readiness-source-confirmed",
        "stale-fact-behavior-confirmed",
        "attempt-consumption-rule-confirmed",
        "budget-reservation-rule-confirmed",
        "trusted-active-position-source-confirmed",
        "trusted-account-fact-source-confirmed",
        "short-side-conservative-profile-confirmed",
        "budget-release-or-consume-rule-confirmed",
        "protection-creation-failure-policy-confirmed",
        "duplicate-submit-policy-confirmed",
        "deployment-readiness-confirmed",
        "explicit-owner-real-submit-authorization",
        "current-head-deployed",
        "owner-live-runtime-enablement-authorized",
        "owner-real-submit-authorization-present",
        "submit-technical-rehearsal-passed",
        "submit-adapter-implemented",
        "staged-submit-chain-available",
    ]
    for name in names:
        parser.add_argument(f"--{name}", action="store_true")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build or apply a guarded live runtime enablement API artifact.",
    )
    parser.add_argument("--api-base", default=os.environ.get("RUNTIME_LIVE_ENABLEMENT_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--env-file")
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--post-submit-budget-settlement-persistence-evidence-id")
    parser.add_argument("--attempt-outcome-policy-id")
    parser.add_argument("--protection-creation-failure-policy-id")
    parser.add_argument("--submit-idempotency-policy-id")
    parser.add_argument("--trusted-submit-fact-snapshot-id")
    parser.add_argument("--local-registration-enablement-decision-id")
    parser.add_argument("--exchange-submit-enablement-decision-id")
    parser.add_argument("--exchange-submit-execution-result-id")
    parser.add_argument("--runtime-submit-rehearsal-id")
    parser.add_argument("--deployment-readiness-evidence-id")
    parser.add_argument("--owner-real-submit-authorization-id")
    parser.add_argument("--forbidden-execution-flags", action="append", default=[])
    parser.add_argument("--apply-mutation", action="store_true")
    parser.add_argument("--confirmation-phrase")
    parser.add_argument("--owner-live-runtime-enablement-authorization-id")
    parser.add_argument("--actor", default="owner")
    parser.add_argument("--json", action="store_true")
    _add_confirmation_flags(parser)
    return parser.parse_args(argv)


def _print_human(artifact: dict[str, Any]) -> None:
    checks = artifact["checks"]
    print(f"status={artifact['status']}")
    print(f"runtime_instance_id={artifact['runtime_instance_id']}")
    print(f"preview_ready={str(checks['preview_ready']).lower()}")
    print(f"apply_requested={str(checks['apply_requested']).lower()}")
    print(f"mutation_applied={str(checks['mutation_applied']).lower()}")
    if checks["blockers"]:
        print("blockers=" + ",".join(checks["blockers"]))
    if checks["warnings"]:
        print("warnings=" + ",".join(checks["warnings"]))


if __name__ == "__main__":
    raise SystemExit(main())
