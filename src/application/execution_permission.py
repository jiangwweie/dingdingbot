"""Execution permission resolution for BRC non-execution handoffs.

This resolver computes the maximum BRC action depth allowed by configuration,
account facts, runtime safety, API-key capability, risk/capital evidence, and
the Operation Layer. It does not authorize orders by itself.
"""

from __future__ import annotations

import os
from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExecutionPermission(IntEnum):
    READ_ONLY = 0
    SIGNAL_ONLY = 1
    INTENT_RECORDING = 2
    EXECUTION_INTENT_ALLOWED = 3
    ORDER_ALLOWED = 4

    @property
    def value_name(self) -> str:
        return _PERMISSION_NAMES[self]

    @classmethod
    def from_value(cls, value: Any, *, default: Optional["ExecutionPermission"] = None) -> "ExecutionPermission":
        if isinstance(value, ExecutionPermission):
            return value
        if value is None:
            if default is not None:
                return default
            raise ValueError("execution permission is required")
        normalized = str(value).strip().lower()
        aliases = {
            "read_only": cls.READ_ONLY,
            "signal_only": cls.SIGNAL_ONLY,
            "intent_recording": cls.INTENT_RECORDING,
            "execution_intent_allowed": cls.EXECUTION_INTENT_ALLOWED,
            "order_allowed": cls.ORDER_ALLOWED,
        }
        if normalized not in aliases:
            raise ValueError(f"invalid execution permission: {value}")
        return aliases[normalized]


_PERMISSION_NAMES = {
    ExecutionPermission.READ_ONLY: "read_only",
    ExecutionPermission.SIGNAL_ONLY: "signal_only",
    ExecutionPermission.INTENT_RECORDING: "intent_recording",
    ExecutionPermission.EXECUTION_INTENT_ALLOWED: "execution_intent_allowed",
    ExecutionPermission.ORDER_ALLOWED: "order_allowed",
}


def parse_execution_permission_max(
    value: Any,
    *,
    default: ExecutionPermission = ExecutionPermission.READ_ONLY,
) -> ExecutionPermission:
    return ExecutionPermission.from_value(value, default=default)


def permission_allows(actual: Any, required: Any) -> bool:
    return ExecutionPermission.from_value(actual) >= ExecutionPermission.from_value(required)


class ExecutionPermissionResolution(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    requested_permission: ExecutionPermission
    configured_max_permission: ExecutionPermission
    api_key_capability: ExecutionPermission
    account_facts_permission: ExecutionPermission
    risk_capital_permission: ExecutionPermission
    runtime_safety_permission: ExecutionPermission
    operation_permission: ExecutionPermission
    final_permission: ExecutionPermission
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    downgrade_reason: Optional[str] = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "requested_permission": self.requested_permission.value_name,
            "configured_max_permission": self.configured_max_permission.value_name,
            "api_key_capability": self.api_key_capability.value_name,
            "account_facts_permission": self.account_facts_permission.value_name,
            "risk_capital_permission": self.risk_capital_permission.value_name,
            "runtime_safety_permission": self.runtime_safety_permission.value_name,
            "operation_permission": self.operation_permission.value_name,
            "final_permission": self.final_permission.value_name,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "downgrade_reason": self.downgrade_reason,
        }


class ExecutionPermissionResolver:
    """Resolve final BRC action permission as the minimum contributor level."""

    def __init__(
        self,
        *,
        configured_max_permission: Optional[ExecutionPermission] = None,
        env: Optional[dict[str, str]] = None,
    ) -> None:
        self._env = env if env is not None else os.environ
        self._configured_max_permission = configured_max_permission

    def configured_max_permission(self) -> ExecutionPermission:
        if self._configured_max_permission is not None:
            return self._configured_max_permission
        return parse_execution_permission_max(
            self._env.get("BRC_EXECUTION_PERMISSION_MAX"),
            default=ExecutionPermission.READ_ONLY,
        )

    def resolve(
        self,
        *,
        requested_permission: ExecutionPermission,
        operation_type: str,
        operation_permission: ExecutionPermission,
        api_key_capability: Optional[ExecutionPermission] = None,
        account_facts: Optional[dict[str, Any]] = None,
        constraints_check: Optional[dict[str, Any]] = None,
        campaign_metadata: Optional[dict[str, Any]] = None,
        runtime_summary: Optional[dict[str, Any]] = None,
        trading_env: Optional[str] = None,
    ) -> ExecutionPermissionResolution:
        configured = self.configured_max_permission()
        blockers: list[str] = []
        warnings: list[str] = []

        api_permission = self._api_key_permission(
            requested_permission=requested_permission,
            explicit=api_key_capability,
            blockers=blockers,
            warnings=warnings,
        )
        account_permission = self._account_facts_permission(
            account_facts=account_facts,
            trading_env=trading_env or self._env.get("TRADING_ENV", "simulation"),
            requested_permission=requested_permission,
            blockers=blockers,
            warnings=warnings,
        )
        risk_permission = self._risk_capital_permission(
            constraints_check=constraints_check,
            blockers=blockers,
            warnings=warnings,
        )
        runtime_permission = self._runtime_safety_permission(
            campaign_metadata=campaign_metadata,
            runtime_summary=runtime_summary,
            blockers=blockers,
        )

        contributors = [
            configured,
            api_permission,
            account_permission,
            risk_permission,
            runtime_permission,
            operation_permission,
        ]
        final_permission = min(contributors)
        if final_permission < requested_permission:
            blockers.append(
                f"final execution permission {final_permission.value_name} is below requested {requested_permission.value_name}"
            )
        downgrade_reason = None
        if final_permission < requested_permission:
            downgrade_reason = "; ".join(dict.fromkeys(blockers)) or "permission downgraded by contributor"
        elif final_permission < configured:
            downgrade_reason = f"final permission downgraded to {final_permission.value_name}"

        return ExecutionPermissionResolution(
            requested_permission=requested_permission,
            configured_max_permission=configured,
            api_key_capability=api_permission,
            account_facts_permission=account_permission,
            risk_capital_permission=risk_permission,
            runtime_safety_permission=runtime_permission,
            operation_permission=operation_permission,
            final_permission=final_permission,
            blockers=list(dict.fromkeys(blockers)),
            warnings=list(dict.fromkeys(warnings)),
            downgrade_reason=downgrade_reason,
        )

    @staticmethod
    def _api_key_permission(
        *,
        requested_permission: ExecutionPermission,
        explicit: Optional[ExecutionPermission],
        blockers: list[str],
        warnings: list[str],
    ) -> ExecutionPermission:
        if explicit is not None:
            return explicit
        warnings.append(
            "api key read-only vs trade-enabled capability is not reliably classified; capping at intent_recording"
        )
        if requested_permission >= ExecutionPermission.EXECUTION_INTENT_ALLOWED:
            blockers.append("unknown API key capability cannot allow execution intents or orders")
        return ExecutionPermission.INTENT_RECORDING

    @staticmethod
    def _account_facts_permission(
        *,
        account_facts: Optional[dict[str, Any]],
        trading_env: str,
        requested_permission: ExecutionPermission,
        blockers: list[str],
        warnings: list[str],
    ) -> ExecutionPermission:
        facts = dict(account_facts or {})
        if not facts:
            blockers.append("account facts unavailable")
            return ExecutionPermission.SIGNAL_ONLY
        freshness = str(
            facts.get("freshness")
            or facts.get("freshness_status")
            or facts.get("staleness_status")
            or ""
        ).lower()
        if freshness in {"stale", "expired", "too_old"} or facts.get("stale") is True:
            blockers.append("account facts freshness unacceptable")
            return ExecutionPermission.SIGNAL_ONLY
        source = str(facts.get("source") or "").lower()
        truth_level = str(facts.get("truth_level") or "").lower()
        if source == "unavailable" or truth_level == "unavailable":
            blockers.append("account facts unavailable")
            return ExecutionPermission.SIGNAL_ONLY
        reconciliation = facts.get("reconciliation_status")
        reconciliation_status = (
            str(reconciliation.get("status") or "").lower()
            if isinstance(reconciliation, dict)
            else str(facts.get("reconciliation_status_value") or "").lower()
        )
        if reconciliation_status == "mismatch":
            blockers.append("account reconciliation mismatch")
            return ExecutionPermission.SIGNAL_ONLY
        unknown_counts = facts.get("unknown_unmanaged_counts")
        if isinstance(unknown_counts, dict) and (
            int(unknown_counts.get("orders") or 0) > 0
            or int(unknown_counts.get("positions") or 0) > 0
        ):
            blockers.append("unknown unmanaged exposure detected")
            return ExecutionPermission.SIGNAL_ONLY
        if trading_env.strip().lower() == "live" and source not in {"exchange_live", "mixed"}:
            warnings.append(
                "TRADING_ENV=live without exchange_live account facts; current facts cap live read-only detection at intent_recording only"
            )
        if requested_permission >= ExecutionPermission.INTENT_RECORDING:
            return ExecutionPermission.INTENT_RECORDING
        return ExecutionPermission.SIGNAL_ONLY

    @staticmethod
    def _risk_capital_permission(
        *,
        constraints_check: Optional[dict[str, Any]],
        blockers: list[str],
        warnings: list[str],
    ) -> ExecutionPermission:
        check = dict(constraints_check or {})
        if check and check.get("complete") is False:
            missing = ", ".join(str(item) for item in check.get("missing") or [])
            blockers.append(f"risk/capital constraints incomplete{(': ' + missing) if missing else ''}")
            return ExecutionPermission.SIGNAL_ONLY
        if check and check.get("constraints_snapshot_exists") is False:
            blockers.append("constraints snapshot unavailable")
            return ExecutionPermission.SIGNAL_ONLY
        if not check:
            warnings.append("risk/capital constraints check unavailable; capping at intent_recording")
        return ExecutionPermission.INTENT_RECORDING

    @staticmethod
    def _runtime_safety_permission(
        *,
        campaign_metadata: Optional[dict[str, Any]],
        runtime_summary: Optional[dict[str, Any]],
        blockers: list[str],
    ) -> ExecutionPermission:
        metadata = dict(campaign_metadata or {})
        runtime = dict(runtime_summary or {})
        if metadata.get("execution_intent_created") is True or metadata.get("order_created") is True:
            blockers.append("campaign already has execution/order state")
            return ExecutionPermission.SIGNAL_ONLY
        if metadata.get("orders_placed") is True or metadata.get("auto_execution_enabled") is True:
            blockers.append("campaign already has order-capable runtime state")
            return ExecutionPermission.SIGNAL_ONLY
        state = str(
            runtime.get("current_runtime_state")
            or runtime.get("runtime_state")
            or metadata.get("runtime_state")
            or ""
        ).lower()
        if state in {"hard_locked", "hard_lock", "emergency_stopped", "emergency_stop", "flatten_required"}:
            blockers.append("runtime safety state blocks intent recording")
            return ExecutionPermission.SIGNAL_ONLY
        if runtime.get("live_ready") is True or metadata.get("live_ready") is True:
            blockers.append("live execution path is already marked ready")
            return ExecutionPermission.SIGNAL_ONLY
        return ExecutionPermission.INTENT_RECORDING
