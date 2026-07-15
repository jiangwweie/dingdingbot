"""Release-bound Action-Time capability identity and currentness truth."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field
import sqlalchemy as sa

from src.application.runtime_process_outcome import (
    materialize_runtime_process_outcome,
)
from src.domain.runtime_lane_identity import RuntimeLaneIdentity


PROCESS_NAME = "action_time_capability_certification"
RELEASE_ACTIVATION_PROCESS_NAME = "runtime_release_activation"
RELEASE_ACTIVATION_SCOPE_KEY = "production:tokyo"
FIRST_BLOCKER = "action_time_boundary_not_reproduced"
CAPABILITY_INPUT_DIGEST_SCHEMA = (
    "brc.action_time_capability_certification_input.v1"
)
LANE_IDENTITY_DIGEST_SCHEMA = "brc.action_time_capability_lane_identity.v2"
CANONICAL_ENCODING = "brc.typed_canonical_json.v1"
DIGEST_ALGORITHM = "sha256"
FACT_SET_DIGEST_SCHEMA = "brc.action_time_fact_set_digest.v1"

CAPABILITY_DIGEST_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
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
        "conditional_hard_gates",
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
        "policy_event_ids",
    ),
    "strategy_event_required_facts": (
        "event_required_fact_id",
        "event_spec_id",
        "required_facts_version_id",
        "fact_key",
        "fact_role",
        "fact_surface",
        "operator",
        "expected_value",
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

JSON_SEMANTIC_FIELDS = {
    ("runtime_scope_bindings", "conditional_hard_gates"),
    ("owner_policy_current", "policy_event_ids"),
    ("strategy_event_required_facts", "expected_value"),
}


class ActionTimeCapabilityIdentityError(ValueError):
    """Raised when a current PG lane cannot form a complete identity."""

    def __init__(self, candidate_scope_id: str, reason: str | None = None) -> None:
        self.candidate_scope_id = candidate_scope_id if reason is not None else ""
        self.reason = reason or candidate_scope_id
        message = (
            f"candidate_scope:{candidate_scope_id}:{reason}"
            if reason is not None
            else candidate_scope_id
        )
        super().__init__(message)


class CapabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ActionTimeCapabilityIdentity(CapabilityModel):
    runtime_lane_identity: RuntimeLaneIdentity
    candidate_scope_id: str = Field(min_length=1)
    strategy_group_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: str = Field(min_length=1)
    scope_key: str = Field(min_length=1)
    strategy_group_version_id: str = Field(min_length=1)
    event_spec_id: str = Field(min_length=1)
    event_spec_version_id: str = Field(min_length=1)
    event_contract_ref: str = Field(min_length=1)
    required_fact_contract_refs: tuple[str, ...] = Field(min_length=1)
    runtime_scope_binding_id: str = Field(min_length=1)
    runtime_scope_contract_ref: str = Field(min_length=1)
    owner_policy_version_id: str = Field(min_length=1)
    owner_policy_contract_ref: str = Field(min_length=1)
    runtime_profile_id: str = Field(min_length=1)
    source_watermark: str = Field(pattern=r"^action_time_capability:[0-9a-f]{64}$")

    @property
    def lane_key(self) -> tuple[str, str, str]:
        return self.strategy_group_id, self.symbol, self.side


class ActionTimeCapabilityTruth(CapabilityModel):
    identity: ActionTimeCapabilityIdentity | None
    certified: bool
    first_blocker: str | None
    reason: str
    certification_ref: str = ""
    certified_runtime_head: str = ""


class ActionTimeCapabilityCertificationPreparation(CapabilityModel):
    digest_schema: str = CAPABILITY_INPUT_DIGEST_SCHEMA
    canonical_encoding: str = CANONICAL_ENCODING
    digest_algorithm: str = DIGEST_ALGORITHM
    runtime_head: str = Field(min_length=1)
    release_activation_process_outcome_id: str = Field(min_length=1)
    release_activation_source_watermark: str = Field(min_length=1)
    referenced_ids: dict[str, tuple[str, ...]]
    lane_source_watermarks: tuple[tuple[str, str], ...]
    fact_set_digest_schema: str = FACT_SET_DIGEST_SCHEMA
    fact_snapshot_ids: tuple[str, ...] = Field(min_length=1, max_length=128)
    fact_set_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    certification_input_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ActionTimeFactDigestRowV1(CapabilityModel):
    fact_snapshot_id: str = Field(min_length=1)
    strategy_group_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: str = Field(min_length=1)
    runtime_profile_id: str = Field(min_length=1)
    fact_surface: str = Field(min_length=1)
    source_kind: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    computed: bool
    satisfied: bool
    freshness_state: str = Field(min_length=1)
    failed_facts: list[Any]
    fact_values: dict[str, Any]
    blocker_class: str | None
    observed_at_ms: int
    valid_until_ms: int


class ActionTimeFactSetDigestV1(CapabilityModel):
    fact_set_digest_schema: str = FACT_SET_DIGEST_SCHEMA
    canonical_encoding: str = CANONICAL_ENCODING
    fact_snapshot_ids: tuple[str, ...] = Field(min_length=1, max_length=128)
    fact_set_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def prepare_action_time_capability_certification(
    control_state: Mapping[str, Any],
    *,
    runtime_head: str,
    fact_digest_rows: Sequence[ActionTimeFactDigestRowV1],
) -> ActionTimeCapabilityCertificationPreparation:
    runtime_head = str(runtime_head or "").strip()
    if not runtime_head:
        raise ValueError("runtime_head_required")
    identities = build_action_time_capability_identities(control_state)
    activations = _strict_digest_rows(control_state, "runtime_process_outcomes")
    if len(activations) != 1:
        raise ValueError("release_activation_not_unique")
    activation = activations[0]
    if str(activation["runtime_head"]) != runtime_head:
        raise ValueError("runtime_head_mismatch")

    referenced_ids = {
        "strategy_group_ids": tuple(
            sorted({identity.strategy_group_id for identity in identities})
        ),
        "strategy_group_version_ids": tuple(
            sorted({identity.strategy_group_version_id for identity in identities})
        ),
        "candidate_scope_ids": tuple(
            sorted({identity.candidate_scope_id for identity in identities})
        ),
        "event_spec_ids": tuple(
            sorted({identity.event_spec_id for identity in identities})
        ),
        "policy_current_ids": tuple(
            sorted(
                {
                    identity.runtime_lane_identity.policy_current_id
                    for identity in identities
                }
            )
        ),
        "runtime_scope_binding_ids": tuple(
            sorted({identity.runtime_scope_binding_id for identity in identities})
        ),
    }
    lane_source_watermarks = tuple(
        sorted(
            (identity.scope_key, identity.source_watermark)
            for identity in identities
        )
    )
    fact_set = compute_action_time_fact_set_digest(fact_digest_rows)
    tables = []
    for table_name, column_names in CAPABILITY_DIGEST_TABLE_COLUMNS.items():
        canonical_rows = []
        for row in _strict_digest_rows(control_state, table_name):
            canonical_rows.append(
                [
                    [
                        column,
                        _canonical_sql_value(
                            row[column],
                            json_semantic=(table_name, column)
                            in JSON_SEMANTIC_FIELDS,
                        ),
                    ]
                    for column in column_names
                ]
            )
        tables.append([table_name, canonical_rows])
    payload = {
        "schema": CAPABILITY_INPUT_DIGEST_SCHEMA,
        "encoding": CANONICAL_ENCODING,
        "algorithm": DIGEST_ALGORITHM,
        "runtime_head": runtime_head,
        "release_activation": {
            key: activation[key]
            for key in CAPABILITY_DIGEST_TABLE_COLUMNS[
                "runtime_process_outcomes"
            ]
        },
        "referenced_ids": referenced_ids,
        "lane_source_watermarks": lane_source_watermarks,
        "fact_set": fact_set.model_dump(mode="json"),
        "tables": tables,
    }
    canonical_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = "sha256:" + sha256(canonical_bytes).hexdigest()
    return ActionTimeCapabilityCertificationPreparation(
        runtime_head=runtime_head,
        release_activation_process_outcome_id=str(
            activation["process_outcome_id"]
        ),
        release_activation_source_watermark=str(activation["source_watermark"]),
        referenced_ids=referenced_ids,
        lane_source_watermarks=lane_source_watermarks,
        fact_set_digest_schema=fact_set.fact_set_digest_schema,
        fact_snapshot_ids=fact_set.fact_snapshot_ids,
        fact_set_digest=fact_set.fact_set_digest,
        certification_input_digest=digest,
    )


def apply_prepared_action_time_capability_certification(
    conn: sa.engine.Connection | None,
    *,
    prepared: ActionTimeCapabilityCertificationPreparation,
    control_state: Mapping[str, Any],
    fact_digest_rows: Sequence[ActionTimeFactDigestRowV1],
    runtime_head: str,
    certification_ref: str,
    expected_lane_count: int,
    now_ms: int,
) -> dict[str, Any]:
    current = prepare_action_time_capability_certification(
        control_state,
        runtime_head=runtime_head,
        fact_digest_rows=fact_digest_rows,
    )
    if current != prepared:
        result = _certification_result(
            status="blocked",
            certified_lane_count=0,
            first_blocker="certification_input_digest_drift",
            blockers=["certification_input_digest_drift"],
        )
        result.update(
            {
                "digest_schema": current.digest_schema,
                "canonical_encoding": current.canonical_encoding,
                "prepared_certification_input_digest": (
                    prepared.certification_input_digest
                ),
                "current_certification_input_digest": (
                    current.certification_input_digest
                ),
            }
        )
        return result
    if conn is None:
        raise ValueError("certification_apply_connection_required")
    result = certify_action_time_capabilities(
        conn,
        control_state=control_state,
        runtime_head=runtime_head,
        certification_ref=certification_ref,
        expected_lane_count=expected_lane_count,
        now_ms=now_ms,
    )
    result.update(
        {
            "digest_schema": prepared.digest_schema,
            "canonical_encoding": prepared.canonical_encoding,
            "certification_input_digest": prepared.certification_input_digest,
        }
    )
    return result


def compute_action_time_fact_set_digest(
    rows: Sequence[ActionTimeFactDigestRowV1],
) -> ActionTimeFactSetDigestV1:
    ordered = sorted(rows, key=lambda row: row.fact_snapshot_id)
    fact_ids = tuple(row.fact_snapshot_id for row in ordered)
    if not fact_ids or len(fact_ids) > 128 or len(set(fact_ids)) != len(fact_ids):
        raise ValueError("fact_digest_id_set_invalid")
    fields = tuple(ActionTimeFactDigestRowV1.model_fields)
    payload_rows = []
    for row in ordered:
        values = row.model_dump(mode="python")
        payload_rows.append(
            [
                [
                    field,
                    _canonical_sql_value(
                        values[field],
                        json_semantic=field in {"failed_facts", "fact_values"},
                    ),
                ]
                for field in fields
            ]
        )
    payload = {
        "schema": FACT_SET_DIGEST_SCHEMA,
        "encoding": CANONICAL_ENCODING,
        "algorithm": DIGEST_ALGORITHM,
        "fact_snapshot_ids": fact_ids,
        "rows": payload_rows,
    }
    canonical_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(canonical_bytes) > 1024 * 1024:
        raise ValueError("fact_digest_canonical_input_too_large")
    return ActionTimeFactSetDigestV1(
        fact_snapshot_ids=fact_ids,
        fact_set_digest="sha256:" + sha256(canonical_bytes).hexdigest(),
    )


def _strict_digest_rows(
    control_state: Mapping[str, Any],
    table_name: str,
) -> list[dict[str, Any]]:
    expected_columns = CAPABILITY_DIGEST_TABLE_COLUMNS[table_name]
    rows = _rows(control_state.get(table_name))
    for row in rows:
        if set(row) != set(expected_columns):
            raise ValueError(f"digest_row_shape_invalid:{table_name}")
    return sorted(rows, key=lambda row: str(row[expected_columns[0]]))


def _canonical_sql_value(value: Any, *, json_semantic: bool) -> list[Any]:
    if json_semantic:
        return _canonical_json_value(value)
    if value is None:
        return ["sql:null"]
    if type(value) is bool:
        return ["sql:bool", value]
    if type(value) is int:
        return ["sql:int", str(value)]
    if isinstance(value, Decimal):
        return ["sql:decimal", _canonical_decimal(value)]
    if isinstance(value, float):
        raise ValueError("binary_float_forbidden")
    if isinstance(value, str):
        return ["sql:text", value]
    raise ValueError(f"unsupported_sql_scalar:{type(value).__name__}")


def _canonical_json_value(value: Any) -> list[Any]:
    if value is None:
        return ["json:null"]
    if type(value) is bool:
        return ["json:bool", value]
    if type(value) is int:
        return ["json:number", _canonical_decimal(Decimal(value))]
    if isinstance(value, Decimal):
        return ["json:number", _canonical_decimal(value)]
    if isinstance(value, float):
        raise ValueError("binary_float_forbidden")
    if isinstance(value, str):
        return ["json:string", value]
    if isinstance(value, list):
        return ["json:array", [_canonical_json_value(item) for item in value]]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("json_object_key_must_be_string")
        return [
            "json:object",
            [
                [key, _canonical_json_value(value[key])]
                for key in sorted(value)
            ],
        ]
    raise ValueError(f"unsupported_json_scalar:{type(value).__name__}")


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("non_finite_decimal_forbidden")
    if value.is_zero():
        return "0e0"
    normalized = value.normalize()
    sign, digits, exponent = normalized.as_tuple()
    coefficient = ("-" if sign else "") + "".join(str(digit) for digit in digits)
    return f"{coefficient}e{exponent}"


def record_runtime_release_activation(
    conn: sa.engine.Connection,
    *,
    runtime_head: str,
    release_name: str,
    verification_ref: str,
    now_ms: int,
) -> dict[str, Any]:
    """Project an exact postdeploy-verified release into bounded PG truth."""

    runtime_head = str(runtime_head or "").strip()
    release_name = str(release_name or "").strip()
    verification_ref = str(verification_ref or "").strip()
    if not runtime_head or not release_name or not verification_ref:
        return {
            "status": "blocked",
            "first_blocker": "release_activation_identity_incomplete",
            "runtime_head": runtime_head,
            "exchange_write_called": False,
        }
    identity = json.dumps(
        {
            "release_name": release_name,
            "runtime_head": runtime_head,
            "verification_ref": verification_ref,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    watermark = "runtime_release_activation:" + sha256(
        identity.encode("utf-8")
    ).hexdigest()
    with conn.begin_nested():
        materialize_runtime_process_outcome(
            conn,
            process_name=RELEASE_ACTIVATION_PROCESS_NAME,
            scope_key=RELEASE_ACTIVATION_SCOPE_KEY,
            run_id=f"release:{release_name}",
            result_status="runtime_release_activation_completed",
            blockers=[],
            started_at_ms=now_ms,
            completed_at_ms=now_ms,
            runtime_head=runtime_head,
            source_watermark=watermark,
        )
    return {
        "status": "runtime_release_activation_completed",
        "first_blocker": None,
        "runtime_head": runtime_head,
        "release_name": release_name,
        "signal_created": False,
        "ticket_created": False,
        "exchange_write_called": False,
        "order_created": False,
        "runtime_authority_created": False,
    }


def certify_action_time_capabilities(
    conn: sa.engine.Connection,
    *,
    control_state: Mapping[str, Any],
    runtime_head: str,
    certification_ref: str,
    expected_lane_count: int,
    now_ms: int,
) -> dict[str, Any]:
    """Upsert bounded release capability rows without creating trade authority."""

    runtime_head = str(runtime_head or "").strip()
    certification_ref = str(certification_ref or "").strip()
    blockers: list[str] = []
    if not runtime_head:
        blockers.append("runtime_head_required")
    if not certification_ref:
        blockers.append("certification_ref_required")
    observed_runtime_head = _current_runtime_head(control_state)
    if not observed_runtime_head:
        blockers.append("current_runtime_head_missing")
    elif runtime_head and observed_runtime_head != runtime_head:
        blockers.append("runtime_head_mismatch")
    try:
        identities = build_action_time_capability_identities(control_state)
    except ActionTimeCapabilityIdentityError as exc:
        blockers.append(str(exc))
        identities = []
    if not identities and not blockers:
        blockers.append("active_candidate_scope_missing")
    if identities and len(identities) != int(expected_lane_count):
        blockers.append("certified_lane_count_mismatch")
    if blockers:
        return _certification_result(
            status="blocked",
            certified_lane_count=0,
            first_blocker=blockers[0],
            blockers=blockers,
        )

    with conn.begin_nested():
        for identity in identities:
            materialize_runtime_process_outcome(
                conn,
                process_name=PROCESS_NAME,
                scope_key=identity.scope_key,
                run_id=f"certification:{certification_ref}",
                result_status="action_time_capability_certification_completed",
                blockers=[],
                started_at_ms=now_ms,
                completed_at_ms=now_ms,
                runtime_head=runtime_head,
                source_watermark=identity.source_watermark,
                lane_identity=identity.runtime_lane_identity,
            )
    return _certification_result(
        status="action_time_capability_certified",
        certified_lane_count=len(identities),
        first_blocker=None,
        blockers=[],
    )


def build_action_time_capability_identities(
    control_state: Mapping[str, Any],
) -> list[ActionTimeCapabilityIdentity]:
    """Build one deterministic identity for every current active candidate."""

    groups = {
        str(row.get("strategy_group_id") or ""): row
        for row in _rows(control_state.get("strategy_groups"))
        if row.get("status") == "active"
    }
    versions = {
        str(row.get("strategy_group_version_id") or ""): row
        for row in _rows(control_state.get("strategy_group_versions"))
        if row.get("status") == "current"
    }
    bindings = _one_by(
        control_state.get("candidate_scope_event_bindings"),
        key="candidate_scope_id",
        status="active",
    )
    events = {
        str(row.get("event_spec_id") or ""): row
        for row in _rows(control_state.get("strategy_side_event_specs"))
        if row.get("status") == "current"
    }
    runtime_bindings = _one_by(
        control_state.get("runtime_scope_bindings"),
        key="candidate_scope_id",
        status="active",
    )
    runtimes_by_lane: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for runtime in _rows(control_state.get("strategy_runtime_instances")):
        if runtime.get("status") != "active":
            continue
        runtimes_by_lane[
            (
                str(runtime.get("strategy_family_id") or ""),
                str(runtime.get("symbol") or ""),
                str(runtime.get("side") or ""),
            )
        ].append(runtime)
    policies = {
        str(row.get("policy_current_id") or ""): row
        for row in _rows(control_state.get("owner_policy_current"))
    }
    facts_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _rows(control_state.get("strategy_event_required_facts")):
        if row.get("status") == "current":
            facts_by_event[str(row.get("event_spec_id") or "")].append(row)

    identities: list[ActionTimeCapabilityIdentity] = []
    for candidate in sorted(
        (
            row
            for row in _rows(control_state.get("candidate_scope"))
            if row.get("status") == "active"
        ),
        key=lambda row: (
            str(row.get("strategy_group_id") or ""),
            int(row.get("priority_rank") or 999),
            str(row.get("symbol") or ""),
            str(row.get("side") or ""),
        ),
    ):
        candidate_id = _required(candidate, "candidate_scope_id")
        group_id = _required(candidate, "strategy_group_id")
        symbol = _required(candidate, "symbol")
        side = _required(candidate, "side")
        group = groups.get(group_id)
        if group is None:
            raise _identity_error(candidate_id, "strategy_group_missing")
        group_version_id = _required(group, "current_version_id")
        if group_version_id not in versions:
            raise _identity_error(candidate_id, "strategy_group_version_missing")
        binding = bindings.get(candidate_id)
        if binding is None:
            raise _identity_error(candidate_id, "event_binding_missing")
        event_spec_id = _required(binding, "event_spec_id")
        event = events.get(event_spec_id)
        if event is None:
            raise _identity_error(candidate_id, "event_spec_missing")
        if str(event.get("strategy_group_version_id") or "") != group_version_id:
            raise _identity_error(candidate_id, "event_spec_version_mismatch")
        if not _event_execution_capability_ready(event):
            raise _identity_error(
                candidate_id,
                "event_execution_capability_not_certified",
            )
        runtime = runtime_bindings.get(candidate_id)
        if runtime is None:
            raise _identity_error(candidate_id, "runtime_scope_binding_missing")
        runtime_instances = runtimes_by_lane.get((group_id, symbol, side), [])
        if not runtime_instances:
            raise _identity_error(candidate_id, "runtime_instance_missing")
        if len(runtime_instances) != 1:
            raise _identity_error(candidate_id, "runtime_instance_ambiguous")
        runtime_instance = runtime_instances[0]
        if str(runtime_instance.get("strategy_family_version_id") or "") != str(
            event.get("strategy_group_version_id") or ""
        ):
            raise _identity_error(candidate_id, "runtime_instance_version_mismatch")
        policy_id = _required(candidate, "policy_current_id")
        policy = policies.get(policy_id)
        if policy is None:
            raise _identity_error(candidate_id, "owner_policy_missing")
        if str(runtime.get("policy_current_id") or "") != policy_id:
            raise _identity_error(candidate_id, "runtime_policy_mismatch")
        runtime_profile_id = _required(runtime, "runtime_profile_id")
        if str(policy.get("runtime_profile_id") or "") != runtime_profile_id:
            raise _identity_error(candidate_id, "runtime_profile_mismatch")
        if not _runtime_scope_ready(runtime):
            raise _identity_error(candidate_id, "runtime_scope_not_certifiable")
        if not _owner_policy_ready(policy):
            raise _identity_error(candidate_id, "owner_policy_not_certifiable")
        fact_rows = facts_by_event.get(event_spec_id, [])
        if not fact_rows:
            raise _identity_error(candidate_id, "required_fact_contract_missing")
        fact_refs = tuple(sorted(_fact_contract_ref(row) for row in fact_rows))
        try:
            runtime_lane_identity = RuntimeLaneIdentity(
                candidate_scope_id=candidate_id,
                candidate_scope_event_binding_id=_required(binding, "binding_id"),
                runtime_scope_binding_id=_required(
                    runtime,
                    "runtime_scope_binding_id",
                ),
                runtime_instance_id=_required(
                    runtime_instance,
                    "runtime_instance_id",
                ),
                runtime_profile_id=runtime_profile_id,
                policy_current_id=policy_id,
                strategy_group_id=group_id,
                strategy_group_version_id=group_version_id,
                symbol=symbol,
                asset_class=_required(candidate, "asset_class"),
                side=side,
                event_spec_id=event_spec_id,
                event_spec_version=_required(event, "event_spec_version"),
                event_id=_required(event, "event_id"),
                timeframe=_required(event, "timeframe"),
                time_authority=_required(event, "time_authority"),
            )
        except (TypeError, ValueError) as exc:
            raise _identity_error(
                candidate_id,
                f"runtime_lane_identity_invalid:{exc}",
            ) from exc
        identity_values = {
            "runtime_lane_identity": runtime_lane_identity.model_dump(mode="json"),
            "candidate_scope_id": candidate_id,
            "strategy_group_id": group_id,
            "symbol": symbol,
            "side": side,
            "scope_key": f"lane:{group_id}:{symbol}:{side}",
            "strategy_group_version_id": group_version_id,
            "event_spec_id": event_spec_id,
            "event_spec_version_id": str(
                event.get("event_spec_version") or event_spec_id
            ),
            "event_contract_ref": _contract_ref(
                event,
                keys=(
                    "event_spec_id",
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
                ),
            ),
            "required_fact_contract_refs": fact_refs,
            "runtime_scope_binding_id": _required(
                runtime,
                "runtime_scope_binding_id",
            ),
            "runtime_scope_contract_ref": _contract_ref(
                runtime,
                keys=(
                    "runtime_scope_binding_id",
                    "candidate_scope_id",
                    "policy_current_id",
                    "runtime_profile_id",
                    "selected_strategygroup_scope",
                    "symbol_side_scope_closed",
                    "notional_leverage_scope_closed",
                    "live_submit_allowed",
                    "server_runtime_coverage_required",
                    "conditional_hard_gates",
                ),
            ),
            "owner_policy_version_id": _policy_version_id(policy),
            "owner_policy_contract_ref": _contract_ref(
                policy,
                keys=(
                    "policy_current_id",
                    "policy_event_ids",
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
            ),
            "runtime_profile_id": runtime_profile_id,
        }
        digest = sha256(
            json.dumps(
                identity_values,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        identities.append(
            ActionTimeCapabilityIdentity(
                **identity_values,
                source_watermark=f"action_time_capability:{digest}",
            )
        )
    return identities


def current_action_time_capability_truth_by_lane(
    control_state: Mapping[str, Any],
    *,
    current_runtime_head: str,
) -> dict[tuple[str, str, str], ActionTimeCapabilityTruth]:
    """Reduce current PG certification outcomes against current lane identity."""

    candidate_by_id = {
        str(row.get("candidate_scope_id") or ""): row
        for row in _rows(control_state.get("candidate_scope"))
        if row.get("status") == "active"
    }
    remaining_candidate_ids = set(candidate_by_id)
    identities: list[ActionTimeCapabilityIdentity] = []
    invalid_lanes: dict[tuple[str, str, str], str] = {}
    while remaining_candidate_ids:
        scoped_control_state = {
            **control_state,
            "candidate_scope": [
                candidate_by_id[candidate_id]
                for candidate_id in sorted(remaining_candidate_ids)
            ],
        }
        try:
            identities.extend(
                build_action_time_capability_identities(scoped_control_state)
            )
            break
        except ActionTimeCapabilityIdentityError as exc:
            candidate = candidate_by_id.get(exc.candidate_scope_id)
            if candidate is None:
                raise
            invalid_lanes[
                (
                    str(candidate.get("strategy_group_id") or ""),
                    str(candidate.get("symbol") or ""),
                    str(candidate.get("side") or ""),
                )
            ] = exc.reason
            remaining_candidate_ids.remove(exc.candidate_scope_id)
    outcomes = {
        str(row.get("scope_key") or ""): row
        for row in sorted(
            _rows(control_state.get("runtime_process_outcomes")),
            key=lambda item: int(item.get("updated_at_ms") or 0),
        )
        if row.get("process_name") == PROCESS_NAME
    }
    truths: dict[tuple[str, str, str], ActionTimeCapabilityTruth] = {}
    for lane_key, reason in invalid_lanes.items():
        truths[lane_key] = ActionTimeCapabilityTruth(
            identity=None,
            certified=False,
            first_blocker=FIRST_BLOCKER,
            reason=reason,
        )
    for identity in identities:
        outcome = outcomes.get(identity.scope_key)
        reason = "certified"
        certified = True
        if outcome is None or outcome.get("process_state") != "succeeded":
            reason = "certification_missing"
            certified = False
        elif not current_runtime_head or str(outcome.get("runtime_head") or "") != current_runtime_head:
            reason = "runtime_head_mismatch"
            certified = False
        elif str(outcome.get("source_watermark") or "") != identity.source_watermark:
            reason = "lineage_mismatch"
            certified = False
        truths[identity.lane_key] = ActionTimeCapabilityTruth(
            identity=identity,
            certified=certified,
            first_blocker=None if certified else FIRST_BLOCKER,
            reason=reason,
            certification_ref=str(outcome.get("run_id") or "") if outcome else "",
            certified_runtime_head=(
                str(outcome.get("runtime_head") or "") if outcome else ""
            ),
        )
    return truths


def current_runtime_head(control_state: Mapping[str, Any]) -> str:
    """Return the newest server-observed release head for capability binding."""

    return _current_runtime_head(control_state)


def _current_runtime_head(control_state: Mapping[str, Any]) -> str:
    explicit = str(control_state.get("current_runtime_head") or "").strip()
    if explicit:
        return explicit
    activation_rows = sorted(
        (
            row
            for row in _rows(control_state.get("runtime_process_outcomes"))
            if row.get("process_name") == RELEASE_ACTIVATION_PROCESS_NAME
            and row.get("scope_key") == RELEASE_ACTIVATION_SCOPE_KEY
            and row.get("process_state") == "succeeded"
            and str(row.get("runtime_head") or "").strip()
        ),
        key=lambda row: int(row.get("updated_at_ms") or 0),
        reverse=True,
    )
    if activation_rows:
        return str(activation_rows[0].get("runtime_head") or "")
    monitor_rows = sorted(
        (
            row
            for row in _rows(control_state.get("server_monitor_runs"))
            if str(row.get("runtime_head") or "").strip()
        ),
        key=lambda row: int(row.get("created_at_ms") or 0),
        reverse=True,
    )
    if monitor_rows:
        return str(monitor_rows[0].get("runtime_head") or "")
    certification_heads = {
        str(row.get("runtime_head") or "").strip()
        for row in _rows(control_state.get("runtime_process_outcomes"))
        if row.get("process_name") == PROCESS_NAME
        and row.get("process_state") == "succeeded"
        and str(row.get("runtime_head") or "").strip()
    }
    if len(certification_heads) == 1:
        return next(iter(certification_heads))
    return ""


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _one_by(value: Any, *, key: str, status: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in _rows(value):
        if row.get("status") != status:
            continue
        identity = str(row.get(key) or "")
        if identity in result:
            raise ActionTimeCapabilityIdentityError(
                f"duplicate_current_identity:{key}:{identity}"
            )
        result[identity] = row
    return result


def _required(row: Mapping[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ActionTimeCapabilityIdentityError(f"required_identity_missing:{key}")
    return value


def _identity_error(candidate_id: str, reason: str) -> ActionTimeCapabilityIdentityError:
    return ActionTimeCapabilityIdentityError(candidate_id, reason)


def _policy_version_id(policy: Mapping[str, Any]) -> str:
    event_ids = policy.get("policy_event_ids")
    if isinstance(event_ids, list) and event_ids:
        return "|".join(sorted(str(value) for value in event_ids))
    return _required(policy, "policy_current_id")


def _fact_contract_ref(row: Mapping[str, Any]) -> str:
    values = {
        key: row.get(key)
        for key in (
            "event_required_fact_id",
            "required_facts_version_id",
            "fact_key",
            "fact_role",
            "fact_surface",
            "operator",
            "expected_value",
            "disable_on_match",
            "freshness_ms",
            "required_for_promotion",
            "required_for_ticket",
            "required_for_finalgate",
            "missing_blocker_class",
            "failed_blocker_class",
            "value_source",
        )
    }
    return json.dumps(values, sort_keys=True, separators=(",", ":"), default=str)


def _contract_ref(row: Mapping[str, Any], *, keys: tuple[str, ...]) -> str:
    return json.dumps(
        {key: row.get(key) for key in keys},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _event_execution_capability_ready(event: Mapping[str, Any]) -> bool:
    return (
        event.get("execution_eligibility_enabled") is True
        and event.get("declared_signal_grade")
        in {"trial_grade_signal", "production_grade_signal"}
        and event.get("declared_required_execution_mode")
        in {"trial_live", "production_live"}
    )


def _runtime_scope_ready(runtime: Mapping[str, Any]) -> bool:
    return (
        runtime.get("selected_strategygroup_scope") is True
        and runtime.get("symbol_side_scope_closed") is True
        and runtime.get("notional_leverage_scope_closed") is True
        and runtime.get("live_submit_allowed") is True
    )


def _owner_policy_ready(policy: Mapping[str, Any]) -> bool:
    return (
        policy.get("enabled_state") == "enabled"
        and policy.get("pretrade_candidate_allowed") is True
        and policy.get("action_time_rehearsal_allowed") is True
        and policy.get("live_submit_allowed")
        in {"scoped", "conditional_hard_gated"}
    )


def _certification_result(
    *,
    status: str,
    certified_lane_count: int,
    first_blocker: str | None,
    blockers: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "certified_lane_count": certified_lane_count,
        "first_blocker": first_blocker,
        "blockers": blockers,
        "signal_created": False,
        "promotion_created": False,
        "action_time_lane_created": False,
        "ticket_created": False,
        "runtime_safety_state_created": False,
        "finalgate_called": False,
        "operation_layer_called": False,
        "exchange_write_called": False,
        "order_created": False,
        "runtime_authority_created": False,
        "owner_policy_changed": False,
        "runtime_profile_changed": False,
        "order_sizing_changed": False,
    }
