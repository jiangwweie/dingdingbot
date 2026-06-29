#!/usr/bin/env python3
"""Summarize active runtime observation artifacts without side effects."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import time
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ObservationArtifactSource:
    role: str
    artifact_name: str
    path: Path

    @property
    def label(self) -> str:
        return self.path.name

    def as_dict(self, *, loaded: bool) -> dict[str, Any]:
        return {
            "role": self.role,
            "artifact_name": self.artifact_name,
            "source_path": str(self.path),
            "loaded": loaded,
        }


ARTIFACT_SOURCE_SPECS = (
    ("supervisor", "supervisor-artifact.json"),
    ("loop", "loop-artifact.json"),
    ("followup", "followup-artifact.json"),
    ("latest_summary", "latest-summary.json"),
)
ARTIFACT_SOURCE_NAMES = (
    "supervisor-artifact.json",
    "loop-artifact.json",
    "followup-artifact.json",
    "latest-summary.json",
)

FORBIDDEN_SAFETY_FLAGS = (
    "exchange_write_called",
    "exchange_called",
    "exchange_order_submitted",
    "order_created",
    "order_lifecycle_called",
    "order_lifecycle_submit_called",
    "executable_execution_intent_created",
    "real_submit_requested",
    "exchange_order_requested",
    "attempt_counter_mutated",
    "runtime_budget_mutated",
    "withdrawal_or_transfer_created",
    "withdrawal_or_transfer_requested",
    "withdrawal_instruction_created",
    "transfer_instruction_created",
)
ALLOWED_PREPARE_RECORD_FLAGS = (
    "prepare_records_created",
    "shadow_candidate_created",
    "runtime_execution_intent_draft_created",
    "recorded_execution_intent_created",
    "submit_authorization_created",
    "protection_plan_created",
)
ALLOWED_OPERATION_LAYER_EVIDENCE_PREP_FLAGS = (
    "attempt_counter_mutated",
    "runtime_budget_mutated",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def _artifact_mtime_ms(path: Path) -> int | None:
    if not path.exists():
        return None
    return int(path.stat().st_mtime * 1000)


def _latest_artifact_path(root: Path) -> Path | None:
    existing = [root / name for name in ARTIFACT_SOURCE_NAMES if (root / name).exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def _preferred_artifact_source(
    root: Path,
    *,
    role: str,
    artifact_name: str,
) -> ObservationArtifactSource:
    artifact_path = root / artifact_name
    return ObservationArtifactSource(
        role=role,
        artifact_name=artifact_name,
        path=artifact_path,
    )


def _collect_forbidden_effects(
    *items: tuple[ObservationArtifactSource, dict[str, Any] | None],
) -> list[str]:
    effects: list[str] = []
    for source, artifact in items:
        if not artifact:
            continue
        safety = artifact.get("safety_invariants")
        if not isinstance(safety, dict):
            continue
        for flag in FORBIDDEN_SAFETY_FLAGS:
            if _allowed_operation_layer_evidence_prep_effect(
                source=source,
                artifact=artifact,
                safety=safety,
                flag=flag,
            ):
                continue
            if bool(safety.get(flag)):
                effects.append(f"{source.label}:{flag}")
        for effect in safety.get("forbidden_effects") or []:
            effects.append(f"{source.label}:{effect}")
        for effect in safety.get("loop_forbidden_effects") or []:
            effects.append(f"{source.label}:loop:{effect}")
        for effect in safety.get("arm_preview_forbidden_effects") or []:
            effects.append(f"{source.label}:arm_preview:{effect}")
        for effect in safety.get("disabled_smoke_forbidden_effects") or []:
            effects.append(f"{source.label}:disabled_smoke:{effect}")
    return effects


def _allowed_operation_layer_evidence_prep_effect(
    *,
    source: ObservationArtifactSource,
    artifact: dict[str, Any],
    safety: dict[str, Any],
    flag: str,
) -> bool:
    if (
        source.role != "followup"
        or flag not in ALLOWED_OPERATION_LAYER_EVIDENCE_PREP_FLAGS
        or not bool(safety.get(flag))
    ):
        return False
    plan = artifact.get("followup_plan")
    if not isinstance(plan, dict):
        plan = {}
    evidence_prep_allowed = (
        plan.get("mutating_attempt_consumption_allowed_by_this_artifact") is True
        or safety.get("attempt_policy_prepare_called") is True
    )
    evidence_prep_called = (
        safety.get("standing_authorized_operation_layer_evidence_prep_called") is True
        or safety.get("attempt_policy_prepare_called") is True
    )
    dangerous_flags_absent = all(
        not bool(safety.get(name))
        for name in (
            "exchange_called",
            "exchange_order_submitted",
            "order_created",
            "order_lifecycle_called",
            "order_lifecycle_submit_called",
            "real_submit_requested",
            "withdrawal_or_transfer_created",
        )
    )
    return evidence_prep_allowed and evidence_prep_called and dangerous_flags_absent


def _collect_allowed_operation_layer_evidence_prep(
    *items: tuple[ObservationArtifactSource, dict[str, Any] | None],
) -> list[str]:
    effects: list[str] = []
    for source, artifact in items:
        if not artifact:
            continue
        safety = artifact.get("safety_invariants")
        if not isinstance(safety, dict):
            continue
        for flag in ALLOWED_OPERATION_LAYER_EVIDENCE_PREP_FLAGS:
            if _allowed_operation_layer_evidence_prep_effect(
                source=source,
                artifact=artifact,
                safety=safety,
                flag=flag,
            ):
                effects.append(f"{source.label}:{flag}")
    return effects


def _collect_allowed_prepare_records(
    *artifacts: dict[str, Any] | None,
) -> dict[str, bool]:
    observed = {flag: False for flag in ALLOWED_PREPARE_RECORD_FLAGS}
    for artifact in artifacts:
        if not artifact:
            continue
        safety = artifact.get("safety_invariants")
        if not isinstance(safety, dict):
            safety = {}
        for flag in ALLOWED_PREPARE_RECORD_FLAGS:
            if bool(artifact.get(flag)) or bool(safety.get(flag)):
                observed[flag] = True
        created = artifact.get("created_records")
        if isinstance(created, dict):
            if bool(created.get("shadow_candidate_created")):
                observed["shadow_candidate_created"] = True
            if bool(created.get("runtime_execution_intent_draft_created")):
                observed["runtime_execution_intent_draft_created"] = True
            if bool(
                created.get("recorded_execution_intent_created")
                or created.get("execution_intent_created")
            ):
                observed["recorded_execution_intent_created"] = True
            if bool(created.get("submit_authorization_created")):
                observed["submit_authorization_created"] = True
            if bool(created.get("protection_plan_created")):
                observed["protection_plan_created"] = True
    return observed


def _runtime_signal_summaries(summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not summary:
        return []
    rows = summary.get("runtime_signal_summaries")
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        signal = row.get("signal_summary")
        if not isinstance(signal, dict):
            signal = {}
        result.append(
            {
                "runtime_instance_id": row.get("runtime_instance_id"),
                "strategy_family_id": row.get("strategy_family_id"),
                "strategy_family_version_id": row.get("strategy_family_version_id"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "status": row.get("status"),
                "signal_input_json": row.get("signal_input_json"),
                "prepared_authorization_id": row.get("prepared_authorization_id"),
                "evaluation_status": signal.get("evaluation_status"),
                "signal_type": signal.get("signal_type"),
                "signal_side": signal.get("side"),
                "confidence": signal.get("confidence"),
                "reason_codes": signal.get("reason_codes") or [],
                "human_summary": signal.get("human_summary"),
            }
        )
    return result


def build_status_artifact(
    output_dir: str | Path,
    *,
    stale_after_seconds: float = 900.0,
    now_ms: int | None = None,
) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    now_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)

    source_by_role = {
        role: _preferred_artifact_source(
            root,
            role=role,
            artifact_name=artifact_name,
        )
        for role, artifact_name in ARTIFACT_SOURCE_SPECS
    }
    supervisor_source = source_by_role["supervisor"]
    loop_source = source_by_role["loop"]
    followup_source = source_by_role["followup"]
    latest_summary_source = source_by_role["latest_summary"]

    supervisor = _read_json(supervisor_source.path)
    loop = _read_json(loop_source.path)
    followup = _read_json(followup_source.path)
    latest_summary = _read_json(latest_summary_source.path)
    if latest_summary is None and isinstance(loop, dict):
        maybe_summary = loop.get("latest_summary")
        latest_summary = maybe_summary if isinstance(maybe_summary, dict) else None
    source_items = (
        (supervisor_source, supervisor),
        (loop_source, loop),
        (followup_source, followup),
        (latest_summary_source, latest_summary),
    )

    latest_path = _latest_artifact_path(root)
    latest_mtime_ms = _artifact_mtime_ms(latest_path) if latest_path else None
    latest_age_seconds = (
        max((now_ms - latest_mtime_ms) / 1000, 0)
        if latest_mtime_ms is not None
        else None
    )
    artifact_stale = (
        latest_age_seconds is None or latest_age_seconds > float(stale_after_seconds)
    )

    latest_status = None
    for artifact in (followup, loop, latest_summary, supervisor):
        if isinstance(artifact, dict) and artifact.get("status"):
            latest_status = artifact.get("status")
            break

    forbidden_effects = _collect_forbidden_effects(*source_items)
    allowed_prepare_records = _collect_allowed_prepare_records(
        supervisor,
        loop,
        followup,
        latest_summary,
    )
    allowed_operation_layer_evidence_prep_effects = (
        _collect_allowed_operation_layer_evidence_prep(*source_items)
    )
    blockers: list[str] = []
    warnings: list[str] = []
    for artifact in (supervisor, loop, followup, latest_summary):
        if not isinstance(artifact, dict):
            continue
        blockers.extend(str(item) for item in artifact.get("blockers") or [])
        warnings.extend(str(item) for item in artifact.get("warnings") or [])
    if artifact_stale:
        blockers.append("active_observation_artifacts_stale_or_missing")
    if forbidden_effects:
        blockers.append("active_observation_forbidden_effects_detected")

    status = "ok"
    if forbidden_effects:
        status = "blocked_forbidden_effect"
    elif artifact_stale:
        status = "stale"
    elif latest_status in {"blocked", "disabled_smoke_blocked", "supervisor_blocked"}:
        status = "blocked"
    elif latest_status in {
        "ready_for_prepare",
        "ready_for_prepare_records",
        "ready_for_final_gate_preflight",
        "ready_for_disabled_smoke",
        "disabled_smoke_completed",
    }:
        status = "attention"
    elif (
        latest_status == "waiting_for_signal"
        and isinstance(loop, dict)
        and loop.get("stop_reason") == "max_iterations_exhausted"
    ):
        status = "observation_window_complete_no_signal"
    elif latest_status == "waiting_for_signal":
        status = "waiting_for_signal"

    latest_summary_observation_plan = (
        latest_summary.get("observation_plan")
        if isinstance(latest_summary, dict)
        else None
    )
    loop_observation_plan = (
        loop.get("observation_loop_plan") if isinstance(loop, dict) else None
    )
    followup_plan = (
        followup.get("followup_plan") if isinstance(followup, dict) else None
    )

    iterations_requested = (
        loop.get("iterations_requested") if isinstance(loop, dict) else None
    )
    iterations_completed = (
        loop.get("iterations_completed") if isinstance(loop, dict) else None
    )
    iterations_remaining = None
    if iterations_requested is not None and iterations_completed is not None:
        iterations_remaining = max(
            int(iterations_requested) - int(iterations_completed),
            0,
        )
    stop_reason = loop.get("stop_reason") if isinstance(loop, dict) else None

    return {
        "scope": "runtime_active_observation_status",
        "status": status,
        "output_dir": str(root),
        "latest_status": latest_status,
        "latest_artifact": str(latest_path) if latest_path else None,
        "artifact_sources": [
            source.as_dict(loaded=artifact is not None)
            for source, artifact in source_items
        ],
        "latest_artifact_age_seconds": latest_age_seconds,
        "stale_after_seconds": float(stale_after_seconds),
        "artifact_stale": artifact_stale,
        "supervisor_status": supervisor.get("status") if isinstance(supervisor, dict) else None,
        "loop_status": loop.get("status") if isinstance(loop, dict) else None,
        "followup_status": followup.get("status") if isinstance(followup, dict) else None,
        "iterations_requested": iterations_requested,
        "iterations_completed": iterations_completed,
        "iterations_remaining": iterations_remaining,
        "latest_iteration": (
            latest_summary.get("iteration")
            if isinstance(latest_summary, dict)
            else None
        ),
        "stop_reason": stop_reason,
        "observation_running": stop_reason == "running",
        "observation_window_complete": stop_reason == "max_iterations_exhausted",
        "active_runtime_count": (
            latest_summary.get("active_runtime_count")
            if isinstance(latest_summary, dict)
            else None
        ),
        "monitored_runtime_count": (
            latest_summary.get("monitored_runtime_count")
            if isinstance(latest_summary, dict)
            else None
        ),
        "selected_runtime_instance_ids": (
            latest_summary.get("selected_runtime_instance_ids")
            if isinstance(latest_summary, dict)
            else []
        ),
        "signal_input_json": (
            latest_summary.get("signal_input_json")
            if isinstance(latest_summary, dict)
            else None
        ),
        "prepared_authorization_id": (
            latest_summary.get("prepared_authorization_id")
            if isinstance(latest_summary, dict)
            else None
        ),
        "shadow_candidate_id": (
            latest_summary.get("shadow_candidate_id")
            if isinstance(latest_summary, dict)
            else None
        ),
        "runtime_signal_summaries": _runtime_signal_summaries(latest_summary),
        "blockers": blockers,
        "warnings": warnings,
        "forbidden_effects": forbidden_effects,
        "allowed_prepare_record_effects": [
            flag for flag, observed in allowed_prepare_records.items() if observed
        ],
        "allowed_operation_layer_evidence_prep_effects": (
            allowed_operation_layer_evidence_prep_effects
        ),
        "observation_plan": {
            "not_execution_authority": True,
            "latest_summary_next_step": (
                latest_summary_observation_plan or {}
            ).get("next_step"),
            "loop_next_step": (loop_observation_plan or {}).get("next_step"),
            "followup_next_step": (followup_plan or {}).get("next_step"),
            "observation_next_step": _observation_next_step(
                status=status,
                stop_reason=stop_reason,
            ),
        },
        "safety_invariants": {
            "read_artifacts_only": True,
            "connects_to_api": False,
            "connects_to_exchange": False,
            "creates_prepare_records": False,
            "observed_prepare_records_created": allowed_prepare_records[
                "prepare_records_created"
            ],
            "observed_shadow_candidate_created": allowed_prepare_records[
                "shadow_candidate_created"
            ],
            "observed_runtime_execution_intent_draft_created": (
                allowed_prepare_records["runtime_execution_intent_draft_created"]
            ),
            "observed_recorded_execution_intent_created": allowed_prepare_records[
                "recorded_execution_intent_created"
            ],
            "observed_submit_authorization_created": allowed_prepare_records[
                "submit_authorization_created"
            ],
            "observed_protection_plan_created": allowed_prepare_records[
                "protection_plan_created"
            ],
            "creates_shadow_candidate": False,
            "creates_execution_intent": False,
            "places_order": False,
            "calls_order_lifecycle": False,
            "mutates_runtime_budget": False,
            "mutates_attempt_counter": False,
            "withdrawal_or_transfer_created": False,
            "forbidden_effects": forbidden_effects,
            "allowed_operation_layer_evidence_prep_effects": (
                allowed_operation_layer_evidence_prep_effects
            ),
        },
    }


def _observation_next_step(*, status: str, stop_reason: str | None) -> str:
    if status == "observation_window_complete_no_signal":
        return "review_no_signal_window_or_start_new_observation"
    if stop_reason == "running":
        return "continue_active_observation_loop"
    if status == "attention":
        return "review_non_executing_prepare_or_preview_artifact"
    if status.startswith("blocked"):
        return "resolve_active_observation_status_blocker"
    if status == "stale":
        return "refresh_or_restart_active_observation_status"
    return "review_active_observation_status"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize runtime active observation artifact state."
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--output-json")
    parser.add_argument("--stale-after-seconds", type=float, default=900.0)
    args = parser.parse_args()

    artifact = build_status_artifact(
        args.output_dir,
        stale_after_seconds=args.stale_after_seconds,
    )
    payload = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        path = Path(args.output_json).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
