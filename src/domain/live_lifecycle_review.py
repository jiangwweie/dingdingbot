"""Live bounded-action lifecycle review ledger contracts."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


LiveLifecycleStatus = Literal[
    "pending_open",
    "protected_open",
    "closed_reviewed",
    "recovery_required",
]


class BrcLiveLifecycleReviewRecord(BaseModel):
    review_id: str
    authorization_id: str
    carrier_id: str
    strategy_family_id: Optional[str] = None
    runtime_instance_id: Optional[str] = None
    trial_binding_id: Optional[str] = None
    strategy_family_version_id: Optional[str] = None
    signal_evaluation_id: Optional[str] = None
    order_candidate_id: Optional[str] = None
    symbol: str
    side: Literal["long", "short"]
    quantity: str
    max_notional: Optional[str] = None
    leverage: Optional[str] = None
    max_attempts: Optional[int] = None
    protection_mode: str = "single_tp_plus_sl"
    review_requirement: str = "post_action_review_required"
    lifecycle_status: LiveLifecycleStatus
    review_status: Literal["pending_open", "closed_reviewed", "recovery_required"]
    final_gate_result: Optional[str] = None
    protection_status: Optional[str] = None
    execution_intent_id: Optional[str] = None
    entry_order_id: Optional[str] = None
    entry_exchange_order_id: Optional[str] = None
    tp_order_ids: list[str] = Field(default_factory=list)
    tp_exchange_order_ids: list[str] = Field(default_factory=list)
    sl_order_id: Optional[str] = None
    sl_exchange_order_id: Optional[str] = None
    tp_price: Optional[str] = None
    sl_trigger: Optional[str] = None
    owner_risk_acceptance: Optional[str] = None
    hard_gates_passed: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    action_allowed: Literal[False] = False
    creates_authorization: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    places_order: Literal[False] = False
    mutates_exchange: Literal[False] = False
    grants_trading_permission: Literal[False] = False
    frontend_action_enabled: Literal[False] = False
    created_by: str = "codex"
    created_at_ms: int
    updated_at_ms: int

    @model_validator(mode="after")
    def _validate_no_action_authority(self) -> "BrcLiveLifecycleReviewRecord":
        if (
            self.action_allowed
            or self.creates_authorization
            or self.creates_execution_intent
            or self.places_order
            or self.mutates_exchange
            or self.grants_trading_permission
            or self.frontend_action_enabled
        ):
            raise ValueError("live lifecycle review records cannot grant or execute action")
        return self
