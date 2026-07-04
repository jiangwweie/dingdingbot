#!/usr/bin/env python3
"""Drive a current runtime-compatible signal to disabled-smoke submit proof.

RTF-061 replaces historical RTF-015 sample handoff replay with a current
runtime-compatible persisted source:

strategy signal
-> persisted shadow SignalEvaluation / OrderCandidate / intent draft source
-> executable readiness
-> blocked initial handoff without fresh authorization
-> fresh authorization binding
-> final handoff using the fresh authorization
-> official disabled-smoke endpoint call

The pipeline may create the non-executing persisted source records and the
fresh submit authorization needed for auditability. It does not request a real
gateway action, submit an exchange order, call OrderLifecycle, open/close a
position, or move funds.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_early_readiness_fact_collector as fact_collector  # noqa: E402
from scripts import runtime_fresh_submit_authorization_binding_api_flow as binding_flow  # noqa: E402
from scripts import runtime_official_submit_disabled_smoke_from_handoff as disabled_smoke_flow  # noqa: E402
from scripts import runtime_official_submit_handoff_from_readiness as handoff_from_readiness  # noqa: E402
from scripts import runtime_persisted_draft_source_readiness_api_flow as readiness_flow  # noqa: E402
from scripts import runtime_real_signal_readiness_evidence_resolver as evidence_resolver  # noqa: E402
from scripts import runtime_strategy_signal_intent_draft_source_api_flow as source_flow  # noqa: E402
from scripts.runtime_first_real_submit_api_flow import DEFAULT_API_BASE  # noqa: E402
from src.domain.runtime_official_submit_handoff import RuntimeOfficialSubmitHandoffMode  # noqa: E402


API_BASE_ENV = "RUNTIME_CURRENT_PERSISTED_SOURCE_DISABLED_SMOKE_API_BASE"

READY_STATUS = "ready_current_persisted_source_disabled_smoke"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _status(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return ""
    return str(report.get("status") or "")


def _blockers(report: dict[str, Any] | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    return [str(item) for item in report.get("blockers") or []]


def _warnings(report: dict[str, Any] | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    return [str(item) for item in report.get("warnings") or []]


def _api_base(args: argparse.Namespace) -> str:
    import os

    return args.api_base or os.environ.get(API_BASE_ENV) or DEFAULT_API_BASE


def _source_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        signal_input_json=args.signal_input_json,
        env_file=args.env_file,
        api_base=_api_base(args),
        candidate_id=args.candidate_id,
        context_id=args.context_id,
        expires_at_ms=args.expires_at_ms,
        active_positions_count=args.active_positions_count,
        allow_live_runtime_handoff_prepare=False,
        metadata_json=args.metadata_json,
    )


def _collector_args(
    args: argparse.Namespace,
    *,
    artifact_root: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        runtime_grant_authorization_id=args.runtime_grant_authorization_id,
        owner_real_submit_authorization_id=args.owner_real_submit_authorization_id,
        final_gate_preview_json=args.final_gate_preview_json,
        trusted_submit_facts_json=args.trusted_submit_facts_json,
        submit_idempotency_json=args.submit_idempotency_json,
        attempt_outcome_policy_json=args.attempt_outcome_policy_json,
        protection_failure_policy_json=args.protection_failure_policy_json,
        local_registration_enablement_json=args.local_registration_enablement_json,
        exchange_submit_enablement_json=args.exchange_submit_enablement_json,
        exchange_action_authorization_json=args.exchange_action_authorization_json,
        order_lifecycle_submit_enablement_json=(
            args.order_lifecycle_submit_enablement_json
        ),
        exchange_adapter_enablement_json=args.exchange_adapter_enablement_json,
        deployment_readiness_json=args.deployment_readiness_json,
        legacy_runtime_submit_rehearsal_id=args.legacy_runtime_submit_rehearsal_id,
        durable_exchange_submit_execution_result_id=(
            args.durable_exchange_submit_execution_result_id
        ),
        artifact_dir=str(artifact_root),
        output=None,
    )


def _resolver_args(
    args: argparse.Namespace,
    *,
    source_path: Path,
    artifact_root: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        intent_draft_source_json=str(source_path),
        artifact_dir=str(artifact_root),
        output=None,
        final_gate_preview_id=args.final_gate_preview_id,
        final_gate_passed=args.final_gate_passed,
        runtime_grant_authorization_id=args.runtime_grant_authorization_id,
        owner_real_submit_authorization_id=args.owner_real_submit_authorization_id,
        trusted_submit_fact_snapshot_id=args.trusted_submit_fact_snapshot_id,
        submit_idempotency_policy_id=args.submit_idempotency_policy_id,
        attempt_outcome_policy_id=args.attempt_outcome_policy_id,
        protection_creation_failure_policy_id=(
            args.protection_creation_failure_policy_id
        ),
        local_registration_enablement_decision_id=(
            args.local_registration_enablement_decision_id
        ),
        exchange_submit_enablement_decision_id=(
            args.exchange_submit_enablement_decision_id
        ),
        exchange_submit_action_authorization_id=(
            args.exchange_submit_action_authorization_id
        ),
        order_lifecycle_submit_enablement_id=(
            args.order_lifecycle_submit_enablement_id
        ),
        exchange_submit_adapter_enablement_id=(
            args.exchange_submit_adapter_enablement_id
        ),
        deployment_readiness_evidence_id=args.deployment_readiness_evidence_id,
        protection_required_and_ready=args.protection_required_and_ready,
        active_position_source_trusted=args.active_position_source_trusted,
        account_facts_fresh=args.account_facts_fresh,
        duplicate_submit_guard_ready=args.duplicate_submit_guard_ready,
        legacy_runtime_submit_rehearsal_id=args.legacy_runtime_submit_rehearsal_id,
        durable_exchange_submit_execution_result_id=(
            args.durable_exchange_submit_execution_result_id
        ),
    )


def _readiness_args(
    args: argparse.Namespace,
    *,
    source_path: Path,
    evidence_json: str,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        intent_draft_source_json=str(source_path),
        evidence_json=evidence_json,
        first_real_submit_evidence_json=None,
        additional_warning=["rtf061_current_persisted_source_disabled_smoke"],
        additional_blocker=None,
        env_file=args.env_file,
        api_base=_api_base(args),
    )


def _binding_args(
    args: argparse.Namespace,
    *,
    handoff_path: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        handoff_artifact_json=str(handoff_path),
        requested_fresh_submit_authorization_id=(
            args.requested_fresh_submit_authorization_id
        ),
        allow_create_from_existing_intent=True,
        allow_create_intent_from_latest_draft=True,
        additional_warning=["rtf061_current_persisted_source_disabled_smoke"],
        additional_blocker=None,
        env_file=args.env_file,
        api_base=_api_base(args),
    )


def _disabled_smoke_args(
    args: argparse.Namespace,
    *,
    handoff_path: Path,
    output_path: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        handoff_artifact_json=str(handoff_path),
        output=str(output_path),
        env_file=args.env_file,
        api_base=_api_base(args),
    )


def _has_report_fact_inputs(args: argparse.Namespace) -> bool:
    return any(
        bool(getattr(args, name, None))
        for name in (
            "final_gate_preview_json",
            "trusted_submit_facts_json",
            "submit_idempotency_json",
            "attempt_outcome_policy_json",
            "protection_failure_policy_json",
            "local_registration_enablement_json",
            "exchange_submit_enablement_json",
            "exchange_action_authorization_json",
            "order_lifecycle_submit_enablement_json",
            "exchange_adapter_enablement_json",
            "deployment_readiness_json",
        )
    )


def _fresh_submit_authorization_id(binding: dict[str, Any]) -> str | None:
    preview = binding.get("operator_action_preview")
    if isinstance(preview, dict):
        value = preview.get("fresh_submit_authorization_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    payload = binding.get("api_payload")
    if isinstance(payload, dict):
        value = payload.get("fresh_submit_authorization_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _build_handoff(
    *,
    readiness: dict[str, Any],
    fresh_submit_authorization_id: str | None,
) -> dict[str, Any]:
    return handoff_from_readiness.build_report(
        readiness_payload=readiness,
        fresh_submit_authorization_id=fresh_submit_authorization_id,
        mode=RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE,
        owner_confirmed_for_real_submit_action=False,
    )


def _build_report(
    args: argparse.Namespace,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    artifact_root = Path(args.artifact_dir).expanduser()
    artifact_root.mkdir(parents=True, exist_ok=True)
    api_client = client or source_flow.UrlLibApiClient(api_base=_api_base(args))
    reports: dict[str, dict[str, Any] | None] = {
        "intent_draft_source": None,
        "early_readiness_fact_collection": None,
        "readiness_evidence_resolution": None,
        "readiness": None,
        "initial_handoff": None,
        "binding": None,
        "final_handoff": None,
        "disabled_smoke": None,
    }

    source = source_flow._build_report(_source_args(args), client=api_client)
    reports["intent_draft_source"] = source
    source_path = artifact_root / "01-intent-draft-source.json"
    _write_json(source_path, source)
    if _status(source) != "persisted_ready_intent_draft":
        return _final_report(
            args,
            artifact_root=artifact_root,
            status="blocked_at_strategy_signal_intent_draft_source",
            blocked_stage="strategy_signal_intent_draft_source",
            reports=reports,
        )

    evidence_json = args.readiness_evidence_json
    if not evidence_json and args.auto_readiness_evidence and _has_report_fact_inputs(args):
        collection = fact_collector._build_report(
            _collector_args(args, artifact_root=artifact_root)
        )
        reports["early_readiness_fact_collection"] = collection
        _write_json(artifact_root / "02-early-readiness-fact-collection.json", collection)
        evidence_json = collection.get("evidence_json_path")
        if _status(collection) != fact_collector.READY_STATUS or not evidence_json:
            return _final_report(
                args,
                artifact_root=artifact_root,
                status="blocked_at_early_readiness_fact_collection",
                blocked_stage="early_readiness_fact_collection",
                reports=reports,
            )

    if not evidence_json and args.auto_readiness_evidence:
        resolution = evidence_resolver._build_report(
            _resolver_args(args, source_path=source_path, artifact_root=artifact_root)
        )
        reports["readiness_evidence_resolution"] = resolution
        _write_json(artifact_root / "02-readiness-evidence-resolution.json", resolution)
        evidence_json = resolution.get("evidence_json_path")
        if _status(resolution) != evidence_resolver.READY_STATUS or not evidence_json:
            return _final_report(
                args,
                artifact_root=artifact_root,
                status="blocked_at_readiness_evidence_resolution",
                blocked_stage="readiness_evidence_resolution",
                reports=reports,
            )

    if not evidence_json:
        return _final_report(
            args,
            artifact_root=artifact_root,
            status="blocked_readiness_evidence_required",
            blocked_stage="persisted_draft_source_readiness",
            reports=reports,
            extra_blockers=["readiness_evidence_json_required_after_source_ready"],
        )

    readiness = readiness_flow._build_artifact(
        _readiness_args(args, source_path=source_path, evidence_json=str(evidence_json)),
        client=api_client,
    )
    reports["readiness"] = readiness
    readiness_path = artifact_root / "03-readiness.json"
    _write_json(readiness_path, readiness)
    if _status(readiness) != "ready_for_executable_submit":
        return _final_report(
            args,
            artifact_root=artifact_root,
            status="blocked_at_persisted_draft_source_readiness",
            blocked_stage="persisted_draft_source_readiness",
            reports=reports,
        )

    initial_handoff = _build_handoff(
        readiness=readiness,
        fresh_submit_authorization_id=None,
    )
    reports["initial_handoff"] = initial_handoff
    initial_handoff_path = artifact_root / "04-initial-handoff-needs-fresh-auth.json"
    _write_json(initial_handoff_path, initial_handoff)

    binding = binding_flow._build_report(
        _binding_args(args, handoff_path=initial_handoff_path),
        client=api_client,
    )
    reports["binding"] = binding
    binding_path = artifact_root / "05-binding.json"
    _write_json(binding_path, binding)
    if _status(binding) not in {
        "bound_existing_authorization",
        "created_authorization",
        "created_intent_and_authorization",
    }:
        return _final_report(
            args,
            artifact_root=artifact_root,
            status="blocked_at_fresh_submit_authorization_binding",
            blocked_stage="fresh_submit_authorization_binding",
            reports=reports,
        )

    fresh_authorization_id = _fresh_submit_authorization_id(binding)
    final_handoff = _build_handoff(
        readiness=readiness,
        fresh_submit_authorization_id=fresh_authorization_id,
    )
    reports["final_handoff"] = final_handoff
    final_handoff_path = artifact_root / "06-final-handoff.json"
    _write_json(final_handoff_path, final_handoff)
    final_handoff_artifact = _handoff_artifact(final_handoff)
    if _status(final_handoff_artifact) != (
        "ready_for_official_submit_call"
    ):
        return _final_report(
            args,
            artifact_root=artifact_root,
            status="blocked_at_final_official_submit_handoff",
            blocked_stage="final_official_submit_handoff",
            reports=reports,
        )

    disabled_smoke = disabled_smoke_flow._build_report(
        _disabled_smoke_args(
            args,
            handoff_path=final_handoff_path,
            output_path=artifact_root / "07-disabled-smoke.json",
        ),
        client=api_client,
    )
    reports["disabled_smoke"] = disabled_smoke
    _write_json(artifact_root / "07-disabled-smoke.json", disabled_smoke)
    status = (
        READY_STATUS
        if _status(disabled_smoke) == "disabled_smoke_passed"
        else "blocked_at_disabled_smoke"
    )
    return _final_report(
        args,
        artifact_root=artifact_root,
        status=status,
        blocked_stage=None if status == READY_STATUS else "disabled_smoke",
        reports=reports,
    )


def _final_report(
    args: argparse.Namespace,
    *,
    artifact_root: Path,
    status: str,
    blocked_stage: str | None,
    reports: dict[str, dict[str, Any] | None],
    extra_blockers: list[str] | None = None,
) -> dict[str, Any]:
    blockers = list(extra_blockers or [])
    warnings: list[str] = []
    for name, report in reports.items():
        blockers.extend(f"{name}:{item}" for item in _blockers(report))
        warnings.extend(f"{name}:{item}" for item in _warnings(report))
    result = {
        "scope": "runtime_current_persisted_source_disabled_smoke_pipeline",
        "status": status,
        "blocked_stage": blocked_stage,
        "runtime_instance_id": args.runtime_instance_id,
        "artifact_dir": str(artifact_root),
        "stage_statuses": {
            key: _report_status(value) for key, value in reports.items()
            if isinstance(value, dict)
        },
        "fresh_submit_authorization_id": _fresh_submit_authorization_id(
            reports.get("binding") or {}
        ),
        "reports": reports,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "safety_invariants": _safety(reports),
    }
    if args.output:
        _write_json(Path(args.output).expanduser(), result)
    return result


def _report_status(report: dict[str, Any]) -> str:
    if "handoff_artifact" in report and isinstance(
        report.get("handoff_artifact"), dict
    ):
        return _status(report["handoff_artifact"])
    return _status(report)


def _handoff_artifact(report: dict[str, Any]) -> dict[str, Any]:
    artifact = report.get("handoff_artifact")
    if isinstance(artifact, dict):
        return artifact
    return {}


def _safety(reports: dict[str, dict[str, Any] | None]) -> dict[str, bool]:
    source = reports.get("intent_draft_source") or {}
    binding = reports.get("binding") or {}
    disabled = reports.get("disabled_smoke") or {}
    disabled_safety = (
        disabled.get("safety_invariants") if isinstance(disabled, dict) else {}
    )
    return {
        "uses_current_runtime_persisted_source": True,
        "uses_historical_rtf015_sample_handoff": False,
        "uses_official_trading_console_api": True,
        "non_executing_until_disabled_smoke": True,
        "signal_evaluation_created": bool(
            source.get("safety_invariants", {}).get("signal_evaluation_created")
        ),
        "order_candidate_created": bool(
            source.get("safety_invariants", {}).get("order_candidate_created")
        ),
        "runtime_execution_intent_draft_created": bool(
            source.get("safety_invariants", {}).get(
                "runtime_execution_intent_draft_created"
            )
        ),
        "execution_intent_created": bool(
            binding.get("safety_invariants", {}).get("creates_execution_intent")
        ),
        "submit_authorization_created": bool(
            binding.get("safety_invariants", {}).get("creates_submit_authorization")
        ),
        "calls_official_submit_endpoint": bool(
            isinstance(disabled_safety, dict)
            and disabled_safety.get("calls_official_submit_endpoint") is True
        ),
        "requests_real_gateway_action": bool(
            isinstance(disabled_safety, dict)
            and disabled_safety.get("requests_real_gateway_action") is True
        ),
        "owner_confirmed_for_first_real_submit_action": bool(
            isinstance(disabled_safety, dict)
            and disabled_safety.get("owner_confirmed_for_first_real_submit_action")
            is True
        ),
        "exchange_submit_execution_enabled": bool(
            isinstance(disabled_safety, dict)
            and disabled_safety.get("exchange_submit_execution_enabled") is True
        ),
        "exchange_write_called": bool(
            isinstance(disabled_safety, dict)
            and disabled_safety.get("exchange_write_called") is True
        ),
        "order_created": bool(
            isinstance(disabled_safety, dict)
            and disabled_safety.get("order_created") is True
        ),
        "order_lifecycle_called": bool(
            isinstance(disabled_safety, dict)
            and disabled_safety.get("order_lifecycle_called") is True
        ),
        "runtime_budget_mutated": bool(
            isinstance(disabled_safety, dict)
            and disabled_safety.get("runtime_budget_mutated") is True
        ),
        "withdrawal_or_transfer_created": bool(
            isinstance(disabled_safety, dict)
            and disabled_safety.get("withdrawal_or_transfer_created") is True
        ),
    }


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
        description=(
            "Run current persisted source -> fresh authorization -> disabled "
            "smoke without historical sample handoff replay."
        ),
    )
    parser.add_argument("--runtime-instance-id", required=True)
    parser.add_argument("--signal-input-json", required=True)
    parser.add_argument("--readiness-evidence-json")
    parser.add_argument("--auto-readiness-evidence", action="store_true")
    parser.add_argument("--final-gate-preview-id")
    parser.add_argument("--final-gate-passed", action="store_true")
    parser.add_argument("--runtime-grant-authorization-id")
    parser.add_argument("--owner-real-submit-authorization-id")
    parser.add_argument("--trusted-submit-fact-snapshot-id")
    parser.add_argument("--submit-idempotency-policy-id")
    parser.add_argument("--attempt-outcome-policy-id")
    parser.add_argument("--protection-creation-failure-policy-id")
    parser.add_argument("--local-registration-enablement-decision-id")
    parser.add_argument("--exchange-submit-enablement-decision-id")
    parser.add_argument("--exchange-submit-action-authorization-id")
    parser.add_argument("--order-lifecycle-submit-enablement-id")
    parser.add_argument("--exchange-submit-adapter-enablement-id")
    parser.add_argument("--deployment-readiness-evidence-id")
    parser.add_argument("--protection-required-and-ready", action="store_true")
    parser.add_argument("--active-position-source-trusted", action="store_true")
    parser.add_argument("--account-facts-fresh", action="store_true")
    parser.add_argument("--duplicate-submit-guard-ready", action="store_true")
    parser.add_argument("--legacy-runtime-submit-rehearsal-id")
    parser.add_argument("--durable-exchange-submit-execution-result-id")
    parser.add_argument("--final-gate-preview-json")
    parser.add_argument("--trusted-submit-facts-json")
    parser.add_argument("--submit-idempotency-json")
    parser.add_argument("--attempt-outcome-policy-json")
    parser.add_argument("--protection-failure-policy-json")
    parser.add_argument("--local-registration-enablement-json")
    parser.add_argument("--exchange-submit-enablement-json")
    parser.add_argument("--exchange-action-authorization-json")
    parser.add_argument("--order-lifecycle-submit-enablement-json")
    parser.add_argument("--exchange-adapter-enablement-json")
    parser.add_argument("--deployment-readiness-json")
    parser.add_argument("--requested-fresh-submit-authorization-id")
    parser.add_argument("--candidate-id")
    parser.add_argument("--context-id")
    parser.add_argument("--expires-at-ms", type=int)
    parser.add_argument("--active-positions-count", type=int)
    parser.add_argument("--metadata-json")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        report = _build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"].startswith(("ready_", "blocked_")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
