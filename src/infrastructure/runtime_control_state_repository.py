"""Runtime control-state repository boundary.

Runtime/control authority is DB-backed only. Historical JSON/Markdown material is
archive provenance and must not be exposed through this current repository.
"""

from __future__ import annotations

from decimal import Decimal
import time
from typing import Any

import sqlalchemy as sa

from src.application.action_time.capability_certification import (
    ActionTimeFactDigestRowV1,
)
from src.application.readmodels.watcher_candidate_universe import (
    WatcherCandidateEventBindingRow,
    WatcherCandidateScopeRow,
    WatcherCandidateUniverseCurrentProjection,
    WatcherRuntimeScopeBindingRow,
    WatcherStrategySideEventSpecRow,
)

from src.application.action_time.identity_conservation import (
    RuntimeLaneIdentityConservationError,
    require_runtime_lane_lineage_match,
    runtime_lane_identity_from_live_signal,
    runtime_lane_lineage_from_record,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentityMismatch


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

RUNTIME_LANE_IDENTITY_COLUMN_SENTINELS = (
    "candidate_scope_event_binding_id",
    "runtime_instance_id",
    "lane_identity_key",
    "source_watermark",
)

WATCHER_CANDIDATE_PROFILE: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "candidate_scope": (
        "brc_strategy_group_candidate_scope",
        "active",
        (
        "candidate_scope_id",
        "strategy_group_id",
        "symbol",
        "asset_class",
        "side",
        "policy_current_id",
        "status",
        ),
    ),
    "candidate_scope_event_bindings": (
        "brc_candidate_scope_event_bindings",
        "active",
        (
        "binding_id",
        "candidate_scope_id",
        "event_spec_id",
        "strategy_group_id",
        "symbol",
        "side",
        "status",
        ),
    ),
    "runtime_scope_bindings": (
        "brc_runtime_scope_bindings",
        "active",
        (
        "runtime_scope_binding_id",
        "candidate_scope_id",
        "strategy_group_id",
        "symbol",
        "side",
        "runtime_profile_id",
        "status",
        ),
    ),
    "strategy_side_event_specs": (
        "brc_strategy_side_event_specs",
        "current",
        (
        "event_spec_id",
        "strategy_group_id",
        "strategy_group_version_id",
        "event_spec_version",
        "event_id",
        "side",
        "timeframe",
        "time_authority",
        "status",
        ),
    ),
}

DEPLOY_VALIDATION_OWNERSHIP_COLUMNS = (
    "projection_key",
    "model_type",
    "projection_scope_key",
    "owner_projector",
    "legacy_writer_allowed",
    "current_source_mode",
    "updated_at_ms",
)

ACTION_TIME_FACT_DIGEST_COLUMNS = (
    "fact_snapshot_id",
    "strategy_group_id",
    "symbol",
    "side",
    "runtime_profile_id",
    "fact_surface",
    "source_kind",
    "source_ref",
    "computed",
    "satisfied",
    "freshness_state",
    "blocker_class",
    "observed_at_ms",
    "valid_until_ms",
)

CAPABILITY_CERTIFICATION_COLUMNS: dict[str, tuple[str, ...]] = {
    "strategy_groups": (
        "strategy_group_id",
        "current_version_id",
        "status",
    ),
    "strategy_group_versions": (
        "strategy_group_version_id",
        "strategy_group_id",
        "status",
    ),
    "strategy_runtime_instances": (
        "runtime_instance_id",
        "strategy_family_id",
        "strategy_family_version_id",
        "symbol",
        "side",
        "status",
    ),
    "candidate_scope": (
        "candidate_scope_id",
        "strategy_group_id",
        "symbol",
        "asset_class",
        "side",
        "policy_current_id",
        "priority_rank",
        "status",
    ),
    "candidate_scope_event_bindings": (
        "binding_id",
        "candidate_scope_id",
        "event_spec_id",
        "strategy_group_id",
        "symbol",
        "side",
        "status",
    ),
    "runtime_scope_bindings": (
        "runtime_scope_binding_id",
        "candidate_scope_id",
        "strategy_group_id",
        "symbol",
        "side",
        "policy_current_id",
        "runtime_profile_id",
        "selected_strategygroup_scope",
        "symbol_side_scope_closed",
        "notional_leverage_scope_closed",
        "live_submit_allowed",
        "server_runtime_coverage_required",
        "status",
    ),
    "strategy_side_event_specs": (
        "event_spec_id",
        "strategy_group_id",
        "strategy_group_version_id",
        "event_spec_version",
        "event_id",
        "side",
        "timeframe",
        "execution_eligibility_enabled",
        "declared_signal_grade",
        "declared_required_execution_mode",
        "freshness_window_ms",
        "time_authority",
        "protection_ref_type",
        "status",
    ),
    "owner_policy_current": (
        "policy_current_id",
        "strategy_group_id",
        "symbol",
        "side",
        "runtime_profile_id",
        "enabled_state",
        "pretrade_candidate_allowed",
        "action_time_rehearsal_allowed",
        "live_submit_allowed",
        "planned_stop_risk_fraction",
        "max_initial_margin_utilization",
        "max_leverage",
        "attempt_cap",
    ),
    "strategy_event_required_facts": (
        "event_required_fact_id",
        "event_spec_id",
        "required_facts_version_id",
        "fact_key",
        "fact_role",
        "fact_surface",
        "operator",
        "disable_on_match",
        "freshness_ms",
        "required_for_promotion",
        "required_for_ticket",
        "required_for_finalgate",
        "missing_blocker_class",
        "failed_blocker_class",
        "value_source",
        "status",
    ),
    "runtime_process_outcomes": (
        "process_outcome_id",
        "process_name",
        "scope_key",
        "process_state",
        "runtime_head",
        "source_watermark",
        "updated_at_ms",
    ),
}

CAPABILITY_CERTIFICATION_TABLES: dict[str, str] = {
    "strategy_groups": "brc_strategy_groups",
    "strategy_group_versions": "brc_strategy_group_versions",
    "strategy_runtime_instances": "strategy_runtime_instances",
    "candidate_scope": "brc_strategy_group_candidate_scope",
    "candidate_scope_event_bindings": "brc_candidate_scope_event_bindings",
    "runtime_scope_bindings": "brc_runtime_scope_bindings",
    "strategy_side_event_specs": "brc_strategy_side_event_specs",
    "owner_policy_current": "brc_owner_policy_current",
    "strategy_event_required_facts": "brc_strategy_event_required_facts",
    "runtime_process_outcomes": "brc_runtime_process_outcomes",
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
        self._validate_watcher_candidate_universe_current(
            _watcher_current_rows(rows)
        )
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
        return self._read_bounded_current_state(
            read_profile="monitor_bounded_current",
        )

    def read_watcher_candidate_universe_current(
        self,
        *,
        row_limit_per_table: int = 256,
    ) -> WatcherCandidateUniverseCurrentProjection:
        if row_limit_per_table < 1:
            raise RuntimeControlStateRepositoryError(
                "watcher_candidate_row_limit_must_be_positive"
            )
        self._configure_read_only_profile()
        inspector = sa.inspect(self.conn)
        existing = set(inspector.get_table_names())
        missing = sorted(
            table_name
            for table_name, _status, _columns in WATCHER_CANDIDATE_PROFILE.values()
            if table_name not in existing
        )
        if missing:
            raise RuntimeControlStateRepositoryError(
                "PG watcher candidate tables missing: " + ", ".join(missing)
            )
        rows: dict[str, list[dict[str, Any]]] = {}
        for logical_key, (
            table_name,
            status,
            column_names,
        ) in WATCHER_CANDIDATE_PROFILE.items():
            metadata = sa.MetaData()
            table = sa.Table(table_name, metadata, autoload_with=self.conn)
            missing_columns = [name for name in column_names if name not in table.c]
            if missing_columns:
                raise RuntimeControlStateRepositoryError(
                    f"watcher_candidate_schema_invalid:{logical_key}:"
                    + ",".join(missing_columns)
                )
            statement = (
                sa.select(*(table.c[name] for name in column_names))
                .where(table.c.status == status)
                .order_by(*table.primary_key.columns)
                .limit(row_limit_per_table + 1)
            )
            selected = [
                {key: _json_safe(value) for key, value in row.items()}
                for row in self.conn.execute(statement).mappings()
            ]
            if len(selected) > row_limit_per_table:
                raise RuntimeControlStateRepositoryError(
                    f"watcher_candidate_row_limit_exceeded:{logical_key}:"
                    f"{row_limit_per_table}"
                )
            rows[logical_key] = selected

        self._validate_watcher_candidate_universe_current(rows)
        return WatcherCandidateUniverseCurrentProjection(
            read_now_ms=self.now_ms,
            candidate_scope=tuple(
                WatcherCandidateScopeRow.model_validate(row)
                for row in rows["candidate_scope"]
            ),
            candidate_scope_event_bindings=tuple(
                WatcherCandidateEventBindingRow.model_validate(row)
                for row in rows["candidate_scope_event_bindings"]
            ),
            runtime_scope_bindings=tuple(
                WatcherRuntimeScopeBindingRow.model_validate(row)
                for row in rows["runtime_scope_bindings"]
            ),
            strategy_side_event_specs=tuple(
                WatcherStrategySideEventSpecRow.model_validate(row)
                for row in rows["strategy_side_event_specs"]
            ),
        )

    def _validate_watcher_candidate_universe_current(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> None:
        _validate_watcher_candidate_universe(rows)

    def read_deploy_validation_state(
        self,
        *,
        row_limit_per_table: int = 256,
    ) -> dict[str, Any]:
        if row_limit_per_table < 1:
            raise RuntimeControlStateRepositoryError(
                "deploy_validation_row_limit_must_be_positive"
            )
        self._configure_read_only_profile()
        inspector = sa.inspect(self.conn)
        required_tables = {
            table_name
            for table_name, _status, _columns in WATCHER_CANDIDATE_PROFILE.values()
        } | {CONTROL_STATE_TABLES["current_projection_ownership"]}
        existing = set(inspector.get_table_names())
        missing = sorted(required_tables - existing)
        if missing:
            raise RuntimeControlStateRepositoryError(
                "PG deploy validation tables missing: " + ", ".join(missing)
            )

        rows: dict[str, list[dict[str, Any]]] = {}
        for logical_key, (
            table_name,
            status,
            column_names,
        ) in WATCHER_CANDIDATE_PROFILE.items():
            rows[logical_key] = self._read_explicit_bounded_rows(
                logical_key=logical_key,
                table_name=table_name,
                column_names=column_names,
                predicate=lambda table, status=status: table.c.status == status,
                row_limit=row_limit_per_table,
                overflow_prefix="deploy_validation_row_limit_exceeded",
            )

        ownership_table = CONTROL_STATE_TABLES["current_projection_ownership"]
        rows["current_projection_ownership"] = self._read_explicit_bounded_rows(
            logical_key="current_projection_ownership",
            table_name=ownership_table,
            column_names=DEPLOY_VALIDATION_OWNERSHIP_COLUMNS,
            predicate=lambda table: table.c.projection_key.is_not(None),
            row_limit=row_limit_per_table,
            overflow_prefix="deploy_validation_row_limit_exceeded",
        )

        self._validate_watcher_candidate_universe_current(
            {key: rows[key] for key in WATCHER_CANDIDATE_PROFILE}
        )
        self._validate_projection_ownership(
            {
                "current_projection_ownership": rows[
                    "current_projection_ownership"
                ],
                "projection_runs": [],
            }
        )
        return {
            "schema": "brc.runtime_control_state_deploy_validation.v1",
            "source_mode": self.source_mode,
            "projection_target": self.projection_target,
            "read_profile": "deploy_validation",
            "read_now_ms": self.now_ms,
            "strategy_group_count": len(
                {
                    str(row["strategy_group_id"])
                    for row in rows["candidate_scope"]
                }
            ),
            "table_counts": {key: len(value) for key, value in rows.items()},
            **rows,
        }

    def _configure_read_only_profile(self) -> None:
        if self.conn.dialect.name != "postgresql":
            return
        self.conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        self.conn.exec_driver_sql("SET LOCAL lock_timeout = '1s'")
        self.conn.exec_driver_sql("SET LOCAL statement_timeout = '5s'")

    def read_action_time_capability_certification_state(
        self,
        *,
        identity_limit: int = 256,
        fact_limit: int = 2048,
    ) -> dict[str, Any]:
        return self._read_action_time_capability_certification_state(
            identity_limit=identity_limit,
            fact_limit=fact_limit,
            read_only=True,
        )

    def reread_action_time_capability_certification_state_for_apply(
        self,
        *,
        identity_limit: int = 256,
        fact_limit: int = 2048,
    ) -> dict[str, Any]:
        return self._read_action_time_capability_certification_state(
            identity_limit=identity_limit,
            fact_limit=fact_limit,
            read_only=False,
        )

    def _read_action_time_capability_certification_state(
        self,
        *,
        identity_limit: int,
        fact_limit: int,
        read_only: bool,
    ) -> dict[str, Any]:
        if identity_limit < 1 or fact_limit < 1:
            raise RuntimeControlStateRepositoryError(
                "capability_certification_row_limit_must_be_positive"
            )
        if read_only:
            self._configure_read_only_profile()
        elif self.conn.dialect.name == "postgresql":
            self.conn.exec_driver_sql("SET LOCAL lock_timeout = '1s'")
            self.conn.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
        existing = set(sa.inspect(self.conn).get_table_names())
        missing = sorted(set(CAPABILITY_CERTIFICATION_TABLES.values()) - existing)
        if missing:
            raise RuntimeControlStateRepositoryError(
                "PG capability certification tables missing: " + ", ".join(missing)
            )

        tables = {
            key: sa.Table(table_name, sa.MetaData(), autoload_with=self.conn)
            for key, table_name in CAPABILITY_CERTIFICATION_TABLES.items()
        }

        candidate_table = tables["candidate_scope"]
        candidates = self._execute_capability_statement(
            logical_key="candidate_scope",
            statement=(
                self._capability_select(candidate_table, "candidate_scope")
                .where(candidate_table.c.status == "active")
                .order_by(*candidate_table.primary_key.columns)
                .limit(identity_limit + 1)
            ),
            row_limit=identity_limit,
        )
        if not candidates:
            raise RuntimeControlStateRepositoryError(
                "capability_certification_active_candidate_scope_missing"
            )

        candidate_ids = sorted(
            {str(row["candidate_scope_id"]) for row in candidates}
        )
        group_ids = sorted({str(row["strategy_group_id"]) for row in candidates})
        policy_ids = sorted({str(row["policy_current_id"]) for row in candidates})
        lane_keys = sorted(
            {
                (
                    str(row["strategy_group_id"]),
                    str(row["symbol"]),
                    str(row["side"]),
                )
                for row in candidates
            }
        )

        group_table = tables["strategy_groups"]
        groups = self._execute_capability_statement(
            logical_key="strategy_groups",
            statement=(
                self._capability_select(group_table, "strategy_groups")
                .where(
                    group_table.c.status == "active",
                    group_table.c.strategy_group_id.in_(group_ids),
                )
                .order_by(*group_table.primary_key.columns)
                .limit(identity_limit + 1)
            ),
            row_limit=identity_limit,
        )
        version_ids = sorted({str(row["current_version_id"]) for row in groups})

        version_table = tables["strategy_group_versions"]
        versions = self._execute_capability_statement(
            logical_key="strategy_group_versions",
            statement=(
                self._capability_select(version_table, "strategy_group_versions")
                .where(
                    version_table.c.status == "current",
                    version_table.c.strategy_group_version_id.in_(version_ids),
                )
                .order_by(*version_table.primary_key.columns)
                .limit(identity_limit + 1)
            ),
            row_limit=identity_limit,
        )

        runtime_instance_table = tables["strategy_runtime_instances"]
        runtimes = self._execute_capability_statement(
            logical_key="strategy_runtime_instances",
            statement=(
                self._capability_select(
                    runtime_instance_table,
                    "strategy_runtime_instances",
                )
                .where(
                    runtime_instance_table.c.status == "active",
                    sa.tuple_(
                        runtime_instance_table.c.strategy_family_id,
                        runtime_instance_table.c.symbol,
                        runtime_instance_table.c.side,
                    ).in_(lane_keys),
                )
                .order_by(*runtime_instance_table.primary_key.columns)
                .limit(identity_limit + 1)
            ),
            row_limit=identity_limit,
        )

        binding_table = tables["candidate_scope_event_bindings"]
        event_bindings = self._execute_capability_statement(
            logical_key="candidate_scope_event_bindings",
            statement=(
                self._capability_select(
                    binding_table,
                    "candidate_scope_event_bindings",
                )
                .where(
                    binding_table.c.status == "active",
                    binding_table.c.candidate_scope_id.in_(candidate_ids),
                )
                .order_by(*binding_table.primary_key.columns)
                .limit(identity_limit + 1)
            ),
            row_limit=identity_limit,
        )
        event_ids = sorted({str(row["event_spec_id"]) for row in event_bindings})

        runtime_binding_table = tables["runtime_scope_bindings"]
        runtime_bindings = self._execute_capability_statement(
            logical_key="runtime_scope_bindings",
            statement=(
                self._capability_select(
                    runtime_binding_table,
                    "runtime_scope_bindings",
                    guarded_json=("conditional_hard_gates", 16_384),
                )
                .where(
                    runtime_binding_table.c.status == "active",
                    runtime_binding_table.c.candidate_scope_id.in_(candidate_ids),
                )
                .order_by(*runtime_binding_table.primary_key.columns)
                .limit(identity_limit + 1)
            ),
            row_limit=identity_limit,
        )

        event_table = tables["strategy_side_event_specs"]
        events = self._execute_capability_statement(
            logical_key="strategy_side_event_specs",
            statement=(
                self._capability_select(event_table, "strategy_side_event_specs")
                .where(
                    event_table.c.status == "current",
                    event_table.c.event_spec_id.in_(event_ids),
                )
                .order_by(*event_table.primary_key.columns)
                .limit(identity_limit + 1)
            ),
            row_limit=identity_limit,
        )

        policy_table = tables["owner_policy_current"]
        policies = self._execute_capability_statement(
            logical_key="owner_policy_current",
            statement=(
                self._capability_select(
                    policy_table,
                    "owner_policy_current",
                    guarded_json=("policy_event_ids", 16_384),
                )
                .where(policy_table.c.policy_current_id.in_(policy_ids))
                .order_by(*policy_table.primary_key.columns)
                .limit(identity_limit + 1)
            ),
            row_limit=identity_limit,
        )

        fact_table = tables["strategy_event_required_facts"]
        facts = self._execute_capability_statement(
            logical_key="strategy_event_required_facts",
            statement=(
                self._capability_select(
                    fact_table,
                    "strategy_event_required_facts",
                    guarded_json=("expected_value", 4_096),
                )
                .where(
                    fact_table.c.status == "current",
                    fact_table.c.event_spec_id.in_(event_ids),
                )
                .order_by(*fact_table.primary_key.columns)
                .limit(fact_limit + 1)
            ),
            row_limit=fact_limit,
        )
        expected_value_bytes = sum(
            int(row.get("expected_value_bytes") or 0) for row in facts
        )
        if expected_value_bytes > 8 * 1024 * 1024:
            raise RuntimeControlStateRepositoryError(
                "capability_certification_expected_value_total_bytes_exceeded"
            )

        outcome_table = tables["runtime_process_outcomes"]
        activations = self._execute_capability_statement(
            logical_key="runtime_process_outcomes",
            statement=(
                self._capability_select(
                    outcome_table,
                    "runtime_process_outcomes",
                )
                .where(
                    outcome_table.c.process_name == "runtime_release_activation",
                    outcome_table.c.scope_key == "production:tokyo",
                    outcome_table.c.process_state == "succeeded",
                )
                .order_by(
                    outcome_table.c.updated_at_ms.desc(),
                    outcome_table.c.process_outcome_id.desc(),
                )
                .limit(2)
            ),
            row_limit=1,
        )
        if len(activations) != 1:
            raise RuntimeControlStateRepositoryError(
                "capability_certification_release_activation_not_unique"
            )

        state = {
            "strategy_groups": groups,
            "strategy_group_versions": versions,
            "strategy_runtime_instances": runtimes,
            "candidate_scope": candidates,
            "candidate_scope_event_bindings": event_bindings,
            "runtime_scope_bindings": runtime_bindings,
            "strategy_side_event_specs": events,
            "owner_policy_current": policies,
            "strategy_event_required_facts": facts,
            "runtime_process_outcomes": activations,
        }
        self._validate_watcher_candidate_universe_current(
            {key: state[key] for key in WATCHER_CANDIDATE_PROFILE}
        )
        _validate_capability_runtime_instances(state)
        for row in runtime_bindings:
            _require_guarded_json_bytes(row, "conditional_hard_gates", 16_384)
        for row in policies:
            _require_guarded_json_bytes(row, "policy_event_ids", 16_384)
        for row in facts:
            _require_guarded_json_bytes(row, "expected_value", 4_096)
        return {
            "schema": "brc.action_time_capability_certification_state.v1",
            "source_mode": self.source_mode,
            "projection_target": self.projection_target,
            "read_profile": "action_time_capability_certification",
            "read_now_ms": self.now_ms,
            "current_runtime_head": str(activations[0]["runtime_head"]),
            "table_counts": {key: len(value) for key, value in state.items()},
            **state,
        }

    def _capability_select(
        self,
        table: sa.Table,
        logical_key: str,
        *,
        guarded_json: tuple[str, int] | None = None,
    ) -> sa.sql.Select:
        column_names = CAPABILITY_CERTIFICATION_COLUMNS[logical_key]
        missing = [name for name in column_names if name not in table.c]
        if guarded_json and guarded_json[0] not in table.c:
            missing.append(guarded_json[0])
        if missing:
            raise RuntimeControlStateRepositoryError(
                f"capability_certification_schema_invalid:{logical_key}:"
                + ",".join(missing)
            )
        selected: list[Any] = [table.c[name] for name in column_names]
        if guarded_json:
            field_name, max_bytes = guarded_json
            field = table.c[field_name]
            logical_bytes = (
                sa.func.octet_length(sa.cast(field, sa.Text))
                if self.conn.dialect.name == "postgresql"
                else sa.func.length(sa.cast(field, sa.Text))
            )
            guarded = sa.type_coerce(
                sa.case(
                    (field.is_(None), None),
                    (logical_bytes <= max_bytes, field),
                    else_=None,
                ),
                field.type,
            ).label(field_name)
            selected.extend(
                [guarded, logical_bytes.label(f"{field_name}_bytes")]
            )
        return sa.select(*selected)

    def read_action_time_fact_digest_rows(
        self,
        *,
        expected_fact_snapshot_ids: tuple[str, ...],
        row_limit: int = 128,
    ) -> tuple[ActionTimeFactDigestRowV1, ...]:
        return self._read_action_time_fact_digest_rows(
            expected_fact_snapshot_ids=expected_fact_snapshot_ids,
            row_limit=row_limit,
            read_only=True,
        )

    def reread_action_time_fact_digest_rows_for_apply(
        self,
        *,
        expected_fact_snapshot_ids: tuple[str, ...],
        row_limit: int = 128,
    ) -> tuple[ActionTimeFactDigestRowV1, ...]:
        return self._read_action_time_fact_digest_rows(
            expected_fact_snapshot_ids=expected_fact_snapshot_ids,
            row_limit=row_limit,
            read_only=False,
        )

    def _read_action_time_fact_digest_rows(
        self,
        *,
        expected_fact_snapshot_ids: tuple[str, ...],
        row_limit: int,
        read_only: bool,
    ) -> tuple[ActionTimeFactDigestRowV1, ...]:
        expected_ids = tuple(sorted(str(value or "").strip() for value in expected_fact_snapshot_ids))
        if (
            not expected_ids
            or any(not value for value in expected_ids)
            or len(set(expected_ids)) != len(expected_ids)
            or row_limit < 1
            or len(expected_ids) > row_limit
        ):
            raise RuntimeControlStateRepositoryError(
                "action_time_fact_digest_expected_id_set_invalid"
            )
        if read_only:
            self._configure_read_only_profile()
        elif self.conn.dialect.name == "postgresql":
            self.conn.exec_driver_sql("SET LOCAL lock_timeout = '1s'")
            self.conn.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
        table_name = CONTROL_STATE_TABLES["runtime_fact_snapshots"]
        if not sa.inspect(self.conn).has_table(table_name):
            raise RuntimeControlStateRepositoryError(
                "action_time_fact_digest_table_missing"
            )
        table = sa.Table(table_name, sa.MetaData(), autoload_with=self.conn)
        missing = [name for name in ACTION_TIME_FACT_DIGEST_COLUMNS if name not in table.c]
        missing.extend(
            name for name in ("failed_facts", "fact_values") if name not in table.c
        )
        if missing:
            raise RuntimeControlStateRepositoryError(
                "action_time_fact_digest_schema_invalid:" + ",".join(missing)
            )
        selected: list[Any] = [
            table.c[name] for name in ACTION_TIME_FACT_DIGEST_COLUMNS
        ]
        for field_name in ("failed_facts", "fact_values"):
            field = table.c[field_name]
            logical_bytes = (
                sa.func.octet_length(sa.cast(field, sa.Text))
                if self.conn.dialect.name == "postgresql"
                else sa.func.length(sa.cast(field, sa.Text))
            )
            selected.extend(
                [
                    sa.type_coerce(
                        sa.case(
                            (logical_bytes <= 65_536, field),
                            else_=None,
                        ),
                        field.type,
                    ).label(field_name),
                    logical_bytes.label(f"{field_name}_bytes"),
                ]
            )
        statement = (
            sa.select(*selected)
            .where(table.c.fact_snapshot_id.in_(expected_ids))
            .order_by(table.c.fact_snapshot_id)
            .limit(row_limit + 1)
        )
        raw_rows = [
            {key: _preserve_typed_value(value) for key, value in row.items()}
            for row in self.conn.execute(statement).mappings()
        ]
        if len(raw_rows) > row_limit:
            raise RuntimeControlStateRepositoryError(
                f"action_time_fact_digest_row_limit_exceeded:{row_limit}"
            )
        for row in raw_rows:
            _require_guarded_json_bytes(row, "failed_facts", 65_536)
            _require_guarded_json_bytes(row, "fact_values", 65_536)
        actual_ids = tuple(sorted(str(row["fact_snapshot_id"]) for row in raw_rows))
        if actual_ids != expected_ids:
            raise RuntimeControlStateRepositoryError(
                "action_time_fact_digest_id_set_mismatch"
            )
        models = tuple(ActionTimeFactDigestRowV1.model_validate(row) for row in raw_rows)
        canonical_size = sum(
            len(model.model_dump_json().encode("utf-8")) for model in models
        )
        if canonical_size > 1024 * 1024:
            raise RuntimeControlStateRepositoryError(
                "action_time_fact_digest_canonical_input_too_large"
            )
        return models

    def _execute_capability_statement(
        self,
        *,
        logical_key: str,
        statement: sa.sql.Select,
        row_limit: int,
    ) -> list[dict[str, Any]]:
        rows = [
            {key: _preserve_typed_value(value) for key, value in row.items()}
            for row in self.conn.execute(statement).mappings()
        ]
        if len(rows) > row_limit:
            raise RuntimeControlStateRepositoryError(
                f"capability_certification_row_limit_exceeded:{logical_key}:"
                f"{row_limit}"
            )
        return rows

    def _read_explicit_bounded_rows(
        self,
        *,
        logical_key: str,
        table_name: str,
        column_names: tuple[str, ...],
        predicate: Any,
        row_limit: int,
        overflow_prefix: str,
    ) -> list[dict[str, Any]]:
        table = sa.Table(table_name, sa.MetaData(), autoload_with=self.conn)
        missing_columns = [name for name in column_names if name not in table.c]
        if missing_columns:
            raise RuntimeControlStateRepositoryError(
                f"{overflow_prefix.replace('row_limit_exceeded', 'schema_invalid')}:"
                f"{logical_key}:" + ",".join(missing_columns)
            )
        statement = (
            sa.select(*(table.c[name] for name in column_names))
            .where(predicate(table))
            .order_by(*table.primary_key.columns)
            .limit(row_limit + 1)
        )
        selected = [
            {key: _json_safe(value) for key, value in row.items()}
            for row in self.conn.execute(statement).mappings()
        ]
        if len(selected) > row_limit:
            raise RuntimeControlStateRepositoryError(
                f"{overflow_prefix}:{logical_key}:{row_limit}"
            )
        return selected

    def read_action_time_control_state(
        self,
        *,
        ticket_id: str = "",
        protected_submit_attempt_id: str = "",
        operation_submit_command_id: str = "",
        operation_layer_handoff_id: str = "",
    ) -> dict[str, Any]:
        """Read only current PG rows suitable for the latency-sensitive path.

        Action-Time materializers must not scan historical fact and watcher
        tables. The bounded predicates are shared with the monitor because both
        consumers require current truth plus retained terminal ticket lineage,
        but the distinct profile name makes production telemetry auditable.
        """
        return self._read_bounded_current_state(
            read_profile="action_time_hot_path_current",
            requested_lineage={
                "ticket_id": ticket_id,
                "protected_submit_attempt_id": protected_submit_attempt_id,
                "operation_submit_command_id": operation_submit_command_id,
                "operation_layer_handoff_id": operation_layer_handoff_id,
            },
        )

    def _read_bounded_current_state(
        self,
        *,
        read_profile: str,
        requested_lineage: dict[str, str] | None = None,
    ) -> dict[str, Any]:
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
        self._retain_monitor_material_notification_lineage(rows)
        if requested_lineage:
            self._retain_requested_action_time_lineage(rows, **requested_lineage)
        self._validate_projection_ownership(rows)
        self._validate_active_event_semantics(rows)
        self._validate_candidate_scope_event_bindings(rows)
        self._validate_runtime_scope_bindings(rows)
        self._validate_live_signal_events(rows)
        self._validate_runtime_lane_lineage_chain(rows)
        if not any(str(value or "") for value in (requested_lineage or {}).values()):
            self._validate_promotion_and_lane_identity(rows)
        return {
            "schema": "brc.runtime_control_state_repository.v1",
            "source_mode": self.source_mode,
            "projection_target": self.projection_target,
            "read_profile": read_profile,
            "read_now_ms": self.now_ms,
            "table_counts": {key: len(value) for key, value in rows.items()},
            **rows,
        }

    def _retain_requested_action_time_lineage(
        self,
        rows: dict[str, list[dict[str, Any]]],
        *,
        ticket_id: str,
        protected_submit_attempt_id: str,
        operation_submit_command_id: str,
        operation_layer_handoff_id: str,
    ) -> None:
        ticket_ids = _texts([ticket_id])
        current_lane_ids = _texts(
            row.get("action_time_lane_input_id")
            for row in rows.get("action_time_lane_inputs") or []
        )
        tickets_for_current_lanes = self._read_rows_where_in(
            CONTROL_STATE_TABLES["action_time_tickets"],
            "action_time_lane_input_id",
            current_lane_ids,
        )
        self._merge_rows(
            rows,
            "action_time_tickets",
            "ticket_id",
            tickets_for_current_lanes,
        )
        ticket_ids.update(
            _texts(row.get("ticket_id") for row in tickets_for_current_lanes)
        )
        attempt_rows: list[dict[str, Any]] = []
        if protected_submit_attempt_id:
            attempt_rows.extend(
                self._read_rows_where_in(
                    CONTROL_STATE_TABLES["ticket_bound_protected_submit_attempts"],
                    "protected_submit_attempt_id",
                    {protected_submit_attempt_id},
                )
            )
        if operation_submit_command_id:
            attempt_rows.extend(
                self._read_rows_where_in(
                    CONTROL_STATE_TABLES["ticket_bound_protected_submit_attempts"],
                    "operation_submit_command_id",
                    {operation_submit_command_id},
                )
            )
        self._merge_rows(
            rows,
            "ticket_bound_protected_submit_attempts",
            "protected_submit_attempt_id",
            attempt_rows,
        )
        ticket_ids.update(_texts(row.get("ticket_id") for row in attempt_rows))

        handoff_rows: list[dict[str, Any]] = []
        if operation_layer_handoff_id:
            handoff_rows.extend(
                self._read_rows_where_in(
                    CONTROL_STATE_TABLES["operation_layer_handoffs"],
                    "operation_layer_handoff_id",
                    {operation_layer_handoff_id},
                )
            )
        if operation_submit_command_id:
            handoff_rows.extend(
                self._read_rows_where_in(
                    CONTROL_STATE_TABLES["operation_layer_handoffs"],
                    "operation_submit_command_id",
                    {operation_submit_command_id},
                )
            )
        if ticket_ids:
            handoff_rows.extend(
                self._read_rows_where_in(
                    CONTROL_STATE_TABLES["operation_layer_handoffs"],
                    "ticket_id",
                    ticket_ids,
                )
            )
        self._merge_rows(
            rows,
            "operation_layer_handoffs",
            "operation_layer_handoff_id",
            handoff_rows,
        )
        ticket_ids.update(_texts(row.get("ticket_id") for row in handoff_rows))
        ticket_rows = self._read_rows_where_in(
            CONTROL_STATE_TABLES["action_time_tickets"],
            "ticket_id",
            ticket_ids,
        )
        self._merge_rows(rows, "action_time_tickets", "ticket_id", ticket_rows)
        self._merge_rows(
            rows,
            "action_time_ticket_events",
            "ticket_event_id",
            self._read_rows_where_in(
                CONTROL_STATE_TABLES["action_time_ticket_events"],
                "ticket_id",
                ticket_ids,
            ),
        )

        lane_ids = _texts(row.get("action_time_lane_input_id") for row in ticket_rows)
        lane_ids.update(
            _texts(row.get("action_time_lane_input_id") for row in attempt_rows)
        )
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
        signal_ids = _texts(
            row.get("signal_event_id")
            for row in [*ticket_rows, *lane_rows, *promotion_rows]
        )
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
        fact_ids = _texts(
            row.get(key)
            for row in [*ticket_rows, *lane_rows]
            for key in (
                "public_fact_snapshot_id",
                "action_time_fact_snapshot_id",
                "account_safe_fact_snapshot_id",
                "account_mode_snapshot_id",
            )
        )
        self._merge_rows(
            rows,
            "runtime_fact_snapshots",
            "fact_snapshot_id",
            self._read_rows_where_in(
                CONTROL_STATE_TABLES["runtime_fact_snapshots"],
                "fact_snapshot_id",
                fact_ids,
            ),
        )
        for logical_key, id_column, lookup_column, values in (
            (
                "budget_reservations",
                "budget_reservation_id",
                "budget_reservation_id",
                _texts(row.get("budget_reservation_id") for row in ticket_rows),
            ),
            (
                "protection_references",
                "protection_ref_id",
                "protection_ref_id",
                _texts(row.get("protection_ref_id") for row in ticket_rows),
            ),
            (
                "runtime_safety_state",
                "runtime_safety_snapshot_id",
                "runtime_safety_snapshot_id",
                _texts(
                    row.get("runtime_safety_snapshot_id") for row in attempt_rows
                ),
            ),
            (
                "ticket_bound_submit_mode_decisions",
                "submit_mode_decision_id",
                "operation_submit_command_id",
                _texts([operation_submit_command_id]),
            ),
        ):
            self._merge_rows(
                rows,
                logical_key,
                id_column,
                self._read_rows_where_in(
                    CONTROL_STATE_TABLES[logical_key],
                    lookup_column,
                    values,
                ),
            )

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

    def _retain_monitor_material_notification_lineage(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> None:
        notifications = rows.get("server_monitor_notifications") or []
        lifecycle_rows = rows.get("ticket_bound_order_lifecycle_runs") or []
        command_rows = rows.get("ticket_bound_exchange_commands") or []
        signal_ids = {
            correlation.removeprefix("signal:")
            for row in notifications
            if (correlation := str(row.get("correlation_id") or "")).startswith(
                "signal:"
            )
        }
        ticket_ids = _texts(
            row.get("ticket_id") for row in [*lifecycle_rows, *command_rows]
        )
        ticket_ids.update(
            correlation.removeprefix("ticket:")
            for row in notifications
            if (correlation := str(row.get("correlation_id") or "")).startswith(
                "ticket:"
            )
        )
        ticket_rows = self._read_rows_where_in(
            CONTROL_STATE_TABLES["action_time_tickets"],
            "ticket_id",
            ticket_ids,
        )
        self._merge_rows(
            rows,
            "action_time_tickets",
            "ticket_id",
            ticket_rows,
        )
        signal_ids.update(_texts(row.get("signal_event_id") for row in ticket_rows))
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
            if _tracks_runtime_lane_identity(signal):
                try:
                    runtime_lane_identity_from_live_signal(signal)
                    runtime_lane_lineage_from_record(signal)
                except RuntimeLaneIdentityConservationError as exc:
                    raise RuntimeControlStateRepositoryError(
                        f"{signal_id} {exc.blocker}"
                    ) from exc

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
            action_time_invocation_id = str(
                promotion.get("action_time_invocation_id") or ""
            ).strip()
            if not signal:
                raise RuntimeControlStateRepositoryError(
                    f"{promotion_id} has no live signal event"
                )
            if action_time_invocation_id:
                expected_direct_ref = (
                    "action_time_invocation:" + action_time_invocation_id
                )
                if str(promotion.get("readiness_row_id") or "") != expected_direct_ref:
                    raise RuntimeControlStateRepositoryError(
                        f"{promotion_id} direct invocation reference mismatch"
                    )
            elif not row:
                raise RuntimeControlStateRepositoryError(
                    f"{promotion_id} has no readiness row"
                )
            for key in ("strategy_group_id", "symbol", "side"):
                if str(promotion.get(key) or "") != str(signal.get(key) or ""):
                    raise RuntimeControlStateRepositoryError(
                        f"{promotion_id} mismatches signal {key}"
                    )
                if row and str(promotion.get(key) or "") != str(row.get(key) or ""):
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
            promotion_invocation_id = str(
                promotion.get("action_time_invocation_id") or ""
            ).strip()
            lane_invocation_id = str(
                lane.get("action_time_invocation_id") or ""
            ).strip()
            if promotion_invocation_id != lane_invocation_id:
                raise RuntimeControlStateRepositoryError(
                    f"{lane_id} mismatches promotion action_time_invocation_id"
                )
            for key in ("strategy_group_id", "symbol", "side"):
                if str(lane.get(key) or "") != str(promotion.get(key) or ""):
                    raise RuntimeControlStateRepositoryError(
                        f"{lane_id} mismatches promotion {key}"
                    )

    def _validate_runtime_lane_lineage_chain(
        self,
        rows: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Apply the immutable lane lineage guard on every current handoff.

        This check stays active for requested Ticket reads.  The hot path may
        retain a narrow lineage instead of the full current pool, but it may
        never skip identity conservation merely because a Ticket ID was passed
        to the repository.
        """

        signals = {
            str(row.get("signal_event_id") or ""): row
            for row in rows["live_signal_events"]
        }
        promotions = {
            str(row.get("promotion_candidate_id") or ""): row
            for row in rows["promotion_candidates"]
        }
        lanes = {
            str(row.get("action_time_lane_input_id") or ""): row
            for row in rows["action_time_lane_inputs"]
        }

        for promotion in rows["promotion_candidates"]:
            if not is_current_promotion_candidate(promotion, self.now_ms):
                continue
            promotion_id = str(promotion.get("promotion_candidate_id") or "")
            signal = signals.get(str(promotion.get("signal_event_id") or ""))
            if signal is None:
                if _tracks_runtime_lane_identity(promotion):
                    raise RuntimeControlStateRepositoryError(
                        f"{promotion_id} "
                        "runtime_lane_identity_mismatch:signal_to_promotion_signal_missing"
                    )
                continue
            _require_current_runtime_lane_lineage(
                signal=signal,
                downstream=promotion,
                boundary="signal_to_promotion",
                entity_id=promotion_id,
            )

        for lane in rows["action_time_lane_inputs"]:
            if not is_current_action_time_lane(lane, self.now_ms):
                continue
            lane_id = str(lane.get("action_time_lane_input_id") or "")
            promotion = promotions.get(str(lane.get("promotion_candidate_id") or ""))
            signal = signals.get(str(lane.get("signal_event_id") or ""))
            if promotion is None or signal is None:
                if _tracks_runtime_lane_identity(lane):
                    missing = "promotion" if promotion is None else "signal"
                    raise RuntimeControlStateRepositoryError(
                        f"{lane_id} runtime_lane_identity_mismatch:"
                        f"promotion_to_action_time_lane_{missing}_missing"
                    )
                continue
            _require_current_runtime_lane_lineage(
                signal=signal,
                downstream=promotion,
                boundary="signal_to_promotion",
                entity_id=str(promotion.get("promotion_candidate_id") or ""),
            )
            _require_current_runtime_lane_lineage(
                signal=signal,
                downstream=lane,
                boundary="promotion_to_action_time_lane",
                entity_id=lane_id,
            )

        for ticket in rows["action_time_tickets"]:
            if ticket.get("status") not in {
                "created",
                "preflight_pending",
                "finalgate_ready",
            } or not is_current_action_time_ticket(ticket, self.now_ms):
                continue
            ticket_id = str(ticket.get("ticket_id") or "")
            lane = lanes.get(str(ticket.get("action_time_lane_input_id") or ""))
            signal = signals.get(str(ticket.get("signal_event_id") or ""))
            if lane is None or signal is None:
                if _tracks_runtime_lane_identity(ticket):
                    missing = "lane" if lane is None else "signal"
                    raise RuntimeControlStateRepositoryError(
                        f"{ticket_id} runtime_lane_identity_mismatch:"
                        f"action_time_lane_to_ticket_{missing}_missing"
                    )
                continue
            _require_current_runtime_lane_lineage(
                signal=signal,
                downstream=lane,
                boundary="promotion_to_action_time_lane",
                entity_id=str(lane.get("action_time_lane_input_id") or ""),
            )
            _require_current_runtime_lane_lineage(
                signal=signal,
                downstream=ticket,
                boundary="action_time_lane_to_ticket",
                entity_id=ticket_id,
            )


def _validate_watcher_candidate_universe(
    rows: dict[str, list[dict[str, Any]]],
) -> None:
    candidates = rows["candidate_scope"]
    if not candidates:
        raise RuntimeControlStateRepositoryError("active candidate scope is empty")

    def unique_by(
        values: list[dict[str, Any]],
        key: str,
        logical_key: str,
    ) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for row in values:
            identity = str(row.get(key) or "").strip()
            if not identity or identity in indexed:
                raise RuntimeControlStateRepositoryError(
                    f"watcher_candidate_duplicate_identity:{logical_key}:{identity}"
                )
            indexed[identity] = row
        return indexed

    candidate_by_id = unique_by(
        candidates,
        "candidate_scope_id",
        "candidate_scope",
    )
    event_by_id = unique_by(
        rows["strategy_side_event_specs"],
        "event_spec_id",
        "strategy_side_event_specs",
    )
    binding_by_id = unique_by(
        rows["candidate_scope_event_bindings"],
        "binding_id",
        "candidate_scope_event_bindings",
    )
    runtime_by_id = unique_by(
        rows["runtime_scope_bindings"],
        "runtime_scope_binding_id",
        "runtime_scope_bindings",
    )

    candidate_keys: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        lane_key = tuple(str(candidate.get(key) or "") for key in (
            "strategy_group_id",
            "symbol",
            "side",
        ))
        if lane_key in candidate_keys:
            raise RuntimeControlStateRepositoryError(
                "watcher_candidate_duplicate_lane:" + ":".join(lane_key)
            )
        candidate_keys.add(lane_key)

    bindings_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for binding in binding_by_id.values():
        candidate_id = str(binding.get("candidate_scope_id") or "")
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None:
            raise RuntimeControlStateRepositoryError(
                f"{binding.get('binding_id')} has no active candidate scope"
            )
        event = event_by_id.get(str(binding.get("event_spec_id") or ""))
        if event is None:
            raise RuntimeControlStateRepositoryError(
                f"{binding.get('binding_id')} does not reference a current event spec"
            )
        for key in ("strategy_group_id", "symbol", "side"):
            if binding.get(key) != candidate.get(key):
                raise RuntimeControlStateRepositoryError(
                    f"{binding.get('binding_id')} mismatches candidate {key}"
                )
        for key in ("strategy_group_id", "side"):
            if event.get(key) != candidate.get(key):
                raise RuntimeControlStateRepositoryError(
                    f"{binding.get('binding_id')} mismatches event {key}"
                )
        bindings_by_candidate.setdefault(candidate_id, []).append(binding)

    runtimes_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for runtime in runtime_by_id.values():
        candidate_id = str(runtime.get("candidate_scope_id") or "")
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None:
            raise RuntimeControlStateRepositoryError(
                f"{runtime.get('runtime_scope_binding_id')} has no active candidate scope"
            )
        for key in (
            "strategy_group_id",
            "symbol",
            "side",
        ):
            if runtime.get(key) != candidate.get(key):
                raise RuntimeControlStateRepositoryError(
                    f"{runtime.get('runtime_scope_binding_id')} mismatches candidate {key}"
                )
        runtimes_by_candidate.setdefault(candidate_id, []).append(runtime)

    for candidate_id in candidate_by_id:
        event_binding_count = len(bindings_by_candidate.get(candidate_id, ()))
        if event_binding_count == 0:
            raise RuntimeControlStateRepositoryError(
                f"{candidate_id} has no active event binding"
            )
        if event_binding_count != 1:
            raise RuntimeControlStateRepositoryError(
                f"{candidate_id} must have exactly one active event binding"
            )
        runtime_binding_count = len(runtimes_by_candidate.get(candidate_id, ()))
        if runtime_binding_count == 0:
            raise RuntimeControlStateRepositoryError(
                f"{candidate_id} has no active runtime scope binding"
            )
        if runtime_binding_count != 1:
            raise RuntimeControlStateRepositoryError(
                f"{candidate_id} must have exactly one active runtime scope binding"
            )


def _watcher_current_rows(
    rows: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        logical_key: [
            row
            for row in rows.get(logical_key, [])
            if row.get("status") == (
                "current" if logical_key == "strategy_side_event_specs" else "active"
            )
        ]
        for logical_key in WATCHER_CANDIDATE_PROFILE
    }


def _require_guarded_json_bytes(
    row: dict[str, Any],
    field_name: str,
    max_bytes: int,
) -> None:
    byte_count = row.pop(f"{field_name}_bytes", None)
    if byte_count is None and row.get(field_name) is None:
        return
    if byte_count is None or int(byte_count) > max_bytes:
        raise RuntimeControlStateRepositoryError(
            f"capability_certification_json_bytes_exceeded:{field_name}:"
            f"{max_bytes}"
        )


def _validate_capability_runtime_instances(
    state: dict[str, list[dict[str, Any]]],
) -> None:
    runtimes_by_lane: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for runtime in state["strategy_runtime_instances"]:
        lane = (
            str(runtime.get("strategy_family_id") or ""),
            str(runtime.get("symbol") or ""),
            str(runtime.get("side") or ""),
        )
        runtimes_by_lane.setdefault(lane, []).append(runtime)

    event_by_id = {
        str(row["event_spec_id"]): row
        for row in state["strategy_side_event_specs"]
    }
    binding_by_candidate = {
        str(row["candidate_scope_id"]): row
        for row in state["candidate_scope_event_bindings"]
    }
    for candidate in state["candidate_scope"]:
        candidate_id = str(candidate["candidate_scope_id"])
        lane = (
            str(candidate["strategy_group_id"]),
            str(candidate["symbol"]),
            str(candidate["side"]),
        )
        runtime_rows = runtimes_by_lane.get(lane, [])
        if len(runtime_rows) != 1:
            raise RuntimeControlStateRepositoryError(
                f"capability_certification_runtime_not_unique:{candidate_id}"
            )
        binding = binding_by_candidate[candidate_id]
        event = event_by_id[str(binding["event_spec_id"])]
        if str(runtime_rows[0]["strategy_family_version_id"]) != str(
            event["strategy_group_version_id"]
        ):
            raise RuntimeControlStateRepositoryError(
                f"capability_certification_runtime_version_mismatch:{candidate_id}"
            )


def _tracks_runtime_lane_identity(row: dict[str, Any]) -> bool:
    """Return whether this row comes from a schema with migrated lane identity.

    Older test schemas do not contain the new columns at all.  A migrated
    production row always contains these keys, even if a corrupt value is NULL,
    so it must fail closed instead of taking a compatibility path.
    """

    return any(field in row for field in RUNTIME_LANE_IDENTITY_COLUMN_SENTINELS)


def _require_current_runtime_lane_lineage(
    *,
    signal: dict[str, Any],
    downstream: dict[str, Any],
    boundary: str,
    entity_id: str,
) -> None:
    """Reject a current Promotion or Lane whose lineage differs from its signal."""

    if not _tracks_runtime_lane_identity(signal) and not _tracks_runtime_lane_identity(
        downstream
    ):
        return
    try:
        source_identity = runtime_lane_identity_from_live_signal(signal)
        source_lineage = runtime_lane_lineage_from_record(signal)
        if source_lineage.lane_identity_key != source_identity.identity_key:
            raise RuntimeLaneIdentityConservationError(
                "runtime_lane_identity_mismatch:signal_lineage_key"
            )
        require_runtime_lane_lineage_match(
            expected=source_lineage,
            actual=runtime_lane_lineage_from_record(downstream),
            boundary=boundary,
        )
    except RuntimeLaneIdentityConservationError as exc:
        raise RuntimeControlStateRepositoryError(
            f"{entity_id} {exc.blocker}"
        ) from exc
    except RuntimeLaneIdentityMismatch as exc:
        raise RuntimeControlStateRepositoryError(f"{entity_id} {exc}") from exc


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _preserve_typed_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _preserve_typed_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_preserve_typed_value(item) for item in value]
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
        return statement.where(
            sa.and_(
                columns.is_current.is_(True),
                columns.last_tick_at_ms.is_not(None),
                columns.last_tick_at_ms <= now_ms,
                columns.valid_until_ms.is_not(None),
                columns.valid_until_ms > now_ms,
            )
        )
    if logical_key == "pretrade_readiness_rows":
        return statement.where(
            sa.and_(
                columns.computed_at_ms <= now_ms,
                sa.or_(
                    columns.valid_until_ms.is_(None),
                    columns.valid_until_ms > now_ms,
                ),
            )
        )
    if logical_key == "runtime_fact_snapshots":
        statement = statement.where(
            sa.and_(
                columns.freshness_state == "fresh",
                columns.observed_at_ms <= now_ms,
                columns.created_at_ms <= now_ms,
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
                columns.event_time_ms <= now_ms,
                columns.observed_at_ms <= now_ms,
                columns.created_at_ms <= now_ms,
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
                columns.created_at_ms <= now_ms,
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
                columns.created_at_ms <= now_ms,
                columns.expires_at_ms.is_not(None),
                columns.expires_at_ms > now_ms,
            )
        )
    if logical_key == "action_time_tickets":
        return statement.where(
            sa.and_(
                columns.created_at_ms <= now_ms,
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
    if logical_key == "runtime_safety_state":
        statement = statement.where(
            sa.and_(
                columns.observed_at_ms <= now_ms,
                columns.valid_until_ms.is_not(None),
                columns.valid_until_ms > now_ms,
            )
        )
        if "observed_at_ms" in columns:
            statement = statement.order_by(columns.observed_at_ms.desc()).limit(200)
        return statement
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
    if logical_key == "server_monitor_notifications" and "updated_at_ms" in columns:
        return statement.order_by(columns.updated_at_ms.desc()).limit(1000)
    if logical_key == "ticket_bound_protected_submit_attempts" and "created_at_ms" in columns:
        return statement.where(
            columns.status.in_(
                [
                    "blocked",
                    "disabled_smoke_passed",
                    "submit_prepared",
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
        return statement.order_by(columns.updated_at_ms.desc()).limit(200)
    if logical_key == "live_outcome_ledger":
        time_column = (
            columns.closed_at_ms
            if "closed_at_ms" in columns
            else columns.created_at_ms
            if "created_at_ms" in columns
            else None
        )
        if time_column is not None:
            return statement.order_by(time_column.desc()).limit(200)
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
        and _timestamp_not_future(row, "event_time_ms", now_ms)
        and _timestamp_not_future(row, "observed_at_ms", now_ms)
        and _timestamp_not_future(row, "created_at_ms", now_ms)
        and row.get("expires_at_ms") is not None
        and int(row.get("expires_at_ms") or 0) > now_ms
    )


def is_current_promotion_candidate(row: dict[str, Any], now_ms: int) -> bool:
    return (
        row.get("closed_at_ms") is None
        and row.get("status")
        in {"eligible", "arbitration_pending", "arbitration_won"}
        and _timestamp_not_future(row, "created_at_ms", now_ms)
        and row.get("expires_at_ms") is not None
        and int(row.get("expires_at_ms") or 0) > now_ms
    )


def is_current_action_time_lane(row: dict[str, Any], now_ms: int) -> bool:
    return (
        row.get("lane_scope") == "real_submit_candidate"
        and row.get("status") in OPEN_REAL_LANE_STATUSES
        and row.get("closed_at_ms") is None
        and _timestamp_not_future(row, "created_at_ms", now_ms)
        and row.get("expires_at_ms") is not None
        and int(row.get("expires_at_ms") or 0) > now_ms
    )


def is_current_action_time_ticket(row: dict[str, Any], now_ms: int) -> bool:
    if row.get("status") == "submitted":
        return _timestamp_not_future(row, "created_at_ms", now_ms)
    return (
        row.get("status") in {"created", "preflight_pending", "finalgate_ready"}
        and _timestamp_not_future(row, "created_at_ms", now_ms)
        and row.get("expires_at_ms") is not None
        and int(row.get("expires_at_ms") or 0) > now_ms
    )


def is_current_fact_snapshot(row: dict[str, Any], now_ms: int) -> bool:
    return (
        row.get("freshness_state") == "fresh"
        and _timestamp_not_future(row, "observed_at_ms", now_ms)
        and _timestamp_not_future(row, "created_at_ms", now_ms)
        and row.get("valid_until_ms") is not None
        and int(row.get("valid_until_ms") or 0) > now_ms
    )


def is_current_watcher_coverage(row: dict[str, Any], now_ms: int) -> bool:
    """Return whether one watcher-coverage row is current at ``now_ms``."""

    last_tick_at_ms = int(row.get("last_tick_at_ms") or 0)
    valid_until_ms = int(row.get("valid_until_ms") or 0)
    return (
        row.get("is_current") is True
        and last_tick_at_ms > 0
        and last_tick_at_ms <= now_ms
        and valid_until_ms > now_ms
    )


def is_current_pretrade_readiness(row: dict[str, Any], now_ms: int) -> bool:
    """Return whether one per-lane readiness projection is current."""

    computed_at_ms = int(row.get("computed_at_ms") or 0)
    valid_until = row.get("valid_until_ms")
    valid_until_current = valid_until in (None, "") or int(valid_until) > now_ms
    return (
        computed_at_ms > 0
        and computed_at_ms <= now_ms
        and valid_until_current
    )


def is_current_runtime_safety_state(row: dict[str, Any], now_ms: int) -> bool:
    """Return whether one Runtime Safety State snapshot is time-current."""

    observed_at_ms = int(row.get("observed_at_ms") or 0)
    valid_until_ms = int(row.get("valid_until_ms") or 0)
    return (
        observed_at_ms > 0
        and observed_at_ms <= now_ms
        and valid_until_ms > now_ms
    )


def runtime_safety_submit_authorized(row: dict[str, Any]) -> bool:
    """Fail closed unless the snapshot itself proves submit eligibility.

    This validates the snapshot payload only. Consumers must additionally prove
    its current lane/ticket/signal/Operation-Layer lineage before presenting
    ``tradable_now`` or any equivalent Owner-facing state.
    """

    blockers = row.get("blockers")
    blockers_clear = isinstance(blockers, list) and not blockers
    trusted_refs = row.get("trusted_fact_refs")
    required_ref_keys = (
        "ticket_id",
        "ticket_hash",
        "finalgate_pass_id",
        "operation_layer_handoff_id",
        "operation_submit_command_id",
        "signal_event_id",
        "budget_reservation_id",
        "protection_ref_id",
        "public_fact_snapshot_id",
        "action_time_fact_snapshot_id",
        "account_safe_fact_snapshot_id",
        "account_mode_snapshot_id",
    )
    trusted_refs_concrete = isinstance(trusted_refs, dict) and all(
        bool(str(trusted_refs.get(key) or "").strip()) for key in required_ref_keys
    )
    return (
        row.get("submit_allowed") is True
        and row.get("safety_state") == "live_submit_ready"
        and row.get("finalgate_ready") is True
        and row.get("operation_layer_ready") is True
        and row.get("protection_ready") is True
        and row.get("active_position_conflict") is False
        and row.get("facts_fresh") is True
        and row.get("trusted_fact_refs_complete") is True
        and trusted_refs_concrete
        and blockers_clear
        and row.get("execution_eligible") is True
        and row.get("signal_grade")
        in {"trial_grade_signal", "production_grade_signal"}
        and row.get("required_execution_mode") in {"trial_live", "production_live"}
        and bool(str(row.get("authority_source_ref") or "").strip())
    )


def _timestamp_not_future(row: dict[str, Any], key: str, now_ms: int) -> bool:
    value = row.get(key)
    if value in (None, ""):
        return True
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return False
    return 0 < timestamp <= now_ms
