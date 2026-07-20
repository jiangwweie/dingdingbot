"""Owner-readable account capacity state without execution internals."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AccountRiskOwnerState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: str
    summary: str
    owner_action_required: bool


def account_risk_owner_state_from_budget(row: dict[str, object]) -> AccountRiskOwnerState:
    """Collapse a Budget Current row into the bounded Owner product language."""

    slots = max(0, int(row.get("claimed_position_slots") or 0))
    maximum = max(1, int(row.get("max_concurrent_positions") or 1))
    reconciliation_state = str(row.get("reconciliation_state") or "")
    new_entry_allowed = row.get("new_entry_allowed") is True
    if reconciliation_state != "matched":
        return AccountRiskOwnerState(
            state="needs_intervention",
            summary="账户事实需要重新对账；系统已停止新开仓，现有保护继续运行",
            owner_action_required=True,
        )
    if slots >= maximum:
        return AccountRiskOwnerState(
            state="running",
            summary=f"当前 {slots}/{maximum} 个仓位正在运行；新机会暂不入场",
            owner_action_required=False,
        )
    if not new_entry_allowed:
        return AccountRiskOwnerState(
            state="temporarily_unavailable",
            summary="账户当前风险或保证金容量不足；系统已停止新开仓，现有保护继续运行",
            owner_action_required=False,
        )
    return AccountRiskOwnerState(
        state="running",
        summary=f"当前 {slots}/{maximum} 个仓位正在运行；仍可接收一个不同品种机会",
        owner_action_required=False,
    )
