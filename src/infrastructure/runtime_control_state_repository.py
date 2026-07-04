"""Runtime control-state repository boundary.

File-backed reads are allowed only for local migration comparison, inventory, or
tests. Production current runtime authority must be DB-backed and fail closed
instead of falling back to repo/output JSON files.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa


class RuntimeControlStateRepositoryError(RuntimeError):
    """Raised when a runtime control-state source is malformed."""


CONTROL_STATE_TABLES: dict[str, str] = {
    "strategy_groups": "brc_strategy_groups",
    "strategy_group_versions": "brc_strategy_group_versions",
    "required_fact_contracts": "brc_required_fact_contracts",
    "strategy_side_event_specs": "brc_strategy_side_event_specs",
    "strategy_event_required_facts": "brc_strategy_event_required_facts",
    "owner_policy_events": "brc_owner_policy_events",
    "owner_policy_current": "brc_owner_policy_current",
    "candidate_scope": "brc_strategy_group_candidate_scope",
    "candidate_scope_event_bindings": "brc_candidate_scope_event_bindings",
    "runtime_scope_bindings": "brc_runtime_scope_bindings",
    "symbols": "brc_symbols",
    "exchange_instruments": "brc_exchange_instruments",
    "symbol_instrument_mappings": "brc_symbol_instrument_mappings",
    "execution_policies": "brc_execution_policies",
    "watcher_runtime_coverage": "brc_watcher_runtime_coverage",
    "runtime_fact_snapshots": "brc_runtime_fact_snapshots",
    "live_signal_events": "brc_live_signal_events",
    "pretrade_readiness_rows": "brc_pretrade_readiness_rows",
    "promotion_candidates": "brc_promotion_candidates",
    "action_time_lane_inputs": "brc_action_time_lane_inputs",
    "budget_reservations": "brc_budget_reservations",
    "protection_references": "brc_protection_references",
    "action_time_tickets": "brc_action_time_tickets",
    "action_time_ticket_events": "brc_action_time_ticket_events",
    "operation_layer_handoffs": "brc_operation_layer_handoffs",
    "runtime_safety_state": "brc_runtime_safety_state_snapshots",
    "ticket_bound_protected_submit_attempts": (
        "brc_ticket_bound_protected_submit_attempts"
    ),
    "goal_status_current": "brc_goal_status_current",
    "projection_runs": "brc_projection_runs",
    "current_projection_ownership": "brc_current_projection_ownership",
    "control_read_model_snapshots": "brc_control_read_model_snapshots",
    "server_monitor_runs": "brc_server_monitor_runs",
    "server_monitor_notifications": "brc_server_monitor_notifications",
}

REQUIRED_PRODUCTION_PROJECTIONS = {
    "candidate_pool",
    "daily_live_enablement_table",
    "goal_status",
    "runtime_safety_state",
    "server_monitor",
    "tradeability_decision",
}


class PgBackedRuntimeControlStateRepository:
    """Read production runtime control-state from PG current tables."""

    def __init__(
        self,
        conn: sa.engine.Connection,
        *,
        source_mode: str = "db_backed",
        projection_target: str = "production_current",
    ) -> None:
        if source_mode != "db_backed":
            raise RuntimeControlStateRepositoryError(
                "PgBackedRuntimeControlStateRepository requires source_mode='db_backed'"
            )
        if projection_target != "production_current":
            raise RuntimeControlStateRepositoryError(
                "PgBackedRuntimeControlStateRepository reads production_current only"
            )
        self.conn = conn
        self.source_mode = source_mode
        self.projection_target = projection_target

    def read_control_state(self) -> dict[str, Any]:
        self._require_tables()
        rows = {
            key: self._read_rows(table_name)
            for key, table_name in CONTROL_STATE_TABLES.items()
        }
        self._validate_projection_ownership(rows)
        self._validate_candidate_scope_event_bindings(rows)
        self._validate_runtime_scope_bindings(rows)
        return {
            "schema": "brc.runtime_control_state_repository.v1",
            "source_mode": self.source_mode,
            "projection_target": self.projection_target,
            "table_counts": {key: len(value) for key, value in rows.items()},
            **rows,
        }

    def _require_tables(self) -> None:
        inspector = sa.inspect(self.conn)
        existing = set(inspector.get_table_names())
        missing = [
            table_name
            for table_name in CONTROL_STATE_TABLES.values()
            if table_name not in existing
        ]
        if missing:
            raise RuntimeControlStateRepositoryError(
                "PG runtime control-state tables missing: " + ", ".join(sorted(missing))
            )

    def _read_rows(self, table_name: str) -> list[dict[str, Any]]:
        metadata = sa.MetaData()
        table = sa.Table(table_name, metadata, autoload_with=self.conn)
        order_by = list(table.primary_key.columns)
        statement = sa.select(table)
        if order_by:
            statement = statement.order_by(*order_by)
        return [
            {key: _json_safe(value) for key, value in row.items()}
            for row in self.conn.execute(statement).mappings()
        ]

    def _validate_projection_ownership(self, rows: dict[str, list[dict[str, Any]]]) -> None:
        ownership_rows = rows["current_projection_ownership"]
        if not ownership_rows:
            raise RuntimeControlStateRepositoryError(
                "current projection ownership is empty"
            )
        model_scope_seen: set[tuple[str, str]] = set()
        model_types: set[str] = set()
        for row in ownership_rows:
            model_type = str(row.get("model_type") or "")
            scope_key = str(row.get("projection_scope_key") or "")
            key = (model_type, scope_key)
            if not model_type or not scope_key:
                raise RuntimeControlStateRepositoryError(
                    "current projection ownership requires model_type and scope key"
                )
            if key in model_scope_seen:
                raise RuntimeControlStateRepositoryError(
                    f"duplicate current projection ownership: {model_type}:{scope_key}"
                )
            model_scope_seen.add(key)
            model_types.add(model_type)
            if row.get("legacy_writer_allowed") is not False:
                raise RuntimeControlStateRepositoryError(
                    f"{model_type}:{scope_key} allows legacy writer"
                )
            if row.get("current_source_mode") != "db_backed":
                raise RuntimeControlStateRepositoryError(
                    f"{model_type}:{scope_key} is not DB-backed"
                )

        missing = REQUIRED_PRODUCTION_PROJECTIONS - model_types
        if missing:
            raise RuntimeControlStateRepositoryError(
                "required production projections missing ownership: "
                + ", ".join(sorted(missing))
            )

        for row in rows["projection_runs"]:
            if (
                row.get("projection_target") == "production_current"
                and row.get("status") == "succeeded"
            ):
                if row.get("source_mode") != "db_backed":
                    raise RuntimeControlStateRepositoryError(
                        f"projection run {row.get('projection_run_id')} is not DB-backed"
                    )
                if row.get("legacy_diagnostics_affected_current") is not False:
                    raise RuntimeControlStateRepositoryError(
                        "legacy diagnostics affected a production current projection"
                    )

    def _validate_candidate_scope_event_bindings(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> None:
        active_candidates = {
            str(row["candidate_scope_id"]): row
            for row in rows["candidate_scope"]
            if row.get("status") == "active"
        }
        if not active_candidates:
            raise RuntimeControlStateRepositoryError("active candidate scope is empty")

        current_events = {
            str(row["event_spec_id"]): row
            for row in rows["strategy_side_event_specs"]
            if row.get("status") == "current"
        }
        active_binding_by_candidate: dict[str, list[dict[str, Any]]] = {}
        for binding in rows["candidate_scope_event_bindings"]:
            if binding.get("status") != "active":
                continue
            active_binding_by_candidate.setdefault(
                str(binding.get("candidate_scope_id") or ""),
                [],
            ).append(binding)

        for candidate_id, candidate in active_candidates.items():
            bindings = active_binding_by_candidate.get(candidate_id) or []
            if not bindings:
                raise RuntimeControlStateRepositoryError(
                    f"{candidate_id} has no active event binding"
                )
            for binding in bindings:
                event = current_events.get(str(binding.get("event_spec_id") or ""))
                if not event:
                    raise RuntimeControlStateRepositoryError(
                        f"{binding.get('binding_id')} does not reference a current event spec"
                    )
                for key in ("strategy_group_id", "side"):
                    if binding.get(key) != candidate.get(key) or event.get(key) != candidate.get(key):
                        raise RuntimeControlStateRepositoryError(
                            f"{binding.get('binding_id')} mismatches candidate {key}"
                        )
                if binding.get("symbol") != candidate.get("symbol"):
                    raise RuntimeControlStateRepositoryError(
                        f"{binding.get('binding_id')} mismatches candidate symbol"
                    )

    def _validate_runtime_scope_bindings(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> None:
        candidates = {
            str(row["candidate_scope_id"]): row
            for row in rows["candidate_scope"]
            if row.get("status") == "active"
        }
        policies = {
            str(row["policy_current_id"]): row
            for row in rows["owner_policy_current"]
        }
        for binding in rows["runtime_scope_bindings"]:
            if binding.get("status") != "active":
                continue
            candidate = candidates.get(str(binding.get("candidate_scope_id") or ""))
            if not candidate:
                raise RuntimeControlStateRepositoryError(
                    f"{binding.get('runtime_scope_binding_id')} has no active candidate scope"
                )
            policy = policies.get(str(binding.get("policy_current_id") or ""))
            if not policy:
                raise RuntimeControlStateRepositoryError(
                    f"{binding.get('runtime_scope_binding_id')} has no current owner policy"
                )
            for key in ("strategy_group_id", "symbol", "side"):
                if binding.get(key) != candidate.get(key):
                    raise RuntimeControlStateRepositoryError(
                        f"{binding.get('runtime_scope_binding_id')} mismatches candidate {key}"
                    )
                if policy.get(key) != binding.get(key):
                    raise RuntimeControlStateRepositoryError(
                        f"{binding.get('runtime_scope_binding_id')} mismatches policy {key}"
                    )
            if binding.get("live_submit_allowed") is True and not (
                binding.get("selected_strategygroup_scope") is True
                and binding.get("symbol_side_scope_closed") is True
                and binding.get("notional_leverage_scope_closed") is True
            ):
                raise RuntimeControlStateRepositoryError(
                    f"{binding.get('runtime_scope_binding_id')} allows live submit without closed scope"
                )


class FileBackedRuntimeControlStateRepository:
    """Read legacy JSON projections for non-production migration comparison."""

    ALLOWED_SOURCE_MODES = {
        "local_migration_comparison",
        "local_file_inventory",
        "test_fixture",
    }

    def __init__(self, *, source_mode: str = "local_migration_comparison") -> None:
        if source_mode not in self.ALLOWED_SOURCE_MODES:
            raise RuntimeControlStateRepositoryError(
                "FileBackedRuntimeControlStateRepository cannot provide "
                f"{source_mode!r} runtime control-state authority"
            )
        self.source_mode = source_mode

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

    def read_optional_json(
        self,
        path: Path | str | None,
        *,
        missing_ok: bool = True,
    ) -> dict[str, Any]:
        if path is None:
            return {}
        return self.read_json(path, missing_ok=missing_ok)

    def candidate_pool_inputs(
        self,
        *,
        daily_table_json: Path,
        tradeability_json: Path,
        replay_live_parity_json: Path,
        action_time_boundary_json: Path,
        sor_detector_json: Path | None,
        mi_trial_admission_json: Path,
        brf2_runtime_signal_facts_json: Path,
        single_lane_task_packet_json: Path,
        runtime_active_monitor_json: Path | None,
        owner_pretrade_authorization_json: Path | None,
    ) -> dict[str, dict[str, Any]]:
        return {
            "daily_table": self.read_json(daily_table_json),
            "tradeability": self.read_json(tradeability_json),
            "replay_live_parity": self.read_json(replay_live_parity_json),
            "action_time_boundary": self.read_json(action_time_boundary_json),
            "sor_detector": self.read_optional_json(sor_detector_json),
            "mi_trial_admission": self.read_json(mi_trial_admission_json),
            "brf2_runtime_signal_facts": self.read_json(brf2_runtime_signal_facts_json),
            "single_lane_task_packet": self.read_json(single_lane_task_packet_json),
            "runtime_active_monitor": self.read_optional_json(
                runtime_active_monitor_json
            ),
            "owner_pretrade_authorization": self.read_optional_json(
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


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
