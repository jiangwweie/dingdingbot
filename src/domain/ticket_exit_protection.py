"""Pure resolution of one Ticket's active exit-protection generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Mapping, Sequence


ExitProtectionRole = Literal["SL", "TP1", "RUNNER_SL"]
DEFAULT_REPLACEMENT_GRACE_MS = 90_000

_ACTIVE_STATUSES = frozenset(
    {
        "planned",
        "submitted",
        "open",
        "partially_filled",
        "cancel_pending",
        "replace_pending",
    }
)
_REPLACEMENT_NEW_STATUSES = frozenset(
    {"planned", "submitted", "open", "partially_filled"}
)
_REPLACEMENT_OLD_STATUSES = frozenset({"cancel_pending", "replace_pending"})


class ActiveProtectionResolutionState(str, Enum):
    ACTIVE_ONE = "active_one"
    REPLACEMENT_OVERLAP = "replacement_overlap"
    MISSING_WHILE_OPEN = "missing_while_open"
    AMBIGUOUS_ACTIVE = "ambiguous_active"
    BROKEN_LINEAGE = "broken_lineage"
    CROSS_SET = "cross_set"
    TERMINAL_POSITION = "terminal_position"


@dataclass(frozen=True, slots=True)
class ExitProtectionOrderView:
    exit_protection_order_id: str
    exit_protection_set_id: str
    role: str
    local_order_id: str
    exchange_order_id: str
    status: str
    replaces_exit_protection_order_id: str | None
    created_at_ms: int
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class ActiveProtectionResolution:
    state: ActiveProtectionResolutionState
    role: ExitProtectionRole
    active_order: ExitProtectionOrderView | None
    blockers: tuple[str, ...]
    superseded_order_ids: tuple[str, ...] = ()
    lineage_leaf: ExitProtectionOrderView | None = None

    @property
    def fails_closed(self) -> bool:
        return self.state in {
            ActiveProtectionResolutionState.AMBIGUOUS_ACTIVE,
            ActiveProtectionResolutionState.BROKEN_LINEAGE,
            ActiveProtectionResolutionState.CROSS_SET,
        }


def exit_protection_order_view_from_mapping(
    row: Mapping[str, Any],
) -> ExitProtectionOrderView:
    replacement_id = str(row.get("replaces_exit_protection_order_id") or "").strip()
    return ExitProtectionOrderView(
        exit_protection_order_id=str(row.get("exit_protection_order_id") or ""),
        exit_protection_set_id=str(row.get("exit_protection_set_id") or ""),
        role=str(row.get("role") or "").upper(),
        local_order_id=str(row.get("local_order_id") or ""),
        exchange_order_id=str(row.get("exchange_order_id") or ""),
        status=str(row.get("status") or "").lower(),
        replaces_exit_protection_order_id=replacement_id or None,
        created_at_ms=int(row.get("created_at_ms") or 0),
        updated_at_ms=int(row.get("updated_at_ms") or 0),
    )


def resolve_active_exit_protection_rows(
    *,
    exit_protection_set_id: str,
    role: ExitProtectionRole,
    orders: Sequence[Mapping[str, Any]],
    position_is_open: bool,
    now_ms: int,
    replacement_grace_ms: int,
) -> ActiveProtectionResolution:
    return resolve_active_exit_protection(
        exit_protection_set_id=exit_protection_set_id,
        role=role,
        orders=tuple(exit_protection_order_view_from_mapping(row) for row in orders),
        position_is_open=position_is_open,
        now_ms=now_ms,
        replacement_grace_ms=replacement_grace_ms,
    )


def order_mapping_for_view(
    orders: Sequence[Mapping[str, Any]],
    view: ExitProtectionOrderView | None,
) -> dict[str, Any]:
    if view is None:
        return {}
    for row in orders:
        if str(row.get("exit_protection_order_id") or "") == view.exit_protection_order_id:
            return dict(row)
    return {}


def resolve_active_exit_protection(
    *,
    exit_protection_set_id: str,
    role: ExitProtectionRole,
    orders: Sequence[ExitProtectionOrderView],
    position_is_open: bool,
    now_ms: int,
    replacement_grace_ms: int,
) -> ActiveProtectionResolution:
    """Resolve one exact protection generation without I/O or order mutation."""

    role_name = role.upper()
    blocker_prefix = f"active_{role_name.lower()}"
    if any(order.exit_protection_set_id != exit_protection_set_id for order in orders):
        return ActiveProtectionResolution(
            state=ActiveProtectionResolutionState.CROSS_SET,
            role=role,
            active_order=None,
            blockers=(f"{blocker_prefix}_cross_set_row",),
        )

    role_orders = tuple(order for order in orders if order.role.upper() == role_name)
    by_id = {order.exit_protection_order_id: order for order in orders}
    if len(by_id) != len(orders) or any(
        order.replaces_exit_protection_order_id
        and order.replaces_exit_protection_order_id not in by_id
        for order in orders
    ):
        return ActiveProtectionResolution(
            state=ActiveProtectionResolutionState.BROKEN_LINEAGE,
            role=role,
            active_order=None,
            blockers=(f"{blocker_prefix}_replacement_lineage_broken",),
        )
    active = tuple(order for order in role_orders if order.status in _ACTIVE_STATUSES)
    lineage_leaf = _single_lineage_leaf(role_orders)
    if not position_is_open:
        return ActiveProtectionResolution(
            state=ActiveProtectionResolutionState.TERMINAL_POSITION,
            role=role,
            active_order=lineage_leaf,
            blockers=(),
            lineage_leaf=lineage_leaf,
        )
    if not active:
        return ActiveProtectionResolution(
            state=ActiveProtectionResolutionState.MISSING_WHILE_OPEN,
            role=role,
            active_order=None,
            blockers=(f"{blocker_prefix}_protection_missing",),
            lineage_leaf=lineage_leaf,
        )
    if len(active) == 1:
        return ActiveProtectionResolution(
            state=ActiveProtectionResolutionState.ACTIVE_ONE,
            role=role,
            active_order=active[0],
            blockers=(),
            lineage_leaf=lineage_leaf,
        )

    overlap = _linked_replacement_overlap(
        active,
        now_ms=now_ms,
        replacement_grace_ms=replacement_grace_ms,
    )
    if overlap is not None:
        new_order, old_order = overlap
        return ActiveProtectionResolution(
            state=ActiveProtectionResolutionState.REPLACEMENT_OVERLAP,
            role=role,
            active_order=new_order,
            blockers=(),
            superseded_order_ids=(old_order.exit_protection_order_id,),
            lineage_leaf=lineage_leaf,
        )
    return ActiveProtectionResolution(
        state=ActiveProtectionResolutionState.AMBIGUOUS_ACTIVE,
        role=role,
        active_order=None,
        blockers=(f"{blocker_prefix}_protection_ambiguous",),
        lineage_leaf=lineage_leaf,
    )


def _linked_replacement_overlap(
    active: Sequence[ExitProtectionOrderView],
    *,
    now_ms: int,
    replacement_grace_ms: int,
) -> tuple[ExitProtectionOrderView, ExitProtectionOrderView] | None:
    if len(active) != 2 or replacement_grace_ms < 0:
        return None
    by_id = {order.exit_protection_order_id: order for order in active}
    for new_order in active:
        old_id = new_order.replaces_exit_protection_order_id
        old_order = by_id.get(str(old_id or ""))
        if old_order is None:
            continue
        if new_order.status not in _REPLACEMENT_NEW_STATUSES:
            continue
        if old_order.status not in _REPLACEMENT_OLD_STATUSES:
            continue
        overlap_started_ms = max(new_order.created_at_ms, old_order.updated_at_ms)
        overlap_age_ms = max(0, now_ms - overlap_started_ms)
        if overlap_age_ms <= replacement_grace_ms:
            return new_order, old_order
    return None


def _single_lineage_leaf(
    orders: Sequence[ExitProtectionOrderView],
) -> ExitProtectionOrderView | None:
    if not orders:
        return None
    replaced_ids = {
        str(order.replaces_exit_protection_order_id)
        for order in orders
        if order.replaces_exit_protection_order_id
    }
    leaves = tuple(
        order
        for order in orders
        if order.exit_protection_order_id not in replaced_ids
    )
    return leaves[0] if len(leaves) == 1 else None
