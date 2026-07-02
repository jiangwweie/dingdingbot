#!/usr/bin/env python3
"""Build CPM shadow candidate evidence read model."""

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


DEFAULT_CAPTURE_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-runtime-signal-capture.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-shadow-candidate-evidence.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "output/runtime-monitor/latest-cpm-shadow-candidate-evidence.md"
)

READY_STATUS = "cpm_shadow_candidate_evidence_ready"
WAITING_STATUS = "cpm_shadow_candidate_evidence_waiting_for_fresh_signal"
BLOCKED_STATUS = "cpm_shadow_candidate_evidence_blocked"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-signal-capture-json", default=str(DEFAULT_CAPTURE_JSON))
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-owner-progress", default=str(DEFAULT_OUTPUT_MD))
    args = parser.parse_args(argv)

    artifact = build_cpm_shadow_candidate_evidence(
        runtime_signal_capture=_read_optional_json(Path(args.runtime_signal_capture_json))
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_owner_progress)
    _write_json(output_json, artifact)
    _write_text(output_md, _markdown(artifact, output_json))
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "shadow_candidate_evidence_ready": artifact[
                    "shadow_candidate_evidence_ready"
                ],
                "first_blocker": artifact["first_blocker"]["class"],
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if artifact["status"] in {READY_STATUS, WAITING_STATUS} else 2


def build_cpm_shadow_candidate_evidence(
    *, runtime_signal_capture: dict[str, Any], generated_at_utc: str | None = None
) -> dict[str, Any]:
    generated = generated_at_utc or datetime.now(timezone.utc).isoformat()
    capture_ready = runtime_signal_capture.get("status") == "cpm_runtime_signal_capture_ready"
    preview = _as_dict(runtime_signal_capture.get("signal_detector_preview"))
    signal_state = str(preview.get("current_signal_state") or "unknown")
    fresh_signal_present = preview.get("fresh_signal_present") is True
    if not capture_ready:
        status = BLOCKED_STATUS
        first_blocker = {
            "class": "cpm_runtime_signal_capture_not_ready",
            "owner": "engineering",
            "repair_checkpoint": "restore_cpm_runtime_signal_capture",
        }
    elif not fresh_signal_present:
        status = WAITING_STATUS
        first_blocker = {
            "class": str(preview.get("first_blocker_class") or "fresh_cpm_long_signal_absent"),
            "owner": str(preview.get("first_blocker_owner") or "market"),
            "repair_checkpoint": str(
                preview.get("signal_capture_checkpoint")
                or "continue_cpm_long_armed_observation_until_reclaim_signal"
            ),
        }
    else:
        status = READY_STATUS
        first_blocker = {
            "class": "cpm_candidate_authorization_evidence_not_created",
            "owner": "runtime",
            "repair_checkpoint": "prepare_cpm_candidate_authorization_evidence",
        }
    ready = status == READY_STATUS
    return {
        "schema": "brc.cpm_shadow_candidate_evidence.v1",
        "scope": "cpm_shadow_candidate_evidence_read_model",
        "status": status,
        "generated_at_utc": generated,
        "strategy_group_id": "CPM-RO-001",
        "shadow_candidate_evidence_ready": ready,
        "shadow_candidate_evidence": {
            "shadow_candidate_evidence_id": (
                f"cpm-shadow-evidence:cpm_long_pullback_reclaim_signal_v1:{generated}"
                if ready
                else ""
            ),
            "shadow_candidate_evidence_type": "cpm_non_executing_long_signal_candidate_evidence",
            "strategy_group_id": "CPM-RO-001",
            "signal_id": "cpm_long_pullback_reclaim_signal_v1",
            "side": "long",
            "signal_state": signal_state,
            "fresh_signal_present": fresh_signal_present,
            "fact_authority": runtime_signal_capture.get("fact_authority") or "",
            "fact_authority_boundary": _as_dict(
                runtime_signal_capture.get("fact_authority_boundary")
            ),
        },
        "first_blocker": first_blocker,
        "next_runtime_step": (
            "prepare_cpm_candidate_authorization_evidence"
            if ready
            else first_blocker["repair_checkpoint"]
        ),
        "after_next_state": (
            "candidate_authorization_evidence_pending_action_time_finalgate"
            if ready
            else "armed_observation"
        ),
        "checks": {
            "shadow_candidate_evidence_ready": ready,
            "fresh_signal_present": fresh_signal_present,
            "non_executing_evidence": True,
        },
        "interaction": non_executing_interaction("L0_local_cpm_shadow_candidate_evidence"),
        "safety_invariants": non_executing_safety_invariants(
            ("authorization_evidence_created", "execution_attempt_created"),
            include_authority_mirrors=False,
        ),
    }


def _markdown(artifact: dict[str, Any], output_json: Path) -> str:
    return "\n".join(
        [
            "## CPM Shadow Candidate Evidence",
            "",
            f"- Status: `{artifact['status']}`",
            f"- Ready: `{_yes_no(artifact['shadow_candidate_evidence_ready'])}`",
            f"- First blocker: `{artifact['first_blocker']['class']}` / `{artifact['first_blocker']['owner']}`",
            f"- Output JSON: `{output_json}`",
        ]
    ) + "\n"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
