"""Runtime control-state repository boundary.

This is the transitional file-backed implementation. Callers consume this
repository instead of scattering direct reads of current projection JSON files.
The storage backend can move to PG without changing the builder entrypoints.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RuntimeControlStateRepositoryError(RuntimeError):
    """Raised when a runtime control-state source is malformed."""


class FileBackedRuntimeControlStateRepository:
    """Read current runtime control-state projections from JSON files."""

    def read_json(self, path: Path | str, *, missing_ok: bool = True) -> dict[str, Any]:
        resolved = Path(path)
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if missing_ok:
                return {}
            raise RuntimeControlStateRepositoryError(f"{resolved} is missing") from None
        except json.JSONDecodeError as exc:
            if missing_ok:
                return {}
            raise RuntimeControlStateRepositoryError(
                f"{resolved} must contain valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            if missing_ok:
                return {}
            raise RuntimeControlStateRepositoryError(
                f"{resolved} must contain a JSON object"
            )
        return payload

    def candidate_pool_inputs(
        self,
        *,
        daily_table_json: Path,
        tradeability_json: Path,
        replay_live_parity_json: Path,
        action_time_boundary_json: Path,
        sor_detector_json: Path,
        mi_trial_admission_json: Path,
        brf2_runtime_signal_facts_json: Path,
        single_lane_task_packet_json: Path,
        runtime_active_monitor_json: Path,
        owner_pretrade_authorization_json: Path,
    ) -> dict[str, dict[str, Any]]:
        return {
            "daily_table": self.read_json(daily_table_json),
            "tradeability": self.read_json(tradeability_json),
            "replay_live_parity": self.read_json(replay_live_parity_json),
            "action_time_boundary": self.read_json(action_time_boundary_json),
            "sor_detector": self.read_json(sor_detector_json),
            "mi_trial_admission": self.read_json(mi_trial_admission_json),
            "brf2_runtime_signal_facts": self.read_json(brf2_runtime_signal_facts_json),
            "single_lane_task_packet": self.read_json(single_lane_task_packet_json),
            "runtime_active_monitor": self.read_json(runtime_active_monitor_json),
            "owner_pretrade_authorization": self.read_json(
                owner_pretrade_authorization_json
            ),
        }

    def daily_table_inputs(
        self,
        *,
        tradeability_json: Path,
        replay_live_parity_json: Path,
        action_time_boundary_json: Path,
        mi_trial_admission_json: Path,
        runtime_safety_json: Path,
        candidate_pool_json: Path | None = None,
    ) -> dict[str, dict[str, Any]]:
        return {
            "tradeability": self.read_json(tradeability_json),
            "replay_live_parity": self.read_json(replay_live_parity_json),
            "action_time_boundary": self.read_json(action_time_boundary_json),
            "mi_trial_admission": self.read_json(mi_trial_admission_json),
            "runtime_safety": self.read_json(runtime_safety_json),
            "candidate_pool": (
                self.read_json(candidate_pool_json) if candidate_pool_json else {}
            ),
        }

    def goal_status_source_artifacts(
        self,
        *,
        report_dir: Path,
        source_artifact_files: dict[str, str],
        candidate_pool_json: Path | None = None,
    ) -> dict[str, dict[str, Any] | None]:
        artifacts: dict[str, dict[str, Any] | None] = {
            key: self.read_json(report_dir / filename)
            or None
            for key, filename in source_artifact_files.items()
        }
        artifacts["candidate_pool"] = (
            self.read_json(candidate_pool_json) or None
            if candidate_pool_json and candidate_pool_json.exists()
            else None
        )
        return artifacts

    def release_manifest(self, path: Path | None) -> dict[str, Any] | None:
        if path is None:
            return None
        return self.read_json(path) or None
