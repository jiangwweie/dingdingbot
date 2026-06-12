#!/usr/bin/env python3
"""Build a local fresh-authorization -> official handoff fixture for RTF-059.

The fixture starts from a ready executable-readiness packet, then proves:

readiness packet
-> blocked official handoff without fresh authorization
-> fresh authorization binding
-> ready official handoff with the fresh authorization
-> disabled-smoke call to the official endpoint

It uses fake API clients for binding and disabled smoke. It never requests a
real gateway action, never places an order, never calls OrderLifecycle, never
calls exchange, and never moves funds.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts import runtime_fresh_submit_authorization_binding_api_flow as binding_flow  # noqa: E402
from scripts import runtime_official_submit_disabled_smoke_from_handoff as disabled_smoke_flow  # noqa: E402
from scripts import runtime_official_submit_handoff_from_readiness as handoff_from_readiness  # noqa: E402
from src.domain.runtime_official_submit_handoff import (  # noqa: E402
    RuntimeOfficialSubmitHandoffMode,
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _paths(root: Path) -> dict[str, Path]:
    return {
        "readiness": root / "00-readiness-ready.json",
        "initial_handoff": root / "01-initial-handoff-needs-fresh-auth.json",
        "binding": root / "02-fresh-authorization-binding.json",
        "final_handoff": root / "03-final-official-handoff.json",
        "disabled_smoke": root / "04-disabled-smoke.json",
    }


def _readiness_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "api_payload": {
            "packet_id": "readiness-rtf059",
            "runtime_instance_id": args.runtime_instance_id,
            "source_strategy_planning_packet_id": "strategy-plan-rtf059",
            "source_authorization_id": "consumed-submit-auth-rtf059",
            "source_release_packet_id": "post-submit-rtf059",
            "strategy_planning_status": "ready_for_final_gate_preflight",
            "signal_evaluation_id": "signal-rtf059",
            "order_candidate_id": "order-candidate-rtf059",
            "status": "ready_for_executable_submit",
            "evidence": {
                "final_gate_preview_id": "final-gate-preview-rtf059",
                "final_gate_passed": True,
                "runtime_grant_authorization_id": args.runtime_grant_authorization_id,
                "trusted_submit_fact_snapshot_id": "trusted-facts-rtf059",
                "submit_idempotency_policy_id": "idem-rtf059",
                "attempt_outcome_policy_id": "attempt-policy-rtf059",
                "protection_creation_failure_policy_id": "protect-policy-rtf059",
                "local_registration_enablement_decision_id": "local-enable-rtf059",
                "exchange_submit_enablement_decision_id": "exchange-enable-rtf059",
                "exchange_submit_action_authorization_id": "exchange-action-auth-rtf059",
                "order_lifecycle_submit_enablement_id": "ol-enable-rtf059",
                "exchange_submit_adapter_enablement_id": "adapter-enable-rtf059",
                "deployment_readiness_evidence_id": "deploy-ready-rtf059",
                "protection_required_and_ready": True,
                "active_position_source_trusted": True,
                "account_facts_fresh": True,
                "duplicate_submit_guard_ready": True,
            },
            "blockers": [],
            "warnings": [],
            "executable_submit_ready": True,
            "requires_official_order_lifecycle_path": True,
            "requires_current_final_gate_pass": True,
            "requires_fresh_strategy_candidate": True,
            "legacy_pre_attempt_rehearsal_required": False,
            "consumed_authorization_replay_only": True,
            "not_exchange_submit_execution": True,
            "not_order_lifecycle_authority": True,
            "execution_intent_created": False,
            "executable_execution_intent_created": False,
            "order_created": False,
            "order_lifecycle_called": False,
            "exchange_called": False,
            "exchange_order_submitted": False,
            "runtime_state_mutated": False,
            "withdrawal_or_transfer_created": False,
            "created_at_ms": 1_781_300_000_000,
            "metadata": {
                "source": "runtime_fresh_authorization_official_handoff_fixture",
                "rtf059": True,
            },
        }
    }


def _build_handoff(
    *,
    readiness_payload: dict[str, Any],
    fresh_submit_authorization_id: str | None,
) -> dict[str, Any]:
    return handoff_from_readiness.build_report(
        readiness_payload=readiness_payload,
        fresh_submit_authorization_id=fresh_submit_authorization_id,
        mode=RuntimeOfficialSubmitHandoffMode.DISABLED_SMOKE,
        owner_confirmed_for_real_submit_action=False,
        now_ms=1_781_300_000_001,
    )


def _binding_args(
    args: argparse.Namespace,
    *,
    handoff_json: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        runtime_instance_id=args.runtime_instance_id,
        handoff_json=str(handoff_json),
        requested_fresh_submit_authorization_id=args.requested_fresh_submit_authorization_id,
        allow_create_from_existing_intent=True,
        allow_create_intent_from_latest_draft=True,
        additional_warning=None,
        additional_blocker=None,
        env_file=None,
        api_base=args.api_base,
    )


def _disabled_smoke_args(
    args: argparse.Namespace,
    *,
    handoff_json: Path,
    output: Path,
) -> argparse.Namespace:
    return argparse.Namespace(
        handoff_json=str(handoff_json),
        output=str(output),
        env_file=None,
        api_base=args.api_base,
    )


class _BindingClient:
    def __init__(self, *, authorization_id: str) -> None:
        self.authorization_id = authorization_id
        self.calls: list[dict[str, Any]] = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            }
        )
        return {
            "http_status": 200,
            "body": {
                "status": "created_intent_and_authorization",
                "blockers": [],
                "warnings": ["rtf059_fixture_binding"],
                "fresh_submit_authorization_id": self.authorization_id,
                "execution_intent_id": "intent-rtf059",
                "runtime_execution_intent_draft_id": "draft-rtf059",
                "ready_for_fresh_authorization_resolution": True,
                "ready_for_disabled_smoke_call": True,
                "binding_source": "latest_ready_draft",
                "creates_execution_intent": True,
                "creates_submit_authorization": True,
            },
        }


class _DisabledSmokeClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request_json(self, method, path, *, query=None, body=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            }
        )
        return {
            "http_status": 200,
            "body": {
                "status": "exchange_submit_execution_disabled",
                "exchange_submit_execution_enabled": False,
                "exchange_submit_execution_mode": "disabled",
                "execution_result_id": "disabled-smoke-rtf059",
            },
        }


def _build_report(args: argparse.Namespace) -> dict[str, Any]:
    artifact_dir = Path(args.artifact_dir).expanduser()
    paths = _paths(artifact_dir)
    readiness = _readiness_payload(args)
    _write_json(paths["readiness"], readiness)

    initial_handoff = _build_handoff(
        readiness_payload=readiness,
        fresh_submit_authorization_id=None,
    )
    _write_json(paths["initial_handoff"], initial_handoff)

    binding_client = _BindingClient(authorization_id=args.fixture_fresh_authorization_id)
    binding = binding_flow._build_report(
        _binding_args(args, handoff_json=paths["initial_handoff"]),
        client=binding_client,
    )
    _write_json(paths["binding"], binding)

    fresh_authorization_id = (
        (binding.get("operator_action_preview") or {}).get(
            "fresh_submit_authorization_id"
        )
        or (binding.get("api_payload") or {}).get("fresh_submit_authorization_id")
    )
    final_handoff = _build_handoff(
        readiness_payload=readiness,
        fresh_submit_authorization_id=fresh_authorization_id,
    )
    _write_json(paths["final_handoff"], final_handoff)

    disabled_client = _DisabledSmokeClient()
    disabled_smoke = disabled_smoke_flow._build_report(
        _disabled_smoke_args(
            args,
            handoff_json=paths["final_handoff"],
            output=paths["disabled_smoke"],
        ),
        client=disabled_client,
    )
    _write_json(paths["disabled_smoke"], disabled_smoke)

    final_handoff_packet = final_handoff.get("packet")
    if not isinstance(final_handoff_packet, dict):
        final_handoff_packet = {}
    status = (
        "ready_fresh_authorization_official_handoff_fixture"
        if binding.get("status")
        in {
            "bound_existing_authorization",
            "created_authorization",
            "created_intent_and_authorization",
        }
        and final_handoff_packet.get("status") == "ready_for_official_submit_call"
        and disabled_smoke.get("status") == "disabled_smoke_passed"
        else "blocked_fresh_authorization_official_handoff_fixture"
    )
    report = {
        "scope": "runtime_fresh_authorization_official_handoff_fixture",
        "status": status,
        "runtime_instance_id": args.runtime_instance_id,
        "artifact_dir": str(artifact_dir),
        "artifact_paths": {key: str(value) for key, value in paths.items()},
        "stage_statuses": {
            "initial_handoff": (initial_handoff.get("packet") or {}).get("status"),
            "binding": binding.get("status"),
            "final_handoff": final_handoff_packet.get("status"),
            "disabled_smoke": disabled_smoke.get("status"),
        },
        "fresh_submit_authorization_id": fresh_authorization_id,
        "initial_handoff": initial_handoff,
        "binding_report": binding,
        "final_handoff": final_handoff,
        "disabled_smoke_report": disabled_smoke,
        "api_call_counts": {
            "binding": len(binding_client.calls),
            "disabled_smoke": len(disabled_client.calls),
        },
        "api_paths": {
            "binding": [call["path"] for call in binding_client.calls],
            "disabled_smoke": [call["path"] for call in disabled_client.calls],
        },
        "blockers": list(binding.get("blockers") or [])
        + list(final_handoff_packet.get("blockers") or [])
        + list(disabled_smoke.get("blockers") or []),
        "warnings": list(binding.get("warnings") or [])
        + list(final_handoff_packet.get("warnings") or [])
        + list(disabled_smoke.get("warnings") or []),
        "safety_invariants": {
            "uses_fake_binding_client": True,
            "uses_fake_disabled_smoke_client": True,
            "does_not_request_real_gateway_action": True,
            "owner_confirmed_for_first_real_submit_action": False,
            "official_submit_endpoint_called_only_disabled_smoke": (
                len(disabled_client.calls) == 1
            ),
            "exchange_submit_execution_enabled": bool(
                disabled_smoke.get("safety_invariants", {}).get(
                    "exchange_submit_execution_enabled"
                )
            ),
            "exchange_write_called": bool(
                disabled_smoke.get("safety_invariants", {}).get(
                    "exchange_write_called"
                )
            ),
            "order_created": bool(
                disabled_smoke.get("safety_invariants", {}).get("order_created")
            ),
            "order_lifecycle_called": bool(
                disabled_smoke.get("safety_invariants", {}).get(
                    "order_lifecycle_called"
                )
            ),
            "runtime_budget_mutated": bool(
                disabled_smoke.get("safety_invariants", {}).get(
                    "runtime_budget_mutated"
                )
            ),
            "withdrawal_or_transfer_created": bool(
                disabled_smoke.get("safety_invariants", {}).get(
                    "withdrawal_or_transfer_created"
                )
            ),
        },
        "created_at_ms": int(time.time() * 1000),
    }
    if args.output:
        _write_json(Path(args.output).expanduser(), report)
    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local RTF-059 fresh authorization official handoff fixture.",
    )
    parser.add_argument("--runtime-instance-id", default="runtime-rtf059")
    parser.add_argument("--runtime-grant-authorization-id", default="grant-rtf059")
    parser.add_argument(
        "--fixture-fresh-authorization-id",
        default="fresh-submit-auth-rtf059",
    )
    parser.add_argument("--requested-fresh-submit-authorization-id")
    parser.add_argument("--api-base", default="http://fixture")
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
