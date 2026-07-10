"""Runtime control-state repository boundary.

Runtime/control authority is DB-backed only. Historical JSON/Markdown material is
archive provenance and must not be exposed through this current repository.
"""

from __future__ import annotations

from decimal import Decimal
import time
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
    "ticket_bound_submit_mode_decisions": "brc_ticket_bound_submit_mode_decisions",
    "ticket_bound_protected_submit_attempts": (
        "brc_ticket_bound_protected_submit_attempts"
    ),
    "ticket_bound_exchange_commands": "brc_ticket_bound_exchange_commands",
    "ticket_bound_post_submit_closures": "brc_ticket_bound_post_submit_closures",
    "ticket_bound_order_lifecycle_runs": "brc_ticket_bound_order_lifecycle_runs",
    "ticket_bound_scope_freezes": "brc_ticket_bound_scope_freezes",
    "live_outcome_ledger": "brc_live_outcome_ledger",
    "goal_status_current": "brc_goal_status_current",
    "projection_runs": "brc_projection_runs",
    "current_projection_ownership": "brc_current_projection_ownership",
    "control_read_model_snapshots": "brc_control_read_model_snapshots",
    "server_monitor_runs": "brc_server_monitor_runs",
    "server_monitor_notifications": "brc_server_monitor_notifications",
    "runtime_process_outcomes": "brc_runtime_process_outcomes",
    "strategy_semantic_admissions": "brc_strategy_semantic_admissions",
    "allocation_decisions": "brc_allocation_decisions",
}

OPTIONAL_CONTROL_STATE_TABLES = {
    "allocation_decisions",
    "runtime_process_outcomes",
    "strategy_semantic_admissions",
    "ticket_bound_order_lifecycle_runs",
    "ticket_bound_exchange_commands",
    "ticket_bound_scope_freezes",
    "live_outcome_ledger",
}

REQUIRED_PRODUCTION_PROJECTIONS = {
    "candidate_pool",
    "daily_live_enablement_table",
    "goal_status",
    "runtime_safety_state",
    "server_monitor",
    "tradeability_decision",
}

OPEN_REAL_LANE_STATUSES = {
    "opened",
    "facts_refreshing",
    "ticket_pending",
    "ticket_created",
}


class PgBackedRuntimeControlStateRepository:
    """Read production runtime control-state from PG current tables."""

    def __init__(
        self,
        conn: sa.engine.Connection,
        *,
        source_mode: str = "db_backed",
        projection_target: str = "production_current",
        now_ms: int | None = None,
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
        self.now_ms = int(now_ms if now_ms is not None else time.time() * 1000)

    def read_control_state(self) -> dict[str, Any]:
        self._require_tables()
        rows = {
            key: self._read_rows(
                table_name,
                optional=key in OPTIONAL_CONTROL_STATE_TABLES,
            )
            for key, table_name in CONTROL_STATE_TABLES.items()
        }
        self._validate_projection_ownership(rows)
        self._validate_active_event_semantics(rows)
        self._validate_candidate_scope_event_bindings(rows)
        self._validate_runtime_scope_bindings(rows)
        self._validate_live_signal_events(rows)
        self._validate_promotion_and_lane_identity(rows)
        return {
            "schema": "brc.runtime_control_state_repository.v1",
            "source_mode": self.source_mode,
            "projection_target": self.projection_target,
            "read_now_ms": self.now_ms,
            "table_counts": {key: len(value) for key, value in rows.items()},
            **rows,
        }

    def read_monitor_control_state(self) -> dict[str, Any]:
        self._require_tables()
        rows = {
            key: self._read_rows(
                table_name,
                monitor_bounded=True,
                logical_key=key,
                optional=key in OPTIONAL_CONTROL_STATE_TABLES,
            )
            for key, table_name in CONTROL_STATE_TABLES.items()
        }
        self._retain_monitor_protected_submit_lineage(rows)
        self._validate_projection_ownership(rows)
        self._validate_active_event_semantics(rows)
        self._validate_candidate_scope_event_bindings(rows)
        self._validate_runtime_scope_bindings(rows)
        self._validate_live_signal_events(rows)
        self._validate_promotion_and_lane_identity(rows)
        return {
            "schema": "brc.runtime_control_state_repository.v1",
            "source_mode": self.source_mode,
            "projection_target": self.projection_target,
            "read_profile": "monitor_bounded_current",
            "read_now_ms": self.now_ms,
            "table_counts": {key: len(value) for key, value in rows.items()},
            **rows,
        }

    def _require_tables(self) -> None:
        inspector = sa.inspect(self.conn)
        existing = set(inspector.get_table_names())
        missing = [
            table_name
            for key, table_name in CONTROL_STATE_TABLES.items()
            if key not in OPTIONAL_CONTROL_STATE_TABLES
            if table_name not in existing
        ]
        if missing:
            raise RuntimeControlStateRepositoryError(
                "PG runtime control-state tables missing: " + ", ".join(sorted(missing))
            )

    def _read_rows(
        self,
        table_name: str,
        *,
        monitor_bounded: bool = False,
        logical_key: str = "",
        optional: bool = False,
    ) -> list[dict[str, Any]]:
        if optional and not sa.inspect(self.conn).has_table(table_name):
            return []
        metadata = sa.MetaData()
        table = sa.Table(table_name, metadata, autoload_with=self.conn)
        order_by = list(table.primary_key.columns)
        statement = sa.select(table)
        if monitor_bounded:
            statement = _monitor_bounded_statement(
                statement,
                table,
                logical_key,
                now_ms=self.now_ms,
            )
        if order_by:
            statement = statement.order_by(*order_by)
        return [
            {key: _json_safe(value) for key, value in row.items()}
            for row in self.conn.execute(statement).mappings()
        ]

    def _read_rows_where_in(
        self,
        table_name: str,
        column_name: str,
        values: set[str],
    ) -> list[dict[str, Any]]:
        if not values:
            return []
        metadata = sa.MetaData()
        table = sa.Table(table_name, metadata, autoload_with=self.conn)
        if column_name not in table.c:
            return []
        statement = sa.select(table).where(table.c[column_name].in_(sorted(values)))
        return [
            {key: _json_safe(value) for key, value in row.items()}
            for row in self.conn.execute(statement).mappings()
        ]

    def _retain_monitor_protected_submit_lineage(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> None:
        attempts = rows.get("ticket_bound_protected_submit_attempts") or []
        if not attempts:
            return

        ticket_ids = _texts(row.get("ticket_id") for row in attempts)
        ticket_rows = self._read_rows_where_in(
            CONTROL_STATE_TABLES["action_time_tickets"],
            "ticket_id",
            ticket_ids,
        )
        current_ticket_ids = {
            str(row.get("ticket_id") or "")
            for row in ticket_rows
            if _is_monitor_current_ticket(row, self.now_ms)
        }
        attempts = [
            row
            for row in attempts
            if str(row.get("status") or "") == "submitted"
            or str(row.get("ticket_id") or "") in current_ticket_ids
        ]
        rows["ticket_bound_protected_submit_attempts"] = attempts
        if not attempts:
            return

        ticket_ids = _texts(row.get("ticket_id") for row in attempts)
        lane_ids = _texts(row.get("action_time_lane_input_id") for row in attempts)
        safety_ids = _texts(row.get("runtime_safety_snapshot_id") for row in attempts)
        handoff_ids = _texts(row.get("operation_layer_handoff_id") for row in attempts)
        ticket_rows = [row for row in ticket_rows if str(row.get("ticket_id") or "") in ticket_ids]

        self._merge_rows(
            rows,
            "runtime_safety_state",
            "runtime_safety_snapshot_id",
            self._read_rows_where_in(
                CONTROL_STATE_TABLES["runtime_safety_state"],
                "runtime_safety_snapshot_id",
                safety_ids,
            ),
        )
        self._merge_rows(
            rows,
            "operation_layer_handoffs",
            "operation_layer_handoff_id",
            self._read_rows_where_in(
                CONTROL_STATE_TABLES["operation_layer_handoffs"],
                "operation_layer_handoff_id",
                handoff_ids,
            ),
        )

        self._merge_rows(rows, "action_time_tickets", "ticket_id", ticket_rows)
        lane_ids.update(_texts(row.get("action_time_lane_input_id") for row in ticket_rows))

        lane_rows = self._read_rows_where_in(
            CONTROL_STATE_TABLES["action_time_lane_inputs"],
            "action_time_lane_input_id",
            lane_ids,
        )
        self._merge_rows(
            rows,
            "action_time_lane_inputs",
            "action_time_lane_input_id",
            lane_rows,
        )

        promotion_ids = _texts(
            row.get("promotion_candidate_id") for row in [*ticket_rows, *lane_rows]
        )
        signal_ids = _texts(row.get("signal_event_id") for row in [*ticket_rows, *lane_rows])
        promotion_rows = self._read_rows_where_in(
            CONTROL_STATE_TABLES["promotion_candidates"],
            "promotion_candidate_id",
            promotion_ids,
        )
        self._merge_rows(
            rows,
            "promotion_candidates",
            "promotion_candidate_id",
            promotion_rows,
        )
        signal_ids.update(_texts(row.get("signal_event_id") for row in promotion_rows))
        self._merge_rows(
            rows,
            "live_signal_events",
            "signal_event_id",
            self._read_rows_where_in(
                CONTROL_STATE_TABLES["live_signal_events"],
                "signal_event_id",
                signal_ids,
            ),
        )

    @staticmethod
    def _merge_rows(
        rows: dict[str, list[dict[str, Any]]],
        logical_key: str,
        id_key: str,
        additions: list[dict[str, Any]],
    ) -> None:
        if not additions:
            return
        existing = {
            str(row.get(id_key) or "")
            for row in rows.get(logical_key, [])
            if str(row.get(id_key) or "")
        }
        for row in additions:
            row_id = str(row.get(id_key) or "")
            if row_id and row_id not in existing:
                rows.setdefault(logical_key, []).append(row)
                existing.add(row_id)

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
            if len(bindings) != 1:
                raise RuntimeControlStateRepositoryError(
                    f"{candidate_id} must have exactly one active event binding"
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
                event_id = str(event.get("event_id") or "")
                candidate_event_id = str(_as_dict(candidate.get("metadata")).get("event_id") or "")
                if candidate_event_id and candidate_event_id != event_id:
                    raise RuntimeControlStateRepositoryError(
                        f"{candidate_id} metadata event_id mismatches current event spec"
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

    def _validate_active_event_semantics(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> None:
        current_events = {
            str(row.get("event_spec_id") or ""): row
            for row in rows["strategy_side_event_specs"]
            if row.get("status") == "current"
        }
        current_versions = {
            str(row.get("strategy_group_version_id") or ""): row
            for row in rows["strategy_group_versions"]
            if row.get("status") == "current"
        }
        if not current_events:
            raise RuntimeControlStateRepositoryError("current PG event specs are empty")
        seen_event_keys: set[tuple[str, str, str]] = set()
        for event_spec_id, event in current_events.items():
            for key in (
                "strategy_group_id",
                "event_id",
                "side",
                "timeframe",
                "time_authority",
                "protection_ref_type",
            ):
                if not str(event.get(key) or ""):
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id} missing {key}"
                    )
            if event.get("side") not in {"long", "short"}:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} has invalid side"
                )
            version = current_versions.get(str(event.get("strategy_group_version_id") or ""))
            if not version:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} has no current StrategyGroup version"
                )
            if str(version.get("strategy_group_id") or "") != str(
                event.get("strategy_group_id") or ""
            ):
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} mismatches StrategyGroup version"
                )
            if event.get("side") not in _as_list(version.get("supported_sides")):
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} side is not supported by StrategyGroup version"
                )
            if event.get("timeframe") not in _as_list(version.get("supported_timeframes")):
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} timeframe is not supported by StrategyGroup version"
                )
            if not _event_id_matches_side(
                strategy_group_id=str(event.get("strategy_group_id") or ""),
                event_id=str(event.get("event_id") or ""),
                side=str(event.get("side") or ""),
            ):
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} event_id is not side-specific"
                )
            event_key = (
                str(event.get("strategy_group_id") or ""),
                str(event.get("side") or ""),
                str(event.get("event_id") or ""),
            )
            if event_key in seen_event_keys:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} duplicates current event identity"
                )
            seen_event_keys.add(event_key)
            event_spec_version = str(event.get("event_spec_version") or "").strip()
            if not event_spec_version:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} missing event_spec_version"
                )
            if not event_spec_id.endswith(f":{event_spec_version}"):
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} mismatches event_spec_version="
                    f"{event_spec_version}"
                )
            if int(event.get("freshness_window_ms") or 0) <= 0:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} freshness_window_ms must be positive"
                )

        self._validate_event_required_facts(rows, current_events)

    def _validate_event_required_facts(
        self,
        rows: dict[str, list[dict[str, Any]]],
        current_events: dict[str, dict[str, Any]],
    ) -> None:
        facts_by_event: dict[str, list[dict[str, Any]]] = {}
        for row in rows["strategy_event_required_facts"]:
            if row.get("status") != "current":
                continue
            event_spec_id = str(row.get("event_spec_id") or "")
            facts_by_event.setdefault(event_spec_id, []).append(row)

        contract_keys = {
            (
                str(row.get("strategy_group_version_id") or ""),
                str(row.get("fact_key") or ""),
                str(row.get("required_surface") or ""),
            )
            for row in rows["required_fact_contracts"]
        }
        required_manifest_by_event: dict[tuple[str, str], set[str]] = {}
        disable_manifest_by_event: dict[tuple[str, str], set[str]] = {}
        for row in rows["required_fact_contracts"]:
            if row.get("required_for_live_submit") is not True:
                continue
            payload = _as_dict(row.get("definition_payload"))
            fact_role = str(payload.get("fact_role") or "required")
            version_id = str(row.get("strategy_group_version_id") or "")
            fact_key = str(row.get("fact_key") or "")
            event_ids = {
                str(item)
                for item in payload.get("event_ids", [])
                if str(item)
            }
            if payload.get("event_id"):
                event_ids.add(str(payload["event_id"]))
            if not event_ids or not version_id or not fact_key:
                continue
            target = (
                disable_manifest_by_event
                if fact_role == "disable"
                else required_manifest_by_event
            )
            for event_id in event_ids:
                target.setdefault((version_id, event_id), set()).add(fact_key)
        bound_current_event_ids = {
            str(row.get("event_spec_id") or "")
            for row in rows["candidate_scope_event_bindings"]
            if row.get("status") == "active"
            and str(row.get("event_spec_id") or "") in current_events
        }
        for event_spec_id in bound_current_event_ids:
            facts = facts_by_event.get(event_spec_id) or []
            required_keys = {
                str(row.get("fact_key") or "")
                for row in facts
                if row.get("fact_role") == "required"
            }
            disable_keys = {
                str(row.get("fact_key") or "")
                for row in facts
                if row.get("fact_role") == "disable"
            }
            if not required_keys:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} has no required facts"
                )

            event = current_events[event_spec_id]
            event_spec_version = str(event.get("event_spec_version") or "").strip()
            protection_ref = str(event.get("protection_ref_type") or "")
            if protection_ref not in required_keys:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} protection_ref_type missing from required facts"
                )
            version_id = str(event.get("strategy_group_version_id") or "")
            event_id = str(event.get("event_id") or "")
            manifest_keys = required_manifest_by_event.get((version_id, event_id)) or set()
            if not manifest_keys:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} has no RequiredFacts manifest"
                )
            if required_keys != manifest_keys:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} RequiredFacts manifest mismatch: "
                    + _manifest_mismatch_detail(manifest_keys, required_keys)
                )
            disable_manifest_keys = (
                disable_manifest_by_event.get((version_id, event_id)) or set()
            )
            if disable_keys != disable_manifest_keys:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} disable manifest mismatch: "
                    + _manifest_mismatch_detail(disable_manifest_keys, disable_keys)
                )
            for fact in facts:
                fact_key = str(fact.get("fact_key") or "")
                if not str(fact.get("required_facts_version_id") or "").endswith(
                    f":{event_spec_version}"
                ):
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id}:{fact_key} has invalid RequiredFacts version"
                    )
                if fact.get("value_source") != "runtime_fact_snapshot":
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id}:{fact_key} must read runtime_fact_snapshot"
                    )
                if not str(fact.get("operator") or ""):
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id}:{fact_key} missing machine operator"
                    )
                if fact.get("required_for_promotion") is not True:
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id}:{fact_key} must be required_for_promotion"
                    )
                if fact.get("required_for_ticket") is not True:
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id}:{fact_key} must be required_for_ticket"
                    )
                if fact.get("required_for_finalgate") is not True:
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id}:{fact_key} must be required_for_finalgate"
                    )
                if fact.get("fact_role") == "disable" and fact.get("disable_on_match") is not True:
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id}:{fact_key} disable fact must disable_on_match"
                    )
                if fact.get("fact_role") == "required" and fact.get("disable_on_match") is not False:
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id}:{fact_key} required fact must not disable_on_match"
                    )
                if fact.get("fact_role") == "required" and (
                    version_id,
                    fact_key,
                    str(fact.get("fact_surface") or ""),
                ) not in contract_keys:
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id}:{fact_key} missing fact contract"
                    )

    def _validate_live_signal_events(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> None:
        candidates = {
            str(row.get("candidate_scope_id") or ""): row
            for row in rows["candidate_scope"]
            if row.get("status") == "active"
        }
        bindings = {
            str(row.get("candidate_scope_id") or ""): row
            for row in rows["candidate_scope_event_bindings"]
            if row.get("status") == "active"
        }
        events = {
            str(row.get("event_spec_id") or ""): row
            for row in rows["strategy_side_event_specs"]
            if row.get("status") == "current"
        }
        for signal in rows["live_signal_events"]:
            if not is_current_live_signal(signal, self.now_ms):
                continue
            signal_id = str(signal.get("signal_event_id") or "")
            candidate_id = str(signal.get("candidate_scope_id") or "")
            candidate = candidates.get(candidate_id)
            if not candidate:
                raise RuntimeControlStateRepositoryError(
                    f"{signal_id} has no active candidate scope"
                )
            binding = bindings.get(candidate_id)
            event = events.get(str(signal.get("event_spec_id") or ""))
            if not binding or not event:
                raise RuntimeControlStateRepositoryError(
                    f"{signal_id} has no active event binding/current event spec"
                )
            if str(binding.get("event_spec_id") or "") != str(signal.get("event_spec_id") or ""):
                raise RuntimeControlStateRepositoryError(
                    f"{signal_id} mismatches candidate event spec"
                )
            for key in ("strategy_group_id", "symbol", "side"):
                if str(signal.get(key) or "") != str(candidate.get(key) or ""):
                    raise RuntimeControlStateRepositoryError(
                        f"{signal_id} mismatches candidate {key}"
                    )
            if str(signal.get("signal_type") or "") != str(event.get("event_id") or ""):
                raise RuntimeControlStateRepositoryError(
                    f"{signal_id} signal_type must equal event_id"
                )
            event_time_ms = int(signal.get("event_time_ms") or 0)
            trigger_ms = int(signal.get("trigger_candle_close_time_ms") or 0)
            created_ms = int(signal.get("created_at_ms") or 0)
            if event_time_ms <= 0 or trigger_ms <= 0:
                raise RuntimeControlStateRepositoryError(
                    f"{signal_id} missing event time authority"
                )
            if event_time_ms != trigger_ms:
                raise RuntimeControlStateRepositoryError(
                    f"{signal_id} event_time_ms must equal trigger_candle_close_time_ms"
                )
            if created_ms == event_time_ms:
                raise RuntimeControlStateRepositoryError(
                    f"{signal_id} uses generated_at as event_time"
                )
            if (
                signal.get("status") == "facts_validated"
                and signal.get("freshness_state") == "fresh"
                and signal.get("source_kind") != "live_market"
            ):
                raise RuntimeControlStateRepositoryError(
                    f"{signal_id} fresh signal must be live_market"
                )

    def _validate_promotion_and_lane_identity(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> None:
        signals = {
            str(row.get("signal_event_id") or ""): row
            for row in rows["live_signal_events"]
        }
        readiness = {
            str(row.get("readiness_row_id") or ""): row
            for row in rows["pretrade_readiness_rows"]
        }
        promotions = {
            str(row.get("promotion_candidate_id") or ""): row
            for row in rows["promotion_candidates"]
        }
        open_winners = [
            row
            for row in rows["promotion_candidates"]
            if row.get("status") == "arbitration_won"
            and is_current_promotion_candidate(row, self.now_ms)
        ]
        if len(open_winners) > 1:
            raise RuntimeControlStateRepositoryError(
                "multiple open arbitration_won promotion candidates"
            )

        for promotion in rows["promotion_candidates"]:
            if not is_current_promotion_candidate(promotion, self.now_ms):
                continue
            promotion_id = str(promotion.get("promotion_candidate_id") or "")
            signal = signals.get(str(promotion.get("signal_event_id") or ""))
            row = readiness.get(str(promotion.get("readiness_row_id") or ""))
            if not signal:
                raise RuntimeControlStateRepositoryError(
                    f"{promotion_id} has no live signal event"
                )
            if not row:
                raise RuntimeControlStateRepositoryError(
                    f"{promotion_id} has no readiness row"
                )
            for key in ("strategy_group_id", "symbol", "side"):
                if str(promotion.get(key) or "") != str(signal.get(key) or ""):
                    raise RuntimeControlStateRepositoryError(
                        f"{promotion_id} mismatches signal {key}"
                    )
                if str(promotion.get(key) or "") != str(row.get(key) or ""):
                    raise RuntimeControlStateRepositoryError(
                        f"{promotion_id} mismatches readiness {key}"
                    )
            if promotion.get("status") == "arbitration_won":
                if signal.get("status") != "facts_validated":
                    raise RuntimeControlStateRepositoryError(
                        f"{promotion_id} winner signal is not facts_validated"
                    )
                if signal.get("freshness_state") != "fresh":
                    raise RuntimeControlStateRepositoryError(
                        f"{promotion_id} winner signal is not fresh"
                    )
                if signal.get("source_kind") != "live_market":
                    raise RuntimeControlStateRepositoryError(
                        f"{promotion_id} winner signal is not live_market"
                    )

        open_real_lanes = [
            row
            for row in rows["action_time_lane_inputs"]
            if is_current_action_time_lane(row, self.now_ms)
        ]
        if len(open_real_lanes) > 1:
            raise RuntimeControlStateRepositoryError(
                "multiple open real-submit action-time lanes"
            )
        for lane in rows["action_time_lane_inputs"]:
            if not is_current_action_time_lane(lane, self.now_ms):
                continue
            lane_id = str(lane.get("action_time_lane_input_id") or "")
            promotion = promotions.get(str(lane.get("promotion_candidate_id") or ""))
            signal = signals.get(str(lane.get("signal_event_id") or ""))
            if not promotion:
                raise RuntimeControlStateRepositoryError(
                    f"{lane_id} has no promotion candidate"
                )
            if not signal:
                raise RuntimeControlStateRepositoryError(
                    f"{lane_id} has no live signal event"
                )
            if promotion.get("status") != "arbitration_won":
                raise RuntimeControlStateRepositoryError(
                    f"{lane_id} does not reference arbitration_won promotion"
                )
            if str(promotion.get("signal_event_id") or "") != str(lane.get("signal_event_id") or ""):
                raise RuntimeControlStateRepositoryError(
                    f"{lane_id} mismatches promotion signal_event_id"
                )
            for key in ("strategy_group_id", "symbol", "side"):
                if str(lane.get(key) or "") != str(promotion.get(key) or ""):
                    raise RuntimeControlStateRepositoryError(
                        f"{lane_id} mismatches promotion {key}"
                    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _texts(values: Any) -> set[str]:
    return {str(value) for value in values if str(value or "")}


def _monitor_bounded_statement(
    statement: sa.sql.Select[Any],
    table: sa.Table,
    logical_key: str,
    *,
    now_ms: int,
) -> sa.sql.Select[Any]:
    columns = table.c
    if logical_key == "watcher_runtime_coverage" and "is_current" in columns:
        return statement.where(columns.is_current.is_(True))
    if logical_key == "runtime_fact_snapshots":
        statement = statement.where(
            sa.and_(
                columns.freshness_state == "fresh",
                columns.valid_until_ms.is_not(None),
                columns.valid_until_ms > now_ms,
            )
        )
        if "created_at_ms" in columns:
            statement = statement.order_by(columns.created_at_ms.desc()).limit(1000)
        return statement
    if logical_key == "live_signal_events":
        statement = statement.where(
            sa.and_(
                columns.status == "facts_validated",
                columns.freshness_state == "fresh",
                columns.source_kind == "live_market",
                columns.invalidated_at_ms.is_(None),
                columns.expires_at_ms.is_not(None),
                columns.expires_at_ms > now_ms,
            )
        )
        if "observed_at_ms" in columns:
            statement = statement.order_by(columns.observed_at_ms.desc()).limit(200)
        return statement
    if logical_key == "promotion_candidates":
        return statement.where(
            sa.and_(
                columns.status.in_(
                    ["eligible", "arbitration_pending", "arbitration_won"]
                ),
                columns.closed_at_ms.is_(None),
                columns.expires_at_ms.is_not(None),
                columns.expires_at_ms > now_ms,
            )
        )
    if logical_key == "action_time_lane_inputs":
        return statement.where(
            sa.and_(
                columns.lane_scope == "real_submit_candidate",
                columns.status.in_(list(OPEN_REAL_LANE_STATUSES)),
                columns.closed_at_ms.is_(None),
                columns.expires_at_ms.is_not(None),
                columns.expires_at_ms > now_ms,
            )
        )
    if logical_key == "action_time_tickets":
        return statement.where(
            sa.and_(
                sa.or_(
                    sa.and_(
                        columns.status.in_(["created", "preflight_pending", "finalgate_ready"]),
                        columns.expires_at_ms.is_not(None),
                        columns.expires_at_ms > now_ms,
                    ),
                    columns.status == "submitted",
                ),
            )
        )
    if logical_key == "projection_runs":
        statement = statement.where(
            sa.and_(
                columns.projection_target == "production_current",
                columns.status == "succeeded",
            )
        )
        if "finished_at_ms" in columns:
            statement = statement.order_by(columns.finished_at_ms.desc()).limit(100)
        return statement
    if logical_key == "control_read_model_snapshots" and "is_current" in columns:
        statement = statement.where(columns.is_current.is_(True))
        if "generated_at_ms" in columns:
            statement = statement.order_by(columns.generated_at_ms.desc()).limit(50)
        return statement
    if logical_key == "server_monitor_runs" and "created_at_ms" in columns:
        return statement.order_by(columns.created_at_ms.desc()).limit(200)
    if logical_key == "ticket_bound_protected_submit_attempts" and "created_at_ms" in columns:
        return statement.where(
            columns.status.in_(
                [
                    "blocked",
                    "disabled_smoke_passed",
                    "submitted",
                    "submit_outcome_unknown",
                    "hard_stopped",
                ]
            )
        ).order_by(columns.created_at_ms.desc()).limit(200)
    if logical_key == "ticket_bound_exchange_commands" and "updated_at_ms" in columns:
        return statement.where(
            columns.command_state.in_(
                ["dispatching", "outcome_unknown", "hard_stopped"]
            )
        ).order_by(columns.updated_at_ms.desc()).limit(200)
    if logical_key == "runtime_process_outcomes" and "updated_at_ms" in columns:
        return statement.order_by(columns.updated_at_ms.desc()).limit(200)
    if logical_key == "ticket_bound_order_lifecycle_runs" and "updated_at_ms" in columns:
        return statement.where(
            ~columns.status.in_(
                [
                    "position_protected",
                    "runner_protected",
                    "reconciliation_matched",
                    "budget_settled",
                    "review_recorded",
                    "lifecycle_closed",
                ]
            )
        ).order_by(columns.updated_at_ms.desc()).limit(200)
    return statement


def _is_monitor_current_ticket(row: dict[str, Any], now_ms: int) -> bool:
    status = str(row.get("status") or "")
    if status == "submitted":
        return True
    if status not in {"created", "preflight_pending", "finalgate_ready"}:
        return False
    return int(row.get("expires_at_ms") or 0) > now_ms


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _manifest_mismatch_detail(
    expected_keys: set[str],
    actual_keys: set[str],
) -> str:
    missing = sorted(expected_keys - actual_keys)
    unexpected = sorted(actual_keys - expected_keys)
    return f"missing={missing}; unexpected={unexpected}"


def _event_id_matches_side(
    *,
    strategy_group_id: str,
    event_id: str,
    side: str,
) -> bool:
    if side not in {"long", "short"}:
        return False
    strategy_prefix = strategy_group_id.split("-", 1)[0].strip().upper()
    expected_suffix = side.upper()
    return bool(strategy_prefix) and event_id == f"{strategy_prefix}-{expected_suffix}"


def is_current_live_signal(row: dict[str, Any], now_ms: int) -> bool:
    return (
        row.get("status") == "facts_validated"
        and row.get("freshness_state") == "fresh"
        and row.get("source_kind") == "live_market"
        and row.get("invalidated_at_ms") is None
        and row.get("expires_at_ms") is not None
        and int(row.get("expires_at_ms") or 0) > now_ms
    )


def is_current_promotion_candidate(row: dict[str, Any], now_ms: int) -> bool:
    return (
        row.get("closed_at_ms") is None
        and row.get("status")
        in {"eligible", "arbitration_pending", "arbitration_won"}
        and row.get("expires_at_ms") is not None
        and int(row.get("expires_at_ms") or 0) > now_ms
    )


def is_current_action_time_lane(row: dict[str, Any], now_ms: int) -> bool:
    return (
        row.get("lane_scope") == "real_submit_candidate"
        and row.get("status") in OPEN_REAL_LANE_STATUSES
        and row.get("closed_at_ms") is None
        and row.get("expires_at_ms") is not None
        and int(row.get("expires_at_ms") or 0) > now_ms
    )


def is_current_action_time_ticket(row: dict[str, Any], now_ms: int) -> bool:
    if row.get("status") == "submitted":
        return True
    return (
        row.get("status") in {"created", "preflight_pending", "finalgate_ready"}
        and row.get("expires_at_ms") is not None
        and int(row.get("expires_at_ms") or 0) > now_ms
    )


def is_current_fact_snapshot(row: dict[str, Any], now_ms: int) -> bool:
    return (
        row.get("freshness_state") == "fresh"
        and row.get("valid_until_ms") is not None
        and int(row.get("valid_until_ms") or 0) > now_ms
    )
