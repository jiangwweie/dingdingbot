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
    "ticket_bound_post_submit_closures": "brc_ticket_bound_post_submit_closures",
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

EXPECTED_ACTIVE_EVENT_SPECS: dict[str, dict[str, Any]] = {
    "event_spec:CPM-RO-001:CPM-LONG:v1": {
        "strategy_group_id": "CPM-RO-001",
        "event_id": "CPM-LONG",
        "side": "long",
        "timeframe": "1h",
        "time_authority": "trigger_candle_close_time_ms",
        "protection_ref_type": "pullback_low_reference",
        "required_facts": {
            "htf_trend_intact",
            "reclaim_confirmed",
            "pullback_low_reference",
        },
        "disable_facts": set(),
    },
    "event_spec:MPG-001:MPG-LONG:v1": {
        "strategy_group_id": "MPG-001",
        "event_id": "MPG-LONG",
        "side": "long",
        "timeframe": "1h",
        "time_authority": "trigger_candle_close_time_ms",
        "protection_ref_type": "momentum_floor_reference",
        "required_facts": {
            "momentum_persistence_confirmed",
            "leader_strength_confirmed",
            "momentum_floor_reference",
        },
        "disable_facts": set(),
    },
    "event_spec:MI-001:MI-LONG:v1": {
        "strategy_group_id": "MI-001",
        "event_id": "MI-LONG",
        "side": "long",
        "timeframe": "1h",
        "time_authority": "trigger_candle_close_time_ms",
        "protection_ref_type": "impulse_invalidation_reference",
        "required_facts": {
            "impulse_confirmed",
            "relative_strength_confirmed",
            "impulse_invalidation_reference",
        },
        "disable_facts": set(),
    },
    "event_spec:SOR-001:SOR-LONG:v1": {
        "strategy_group_id": "SOR-001",
        "event_id": "SOR-LONG",
        "side": "long",
        "timeframe": "15m",
        "time_authority": "trigger_candle_close_time_ms",
        "protection_ref_type": "opening_range_low_reference",
        "required_facts": {
            "opening_range_defined",
            "breakout_confirmed",
            "opening_range_low_reference",
        },
        "disable_facts": set(),
    },
    "event_spec:SOR-001:SOR-SHORT:v1": {
        "strategy_group_id": "SOR-001",
        "event_id": "SOR-SHORT",
        "side": "short",
        "timeframe": "15m",
        "time_authority": "trigger_candle_close_time_ms",
        "protection_ref_type": "opening_range_high_reference",
        "required_facts": {
            "opening_range_defined",
            "breakdown_confirmed",
            "opening_range_high_reference",
        },
        "disable_facts": set(),
    },
    "event_spec:BRF2-001:BRF2-SHORT:v1": {
        "strategy_group_id": "BRF2-001",
        "event_id": "BRF2-SHORT",
        "side": "short",
        "timeframe": "1h",
        "time_authority": "trigger_candle_close_time_ms",
        "protection_ref_type": "rally_high_reference",
        "required_facts": {
            "rally_failure_confirmed",
            "short_side_not_disabled",
            "rally_high_reference",
        },
        "disable_facts": {"strong_uptrend_disable"},
    },
}
EXPECTED_ACTIVE_SCOPE_KEYS = {
    (
        spec["strategy_group_id"],
        spec["side"],
        spec["event_id"],
    )
    for spec in EXPECTED_ACTIVE_EVENT_SPECS.values()
}
ACTIVE_RUNTIME_STRATEGY_GROUP_IDS = {
    str(spec["strategy_group_id"]) for spec in EXPECTED_ACTIVE_EVENT_SPECS.values()
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
        self._validate_active_event_semantics(rows)
        self._validate_candidate_scope_event_bindings(rows)
        self._validate_runtime_scope_bindings(rows)
        self._validate_live_signal_events(rows)
        self._validate_promotion_and_lane_identity(rows)
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
        for candidate_id, candidate in active_candidates.items():
            event_id = str(_as_dict(candidate.get("metadata")).get("event_id") or "")
            key = (
                str(candidate.get("strategy_group_id") or ""),
                str(candidate.get("side") or ""),
                event_id,
            )
            if key not in EXPECTED_ACTIVE_SCOPE_KEYS:
                raise RuntimeControlStateRepositoryError(
                    f"{candidate_id} is outside active PG event scope"
                )

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
        expected_ids = set(EXPECTED_ACTIVE_EVENT_SPECS)
        actual_ids = set(current_events)
        missing = expected_ids - actual_ids
        extra = {
            event_spec_id
            for event_spec_id in actual_ids - expected_ids
            if str(current_events[event_spec_id].get("strategy_group_id") or "")
            in ACTIVE_RUNTIME_STRATEGY_GROUP_IDS
        }
        if missing or extra:
            details = []
            if missing:
                details.append("missing=" + ",".join(sorted(missing)))
            if extra:
                details.append("unexpected=" + ",".join(sorted(extra)))
            raise RuntimeControlStateRepositoryError(
                "current PG event specs do not match active contract: "
                + "; ".join(details)
            )

        for event_spec_id, expected in EXPECTED_ACTIVE_EVENT_SPECS.items():
            event = current_events[event_spec_id]
            for key in (
                "strategy_group_id",
                "event_id",
                "side",
                "timeframe",
                "time_authority",
                "protection_ref_type",
            ):
                if str(event.get(key) or "") != str(expected[key]):
                    raise RuntimeControlStateRepositoryError(
                        f"{event_spec_id} mismatches {key}"
                    )
            if str(event.get("event_spec_version") or "") != "v1":
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} must use event_spec_version=v1"
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
        for event_spec_id, expected in EXPECTED_ACTIVE_EVENT_SPECS.items():
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
            if required_keys != expected["required_facts"]:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} required facts mismatch: "
                    f"expected={sorted(expected['required_facts'])}, "
                    f"actual={sorted(required_keys)}"
                )
            if disable_keys != expected["disable_facts"]:
                raise RuntimeControlStateRepositoryError(
                    f"{event_spec_id} disable facts mismatch: "
                    f"expected={sorted(expected['disable_facts'])}, "
                    f"actual={sorted(disable_keys)}"
                )

            event = current_events[event_spec_id]
            version_id = str(event.get("strategy_group_version_id") or "")
            for fact in facts:
                fact_key = str(fact.get("fact_key") or "")
                if not str(fact.get("required_facts_version_id") or "").endswith(":v1"):
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
            if not _is_current_fresh_signal(signal):
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
            and row.get("closed_at_ms") is None
        ]
        if len(open_winners) > 1:
            raise RuntimeControlStateRepositoryError(
                "multiple open arbitration_won promotion candidates"
            )

        for promotion in rows["promotion_candidates"]:
            if not _requires_current_promotion_validation(promotion):
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
            if row.get("lane_scope") == "real_submit_candidate"
            and row.get("status") in OPEN_REAL_LANE_STATUSES
        ]
        if len(open_real_lanes) > 1:
            raise RuntimeControlStateRepositoryError(
                "multiple open real-submit action-time lanes"
            )
        for lane in rows["action_time_lane_inputs"]:
            if not _requires_current_lane_validation(lane):
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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_current_fresh_signal(row: dict[str, Any]) -> bool:
    return (
        row.get("status") == "facts_validated"
        and row.get("freshness_state") == "fresh"
        and row.get("invalidated_at_ms") is None
    )


def _requires_current_promotion_validation(row: dict[str, Any]) -> bool:
    return (
        row.get("closed_at_ms") is None
        and row.get("status")
        in {"eligible", "arbitration_pending", "arbitration_won"}
    )


def _requires_current_lane_validation(row: dict[str, Any]) -> bool:
    return (
        row.get("lane_scope") == "real_submit_candidate"
        and row.get("status") in OPEN_REAL_LANE_STATUSES
    )
