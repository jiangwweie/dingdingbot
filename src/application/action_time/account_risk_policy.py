"""Account-scoped Owner policy for dual-position risk capacity."""

from __future__ import annotations

from hashlib import sha256
from decimal import Decimal
from typing import Sequence
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
import sqlalchemy as sa
from src.domain.account_risk import AccountRiskPolicy, RiskClusterMembership


class AccountRiskPolicyCurrentProjection(BaseModel):
    """Current policy plus the immutable Owner command that authorized it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: AccountRiskPolicy
    source_event_id: str


def append_account_risk_policy_event(
    conn: sa.Connection,
    *,
    account_id: str,
    runtime_profile_id: str,
    event_type: str,
    policy: AccountRiskPolicy,
    created_by: str,
    now_ms: int,
    operation_id: str | None = None,
) -> AccountRiskPolicy:
    """Append policy provenance and replace its single account current projection."""

    _require_text(account_id, "account_id")
    _require_text(runtime_profile_id, "runtime_profile_id")
    _require_text(event_type, "event_type")
    _require_text(created_by, "created_by")
    if now_ms <= 0:
        raise ValueError("now_ms must be positive")
    operation_id = operation_id or uuid4().hex
    _require_text(operation_id, "operation_id")

    events = _table(conn, "brc_account_risk_policy_events")
    current = _table(conn, "brc_account_risk_policy_current")
    event_id = _stable_id(
        "account_risk_policy_event",
        account_id,
        runtime_profile_id,
        operation_id,
    )
    payload = _payload(policy)
    event_row = {
        "account_risk_policy_event_id": event_id,
        "account_id": account_id,
        "runtime_profile_id": runtime_profile_id,
        "event_type": event_type,
        "risk_policy_version": policy.risk_policy_version,
        "payload": _event_payload(payload),
        "created_at_ms": now_ms,
        "created_by": created_by,
    }
    existing_event = conn.execute(
        sa.select(events).where(
            events.c.account_risk_policy_event_id == event_id
        )
    ).mappings().one_or_none()
    if existing_event is not None:
        if not _same_policy_operation(existing_event, event_row):
            raise ValueError("account risk policy operation id was reused")
        return policy
    else:
        conn.execute(events.insert().values(**event_row))

    current_row = {
        "account_risk_policy_current_id": _stable_id(
            "account_risk_policy_current", account_id, runtime_profile_id
        ),
        "account_id": account_id,
        "runtime_profile_id": runtime_profile_id,
        "source_event_id": event_id,
        "updated_at_ms": now_ms,
        **payload,
    }
    existing = conn.execute(
        sa.select(current.c.account_risk_policy_current_id).where(
            current.c.account_id == account_id,
            current.c.runtime_profile_id == runtime_profile_id,
        )
    ).first()
    if existing:
        conn.execute(
            current.update()
            .where(
                current.c.account_id == account_id,
                current.c.runtime_profile_id == runtime_profile_id,
            )
            .values(**current_row)
        )
    else:
        conn.execute(current.insert().values(**current_row))
    return policy


def load_account_risk_policy_current(
    conn: sa.Connection,
    *,
    account_id: str,
    runtime_profile_id: str,
) -> AccountRiskPolicy | None:
    """Load only the current policy for the exact account/profile scope."""

    projection = load_account_risk_policy_current_projection(
        conn,
        account_id=account_id,
        runtime_profile_id=runtime_profile_id,
    )
    return projection.policy if projection is not None else None


def load_account_risk_policy_current_projection(
    conn: sa.Connection,
    *,
    account_id: str,
    runtime_profile_id: str,
) -> AccountRiskPolicyCurrentProjection | None:
    """Load current policy with the immutable event identity FinalGate must bind."""

    current = _table(conn, "brc_account_risk_policy_current")
    row = conn.execute(
        sa.select(current).where(
            current.c.account_id == account_id,
            current.c.runtime_profile_id == runtime_profile_id,
        )
    ).mappings().one_or_none()
    if row is None:
        return None
    return AccountRiskPolicyCurrentProjection(
        policy=_policy_from_row(row),
        source_event_id=str(row["source_event_id"]),
    )


def replace_risk_cluster_memberships(
    conn: sa.Connection,
    *,
    risk_policy_version: str,
    memberships: Sequence[RiskClusterMembership],
    created_by: str,
    now_ms: int,
) -> None:
    """Replace one policy version's explicit static cluster mapping atomically."""

    _require_text(risk_policy_version, "risk_policy_version")
    _require_text(created_by, "created_by")
    if now_ms <= 0:
        raise ValueError("now_ms must be positive")
    instrument_ids = [item.exchange_instrument_id for item in memberships]
    if len(instrument_ids) != len(set(instrument_ids)):
        raise ValueError("risk cluster memberships must be unique per instrument")
    table = _table(conn, "brc_risk_cluster_memberships")
    conn.execute(
        table.delete().where(table.c.risk_policy_version == risk_policy_version)
    )
    for membership in memberships:
        conn.execute(
            table.insert().values(
                risk_cluster_membership_id=_stable_id(
                    "risk_cluster_membership",
                    risk_policy_version,
                    membership.exchange_instrument_id,
                ),
                risk_policy_version=risk_policy_version,
                exchange_instrument_id=membership.exchange_instrument_id,
                risk_cluster_id=membership.risk_cluster_id,
                created_at_ms=now_ms,
                created_by=created_by,
            )
        )


def _table(conn: sa.Connection, table_name: str) -> sa.Table:
    return sa.Table(table_name, sa.MetaData(), autoload_with=conn)


def _payload(policy: AccountRiskPolicy) -> dict[str, object]:
    return {
        "risk_policy_version": policy.risk_policy_version,
        "planned_stop_risk_fraction": policy.planned_stop_risk_fraction,
        "max_concurrent_positions": policy.max_concurrent_positions,
        "max_portfolio_open_risk_fraction": policy.max_portfolio_open_risk_fraction,
        "max_cluster_open_risk_fraction": policy.max_cluster_open_risk_fraction,
        "max_portfolio_initial_margin_fraction": policy.max_portfolio_initial_margin_fraction,
        "max_leverage": policy.max_leverage,
        "max_new_action_time_lanes": policy.max_new_action_time_lanes,
        "automatic_downsize_enabled": policy.automatic_downsize_enabled,
        "unknown_exposure_policy": policy.unknown_exposure_policy,
        "activation_state": policy.activation_state,
    }


def _event_payload(payload: dict[str, object]) -> dict[str, object]:
    """Keep JSON audit payload exact without leaking Decimal into the driver."""

    return {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in payload.items()
    }


def _same_policy_operation(
    existing: dict[str, object], expected: dict[str, object]
) -> bool:
    return all(
        existing.get(field) == expected[field]
        for field in (
            "account_id",
            "runtime_profile_id",
            "event_type",
            "risk_policy_version",
            "payload",
            "created_by",
        )
    )


def _policy_from_row(row: dict[str, object]) -> AccountRiskPolicy:
    return AccountRiskPolicy(
        risk_policy_version=str(row["risk_policy_version"]),
        planned_stop_risk_fraction=_decimal(row["planned_stop_risk_fraction"]),
        max_concurrent_positions=int(row["max_concurrent_positions"]),
        max_portfolio_open_risk_fraction=_decimal(
            row["max_portfolio_open_risk_fraction"]
        ),
        max_cluster_open_risk_fraction=_decimal(row["max_cluster_open_risk_fraction"]),
        max_portfolio_initial_margin_fraction=_decimal(
            row["max_portfolio_initial_margin_fraction"]
        ),
        max_leverage=int(row["max_leverage"]),
        max_new_action_time_lanes=int(row["max_new_action_time_lanes"]),
        automatic_downsize_enabled=bool(row["automatic_downsize_enabled"]),
        unknown_exposure_policy=str(row["unknown_exposure_policy"]),
        activation_state=str(row["activation_state"]),
    )


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return f"{prefix}:{sha256(raw).hexdigest()[:32]}"


def _require_text(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
