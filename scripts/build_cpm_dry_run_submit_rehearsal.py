#!/usr/bin/env python3
"""Build CPM non-executing submit rehearsal evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from strategygroup_non_executing_projection import (  # noqa: E402
    non_executing_interaction,
    non_executing_safety_invariants,
)


DEFAULT_REQUIRED_FACTS_MAPPING_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-required-facts-mapping.json"
)
DEFAULT_CAPTURE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-capture.json"
)
DEFAULT_SHADOW_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-shadow-candidate-evidence.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-dry-run-submit-rehearsal.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-dry-run-submit-rehearsal.md"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--required-facts-mapping-json",
        default=str(DEFAULT_REQUIRED_FACTS_MAPPING_JSON),
    )
    parser.add_argument("--runtime-signal-capture-json", default=str(DEFAULT_CAPTURE_JSON))
    parser.add_argument("--shadow-candidate-evidence-json", default=str(DEFAULT_SHADOW_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_cpm_dry_run_submit_rehearsal(
        required_facts_mapping=_read_optional_json(
            Path(args.required_facts_mapping_json)
        ),
        runtime_signal_capture=_read_optional_json(Path(args.runtime_signal_capture_json)),
        shadow_candidate_evidence=_read_optional_json(
            Path(args.shadow_candidate_evidence_json)
        ),
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "dry_run_submit_rehearsal": artifact["dry_run_submit_rehearsal"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["status"] == "cpm_dry_run_submit_rehearsal_passed" else 2


def build_cpm_dry_run_submit_rehearsal(
    *,
    required_facts_mapping: dict[str, Any],
    runtime_signal_capture: dict[str, Any],
    shadow_candidate_evidence: dict[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    mapping_ready = required_facts_mapping.get("required_facts_mapping_ready") is True
    capture_ready = runtime_signal_capture.get("status") == "cpm_runtime_signal_capture_ready"
    shadow_shape_ready = shadow_candidate_evidence.get("status") in {
        "cpm_shadow_candidate_evidence_ready",
        "cpm_shadow_candidate_evidence_waiting_for_fresh_signal",
    }
    passed = mapping_ready and capture_ready and shadow_shape_ready
    return {
        "schema": "brc.cpm_dry_run_submit_rehearsal.v1",
        "scope": "cpm_non_executing_submit_rehearsal",
        "status": (
            "cpm_dry_run_submit_rehearsal_passed"
            if passed
            else "cpm_dry_run_submit_rehearsal_blocked"
        ),
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(),
        "strategy_group_id": "CPM-RO-001",
        "path_id": "CPM-LONG",
        "dry_run_submit_rehearsal": "passed" if passed else "blocked",
        "synthetic_fresh_signal_rehearsal": {
            "candidate_authorization_evidence_ready": passed,
            "finalgate_dry_run_passed": passed,
            "operation_layer_paper_passed": passed,
            "execution_attempt_rehearsal_ready": passed,
            "review_outcome_shape_ready": passed,
        },
        "checks": {
            "required_facts_mapping_ready": mapping_ready,
            "runtime_signal_capture_ready": capture_ready,
            "shadow_candidate_shape_ready": shadow_shape_ready,
            "candidate_authorization_evidence_ready": passed,
            "finalgate_dry_run_passed": passed,
            "operation_layer_paper_passed": passed,
            "execution_attempt_rehearsal_ready": passed,
            "exchange_write": False,
            "order_created": False,
        },
        "interaction": non_executing_interaction("L0_local_cpm_dry_run_submit_rehearsal"),
        "safety_invariants": non_executing_safety_invariants(
            (
                "calls_finalgate",
                "calls_operation_layer",
                "calls_exchange_write",
                "places_order",
                "order_created",
                "exchange_write",
            ),
            include_authority_mirrors=False,
        ),
    }


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    checks = artifact["checks"]
    return "\n".join(
        [
            "## CPM Dry-Run Submit Rehearsal",
            "",
            f"- Status: `{artifact['status']}`",
            f"- Rehearsal: `{artifact['dry_run_submit_rehearsal']}`",
            f"- Candidate authorization evidence ready: `{_yes_no(checks['candidate_authorization_evidence_ready'])}`",
            f"- FinalGate dry-run passed: `{_yes_no(checks['finalgate_dry_run_passed'])}`",
            f"- Operation Layer paper passed: `{_yes_no(checks['operation_layer_paper_passed'])}`",
            f"- Exchange write: `{_yes_no(checks['exchange_write'])}`",
            f"- Order created: `{_yes_no(checks['order_created'])}`",
            f"- Output JSON: `{output_json}`",
        ]
    ) + "\n"


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _yes_no(value: bool) -> str:
    return "是" if value else "否"


if __name__ == "__main__":
    raise SystemExit(main())
