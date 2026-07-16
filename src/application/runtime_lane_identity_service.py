"""Resolve one immutable production lane identity from current PG state."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
import sqlalchemy as sa

from src.domain.runtime_lane_identity import RuntimeLaneIdentity


class RuntimeLaneIdentityResolutionError(RuntimeError):
    """Fail-closed result for an incomplete or conflicting PG lane."""

    def __init__(self, blocker: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(blocker)
        self.blocker = blocker
        self.details = details or {}


class RuntimeLaneIdentityResolution(BaseModel):
    """Identity plus Event-Spec metadata required for event-time evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: RuntimeLaneIdentity
    evaluator_version_id: str = Field(min_length=1, max_length=192)
    freshness_window_ms: int = Field(gt=0)


class RuntimeLaneIdentityService:
    """Resolve exactly one current PG lane for an active runtime instance.

    The strategy runtime's evaluator implementation version is deliberately
    distinct from the versioned StrategyGroup/Event-Spec semantic definition.
    The former is returned as provenance, while ``RuntimeLaneIdentity`` carries
    the latter and remains the lane authority.
    """

    def resolve(
        self,
        conn: sa.engine.Connection,
        *,
        runtime_instance_id: str,
    ) -> RuntimeLaneIdentityResolution:
        runtime = self._runtime(conn, runtime_instance_id=runtime_instance_id)
        strategy_group_id = _required(runtime, "strategy_family_id")
        symbol = _normalized_symbol(_required(runtime, "symbol"))
        side = _required(runtime, "side")
        if side not in {"long", "short"}:
            raise RuntimeLaneIdentityResolutionError(
                "runtime_instance_not_selected",
                details={"runtime_instance_id": runtime_instance_id, "side": side},
            )

        candidate = self._candidate(
            conn,
            runtime_instance_id=runtime_instance_id,
            strategy_group_id=strategy_group_id,
            symbol=symbol,
            side=side,
        )
        binding = self._binding(conn, candidate_scope_id=_required(candidate, "candidate_scope_id"))
        self._assert_scope_fields_match(
            expected=candidate,
            actual=binding,
            fields=("strategy_group_id", "symbol", "side"),
            boundary="candidate_scope_event_binding",
        )
        event_spec = self._event_spec(conn, event_spec_id=_required(binding, "event_spec_id"))
        self._assert_scope_fields_match(
            expected=candidate,
            actual=event_spec,
            fields=("strategy_group_id", "side"),
            boundary="event_spec",
        )
        timeframe = str(event_spec.get("timeframe") or "").strip()
        if not timeframe:
            raise RuntimeLaneIdentityResolutionError("event_spec_timeframe_missing")
        freshness_window_ms = _positive_int(event_spec.get("freshness_window_ms"))
        if freshness_window_ms <= 0:
            raise RuntimeLaneIdentityResolutionError("event_spec_freshness_window_missing")
        if _required(candidate, "timeframe") != timeframe:
            raise RuntimeLaneIdentityResolutionError(
                "runtime_lane_identity_mismatch",
                details={"boundary": "candidate_scope_timeframe"},
            )

        runtime_scope = self._runtime_scope(
            conn,
            candidate_scope_id=_required(candidate, "candidate_scope_id"),
        )
        self._assert_scope_fields_match(
            expected=candidate,
            actual=runtime_scope,
            fields=("strategy_group_id", "symbol", "side", "policy_current_id"),
            boundary="runtime_scope",
        )
        policy = self._policy(
            conn,
            policy_current_id=_required(runtime_scope, "policy_current_id"),
        )
        self._assert_scope_fields_match(
            expected=candidate,
            actual=policy,
            fields=("strategy_group_id", "symbol", "side"),
            boundary="owner_policy",
        )
        if _required(runtime_scope, "runtime_profile_id") != _required(
            policy,
            "runtime_profile_id",
        ):
            raise RuntimeLaneIdentityResolutionError(
                "runtime_lane_identity_mismatch",
                details={"boundary": "runtime_profile"},
            )

        try:
            identity = RuntimeLaneIdentity(
                candidate_scope_id=_required(candidate, "candidate_scope_id"),
                candidate_scope_event_binding_id=_required(binding, "binding_id"),
                runtime_scope_binding_id=_required(runtime_scope, "runtime_scope_binding_id"),
                runtime_instance_id=_required(runtime, "runtime_instance_id"),
                runtime_profile_id=_required(runtime_scope, "runtime_profile_id"),
                policy_current_id=_required(runtime_scope, "policy_current_id"),
                strategy_group_id=_required(candidate, "strategy_group_id"),
                strategy_group_version_id=_required(event_spec, "strategy_group_version_id"),
                symbol=_normalized_symbol(_required(candidate, "symbol")),
                exchange_instrument_id=_required(
                    candidate,
                    "exchange_instrument_id",
                ),
                asset_class=_required(candidate, "asset_class"),
                side=_required(candidate, "side"),
                event_spec_id=_required(event_spec, "event_spec_id"),
                event_spec_version=_required(event_spec, "event_spec_version"),
                event_id=_required(event_spec, "event_id"),
                timeframe=timeframe,
                time_authority=_required(event_spec, "time_authority"),
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeLaneIdentityResolutionError(
                "runtime_lane_identity_mismatch",
                details={"boundary": "runtime_lane_identity", "reason": str(exc)},
            ) from exc

        return RuntimeLaneIdentityResolution(
            identity=identity,
            evaluator_version_id=_required(runtime, "strategy_family_version_id"),
            freshness_window_ms=freshness_window_ms,
        )

    def _runtime(
        self,
        conn: sa.engine.Connection,
        *,
        runtime_instance_id: str,
    ) -> dict[str, Any]:
        rows = _rows(
            conn,
            """
            SELECT runtime_instance_id, strategy_family_id, strategy_family_version_id,
                   symbol, side, status
            FROM strategy_runtime_instances
            WHERE runtime_instance_id = :runtime_instance_id
            """,
            {"runtime_instance_id": runtime_instance_id},
        )
        if len(rows) != 1 or str(rows[0].get("status") or "") != "active":
            raise RuntimeLaneIdentityResolutionError(
                "runtime_instance_not_selected",
                details={"runtime_instance_id": runtime_instance_id},
            )
        return rows[0]

    def _candidate(
        self,
        conn: sa.engine.Connection,
        *,
        runtime_instance_id: str,
        strategy_group_id: str,
        symbol: str,
        side: str,
    ) -> dict[str, Any]:
        rows = _rows(
            conn,
            """
            SELECT candidate_scope_id, strategy_group_id, symbol,
                   exchange_instrument_id, asset_class, side, timeframe,
                   policy_current_id
            FROM brc_strategy_group_candidate_scope
            WHERE strategy_group_id = :strategy_group_id
              AND symbol = :symbol
              AND side = :side
              AND status = 'active'
            ORDER BY candidate_scope_id
            LIMIT 2
            """,
            {
                "strategy_group_id": strategy_group_id,
                "symbol": symbol,
                "side": side,
            },
        )
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            raise RuntimeLaneIdentityResolutionError("candidate_scope_ambiguous")
        group_rows = _rows(
            conn,
            """
            SELECT candidate_scope_id
            FROM brc_strategy_group_candidate_scope
            WHERE strategy_group_id = :strategy_group_id
              AND status = 'active'
            ORDER BY candidate_scope_id
            LIMIT 1
            """,
            {"strategy_group_id": strategy_group_id},
        )
        if group_rows:
            raise RuntimeLaneIdentityResolutionError(
                "runtime_instance_not_selected",
                details={
                    "runtime_instance_id": runtime_instance_id,
                    "strategy_group_id": strategy_group_id,
                    "symbol": symbol,
                    "side": side,
                },
            )
        raise RuntimeLaneIdentityResolutionError("candidate_scope_missing")

    def _binding(
        self,
        conn: sa.engine.Connection,
        *,
        candidate_scope_id: str,
    ) -> dict[str, Any]:
        rows = _rows(
            conn,
            """
            SELECT binding_id, candidate_scope_id, event_spec_id, strategy_group_id,
                   symbol, side
            FROM brc_candidate_scope_event_bindings
            WHERE candidate_scope_id = :candidate_scope_id
              AND status = 'active'
            """,
            {"candidate_scope_id": candidate_scope_id},
        )
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            raise RuntimeLaneIdentityResolutionError(
                "candidate_scope_event_binding_ambiguous"
            )
        raise RuntimeLaneIdentityResolutionError("candidate_scope_event_binding_missing")

    def _event_spec(
        self,
        conn: sa.engine.Connection,
        *,
        event_spec_id: str,
    ) -> dict[str, Any]:
        rows = _rows(
            conn,
            """
            SELECT event_spec_id, strategy_group_id, strategy_group_version_id,
                   event_id, side, timeframe, event_spec_version, time_authority,
                   freshness_window_ms
            FROM brc_strategy_side_event_specs
            WHERE event_spec_id = :event_spec_id
              AND status = 'current'
            """,
            {"event_spec_id": event_spec_id},
        )
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            raise RuntimeLaneIdentityResolutionError("event_spec_ambiguous")
        raise RuntimeLaneIdentityResolutionError("event_spec_missing")

    def _runtime_scope(
        self,
        conn: sa.engine.Connection,
        *,
        candidate_scope_id: str,
    ) -> dict[str, Any]:
        rows = _rows(
            conn,
            """
            SELECT runtime_scope_binding_id, candidate_scope_id, strategy_group_id,
                   symbol, side, runtime_profile_id, policy_current_id
            FROM brc_runtime_scope_bindings
            WHERE candidate_scope_id = :candidate_scope_id
              AND status = 'active'
            """,
            {"candidate_scope_id": candidate_scope_id},
        )
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            raise RuntimeLaneIdentityResolutionError("runtime_scope_binding_ambiguous")
        raise RuntimeLaneIdentityResolutionError("runtime_scope_binding_missing")

    def _policy(
        self,
        conn: sa.engine.Connection,
        *,
        policy_current_id: str,
    ) -> dict[str, Any]:
        rows = _rows(
            conn,
            """
            SELECT policy_current_id, strategy_group_id, symbol, side, runtime_profile_id
            FROM brc_owner_policy_current
            WHERE policy_current_id = :policy_current_id
            """,
            {"policy_current_id": policy_current_id},
        )
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            raise RuntimeLaneIdentityResolutionError("policy_current_ambiguous")
        raise RuntimeLaneIdentityResolutionError("policy_current_missing")

    @staticmethod
    def _assert_scope_fields_match(
        *,
        expected: dict[str, Any],
        actual: dict[str, Any],
        fields: tuple[str, ...],
        boundary: str,
    ) -> None:
        for field in fields:
            expected_value = _normalized_field(field, expected.get(field))
            actual_value = _normalized_field(field, actual.get(field))
            if expected_value != actual_value:
                raise RuntimeLaneIdentityResolutionError(
                    "runtime_lane_identity_mismatch",
                    details={
                        "boundary": boundary,
                        "field": field,
                        "expected": expected_value,
                        "actual": actual_value,
                    },
                )


def _rows(
    conn: sa.engine.Connection,
    query: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in conn.execute(sa.text(query), params).mappings().all()]
    except sa.exc.SQLAlchemyError as exc:
        raise RuntimeLaneIdentityResolutionError(
            "runtime_lane_identity_resolution_unavailable",
            details={"database_error": exc.__class__.__name__},
        ) from exc


def _required(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise RuntimeLaneIdentityResolutionError(
            "runtime_lane_identity_mismatch",
            details={"field": key, "reason": "missing"},
        )
    return value


def _positive_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalized_symbol(value: str) -> str:
    return value.upper().split(":", 1)[0].replace("/", "")


def _normalized_field(field: str, value: Any) -> str:
    normalized = str(value or "").strip()
    if field == "symbol":
        return _normalized_symbol(normalized)
    return normalized
