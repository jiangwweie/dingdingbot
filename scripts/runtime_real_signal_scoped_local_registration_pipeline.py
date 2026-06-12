#!/usr/bin/env python3
"""Drive real strategy signal evidence toward scoped local registration."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
import tempfile
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.runtime_first_real_submit_api_flow import (  # noqa: E402
    API_BASE_ENV as FIRST_REAL_SUBMIT_API_BASE_ENV,
    DEFAULT_API_BASE,
    UrlLibApiClient,
    _load_env_file,
)
from scripts import runtime_fresh_submit_authorization_binding_api_flow  # noqa: E402
from scripts import runtime_official_evidence_chain_from_binding  # noqa: E402
from scripts import runtime_official_submit_handoff_api_flow  # noqa: E402
from scripts import runtime_persisted_draft_source_readiness_api_flow  # noqa: E402
from scripts import runtime_real_signal_readiness_evidence_resolver  # noqa: E402
from scripts import runtime_scoped_local_registration_proof_from_evidence  # noqa: E402
from scripts import runtime_strategy_signal_intent_draft_source_api_flow  # noqa: E402


API_BASE_ENV = "RUNTIME_REAL_SIGNAL_SCOPED_LOCAL_REGISTRATION_PIPELINE_API_BASE"


def _api_base(args: argparse.Namespace) -> str:
    import os

    return (
        args.api_base
        or os.environ.get(API_BASE_ENV)
        or os.environ.get(FIRST_REAL_SUBMIT_API_BASE_ENV)
        or DEFAULT_API_BASE
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _status(value: dict[str, Any] | None) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("status") or "")


def _blockers(value: dict[str, Any] | None) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [str(item) for item in value.get("blockers") or []]


def _fresh_id_hint(readiness_report: dict[str, Any]) -> str:
    preview = readiness_report.get("operator_action_preview")
    candidate_id = None
    packet_id = None
    if isinstance(preview, dict):
        candidate_id = preview.get("order_candidate_id")
        packet_id = preview.get("readiness_packet_id")
    payload = readiness_report.get("api_payload")
    if isinstance(payload, dict):
        candidate_id = candidate_id or payload.get("order_candidate_id")
        packet_id = packet_id or payload.get("packet_id")
    raw = str(candidate_id or packet_id or "unknown").strip()
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in raw)
    return f"requested-fresh-submit-authorization-{safe[:160]}"


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
        metadata_json=args.metadata_json,
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
        first_real_submit_packet_json=None,
        additional_warning=["rtf020_real_signal_pipeline"],
        additional_blocker=None,
        env_file=args.env_file,
        api_base=_api_base(args),
    )


def _handoff_args(
    args: argparse.Namespace,
    *,
    readiness_path: Path,
    fresh_submit_authorization_id: str,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        readiness_json=str(readiness_path),
        fresh_submit_authorization_id=fresh_submit_authorization_id,
        mode="disabled_smoke",
        owner_confirmed_for_real_submit_action=False,
        additional_warning=["rtf020_real_signal_pipeline"],
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
        handoff_json=str(handoff_path),
        requested_fresh_submit_authorization_id=None,
        allow_create_from_existing_intent=True,
        allow_create_intent_from_latest_draft=True,
        additional_warning=["rtf020_real_signal_pipeline"],
        additional_blocker=None,
        env_file=args.env_file,
        api_base=_api_base(args),
    )


def _evidence_args(
    args: argparse.Namespace,
    *,
    binding_path: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        binding_json=str(binding_path),
        output=None,
        env_file=args.env_file,
        api_base=_api_base(args),
        skip_evidence_preparation_probe=False,
    )


def _scoped_proof_args(
    args: argparse.Namespace,
    *,
    evidence_path: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        evidence_chain_json=str(evidence_path),
        source_kind="current_live_signal",
        allow_scoped_local_registration_proof=True,
        allow_sample_local_registration=False,
        execute_scoped_local_registration_proof=(
            args.execute_scoped_local_registration_proof
        ),
        api_base=_api_base(args),
        env_file=args.env_file,
        owner_operator_id=args.owner_operator_id,
        owner_confirmation_reference=args.owner_confirmation_reference,
        reason=args.reason,
        outcome_kind=args.outcome_kind,
        skip_next_attempt_gate_check=args.skip_next_attempt_gate_check,
        output=None,
    )


def _readiness_evidence_resolution_args(
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


def _build_report(
    args: argparse.Namespace,
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    _load_env_file(args.env_file)
    api_client = client or UrlLibApiClient(api_base=_api_base(args))
    artifact_root_ctx = (
        tempfile.TemporaryDirectory(prefix="rtf020-real-signal-")
        if not args.artifact_dir
        else None
    )
    artifact_root = Path(args.artifact_dir or artifact_root_ctx.name)
    artifact_root.mkdir(parents=True, exist_ok=True)
    reports: dict[str, dict[str, Any] | None] = {
        "intent_draft_source": None,
        "readiness_evidence_resolution": None,
        "readiness": None,
        "handoff": None,
        "binding": None,
        "evidence_chain": None,
        "scoped_local_registration_proof": None,
    }
    try:
        source = runtime_strategy_signal_intent_draft_source_api_flow._build_report(
            _source_args(args),
            client=api_client,
        )
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

        readiness_evidence_json = args.readiness_evidence_json
        if not readiness_evidence_json and args.auto_readiness_evidence:
            resolution = runtime_real_signal_readiness_evidence_resolver._build_report(
                _readiness_evidence_resolution_args(
                    args,
                    source_path=source_path,
                    artifact_root=artifact_root,
                )
            )
            reports["readiness_evidence_resolution"] = resolution
            _write_json(
                artifact_root / "02-readiness-evidence-resolution.json",
                resolution,
            )
            readiness_evidence_json = resolution.get("evidence_json_path")
            if _status(resolution) != (
                runtime_real_signal_readiness_evidence_resolver.READY_STATUS
            ) or not readiness_evidence_json:
                return _final_report(
                    args,
                    artifact_root=artifact_root,
                    status="blocked_at_readiness_evidence_resolution",
                    blocked_stage="readiness_evidence_resolution",
                    reports=reports,
                )

        if not readiness_evidence_json:
            return _final_report(
                args,
                artifact_root=artifact_root,
                status="blocked_readiness_evidence_required",
                blocked_stage="persisted_draft_source_readiness",
                reports=reports,
                extra_blockers=["readiness_evidence_json_required_after_source_ready"],
            )

        readiness = runtime_persisted_draft_source_readiness_api_flow._build_packet(
            _readiness_args(
                args,
                source_path=source_path,
                evidence_json=str(readiness_evidence_json),
            ),
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

        handoff = runtime_official_submit_handoff_api_flow._build_packet(
            _handoff_args(
                args,
                readiness_path=readiness_path,
                fresh_submit_authorization_id=_fresh_id_hint(readiness),
            ),
            client=api_client,
        )
        reports["handoff"] = handoff
        handoff_path = artifact_root / "04-handoff.json"
        _write_json(handoff_path, handoff)
        if _status(handoff) != "ready_for_official_submit_call":
            return _final_report(
                args,
                artifact_root=artifact_root,
                status="blocked_at_official_submit_handoff",
                blocked_stage="official_submit_handoff",
                reports=reports,
            )

        binding = runtime_fresh_submit_authorization_binding_api_flow._build_report(
            _binding_args(args, handoff_path=handoff_path),
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

        evidence = runtime_official_evidence_chain_from_binding._build_report(
            _evidence_args(args, binding_path=binding_path),
            client=api_client,
        )
        reports["evidence_chain"] = evidence
        evidence_path = artifact_root / "06-evidence-chain.json"
        _write_json(evidence_path, evidence)
        if _status(evidence) not in {
            "prepared_machine_evidence_blocked_before_local_order_adapter",
            "official_evidence_chain_ready",
        }:
            return _final_report(
                args,
                artifact_root=artifact_root,
                status="blocked_at_official_evidence_chain",
                blocked_stage="official_evidence_chain",
                reports=reports,
            )

        scoped = runtime_scoped_local_registration_proof_from_evidence._build_report(
            _scoped_proof_args(args, evidence_path=evidence_path),
            client=api_client,
        )
        reports["scoped_local_registration_proof"] = scoped
        _write_json(artifact_root / "07-scoped-local-registration-proof.json", scoped)
        scoped_status = _status(scoped)
        final_status = (
            "ready_for_real_signal_scoped_local_registration_proof"
            if scoped_status == "ready_for_scoped_local_registration_proof_dry_run"
            else scoped_status
            if scoped_status == "scoped_local_registration_proof_recorded"
            else "blocked_at_scoped_local_registration_proof"
        )
        return _final_report(
            args,
            artifact_root=artifact_root,
            status=final_status,
            blocked_stage=(
                None
                if final_status.startswith(("ready_", "scoped_"))
                else "scoped_local_registration_proof"
            ),
            reports=reports,
        )
    finally:
        if artifact_root_ctx is not None:
            artifact_root_ctx.cleanup()


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
    for name in (
        "intent_draft_source",
        "readiness_evidence_resolution",
        "readiness",
        "handoff",
        "binding",
        "evidence_chain",
        "scoped_local_registration_proof",
    ):
        report = reports.get(name)
        blockers.extend(f"{name}:{item}" for item in _blockers(report))
        warnings.extend(
            f"{name}:{item}"
            for item in (
                report.get("warnings") if isinstance(report, dict) else []
            )
            or []
        )
    result = {
        "scope": "runtime_real_signal_scoped_local_registration_pipeline",
        "status": status,
        "blocked_stage": blocked_stage,
        "runtime_instance_id": args.runtime_instance_id,
        "artifact_dir": str(artifact_root),
        "stage_statuses": {
            key: _status(value)
            for key, value in reports.items()
            if isinstance(value, dict)
        },
        "reports": reports,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "safety_invariants": _safety(reports),
    }
    if args.output:
        _write_json(Path(args.output).expanduser(), result)
    return result


def _safety(reports: dict[str, dict[str, Any] | None]) -> dict[str, bool]:
    scoped = reports.get("scoped_local_registration_proof") or {}
    scoped_safety = (
        scoped.get("safety_invariants") if isinstance(scoped, dict) else {}
    )
    return {
        "uses_official_trading_console_api": True,
        "real_signal_input_required": True,
        "sample_rehearsal_used": False,
        "non_executing_until_scoped_local_registration": True,
        "local_registration_attempted": bool(
            isinstance(scoped_safety, dict)
            and scoped_safety.get("local_registration_attempted") is True
        ),
        "local_registration_recorded": bool(
            isinstance(scoped_safety, dict)
            and scoped_safety.get("local_registration_recorded") is True
        ),
        "exchange_arm_enabled": False,
        "exchange_write_called": False,
        "execute_real_submit": False,
        "first_real_submit_action_called": False,
        "post_submit_accounting_called": False,
        "withdrawal_or_transfer_created": False,
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
            "Run the real StrategySignal -> scoped local registration proof "
            "pipeline without sample rehearsal fallback."
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
    parser.add_argument("--candidate-id")
    parser.add_argument("--context-id")
    parser.add_argument("--expires-at-ms", type=int)
    parser.add_argument("--active-positions-count", type=int)
    parser.add_argument("--metadata-json")
    parser.add_argument("--execute-scoped-local-registration-proof", action="store_true")
    parser.add_argument("--owner-operator-id", default="owner")
    parser.add_argument(
        "--owner-confirmation-reference",
        default="owner-authorized-real-signal-scoped-local-registration",
    )
    parser.add_argument(
        "--reason",
        default="owner authorized real signal scoped local registration proof",
    )
    parser.add_argument(
        "--outcome-kind",
        default="entry_filled_protection_creation_failed",
    )
    parser.add_argument("--skip-next-attempt-gate-check", action="store_true")
    parser.add_argument("--env-file")
    parser.add_argument("--api-base")
    parser.add_argument("--artifact-dir")
    parser.add_argument("--output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    with redirect_stdout(sys.stderr):
        report = _build_report(args)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if report["status"].startswith(("ready_", "blocked_", "scoped_")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
