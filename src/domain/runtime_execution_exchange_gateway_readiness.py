"""Runtime exchange gateway readiness evidence.

This records whether the deployment environment is ready for a future manual
runtime exchange-gateway binding. It is evidence only: it does not initialize a
gateway, call exchange, inject a gateway into the runtime adapter, create
orders, or authorize live trading.
"""

from __future__ import annotations

from enum import Enum
from hashlib import sha256
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


GATEWAY_BINDING_ENABLED_ENV = "RUNTIME_EXCHANGE_SUBMIT_GATEWAY_BINDING_ENABLED"
DEFAULT_RUNTIME_EXCHANGE_GATEWAY_READINESS_MAX_AGE_MS = 15 * 60 * 1000


class RuntimeExecutionExchangeGatewayReadinessModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimeExecutionExchangeGatewayReadinessStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_MANUAL_GATEWAY_BINDING = "ready_for_manual_gateway_binding"


class RuntimeExecutionExchangeGatewayReadiness(
    RuntimeExecutionExchangeGatewayReadinessModel
):
    readiness_id: str = Field(min_length=1, max_length=128)
    status: RuntimeExecutionExchangeGatewayReadinessStatus
    exchange_name: str = Field(min_length=1, max_length=64)
    trading_env: str = Field(min_length=1, max_length=64)
    exchange_testnet: str = Field(min_length=1, max_length=16)
    execution_permission_max: str = Field(min_length=1, max_length=64)
    runtime_control_api_enabled: str = Field(min_length=1, max_length=16)
    runtime_test_signal_injection_enabled: str = Field(min_length=1, max_length=16)
    runtime_exchange_submit_gateway_binding_enabled: bool
    exchange_credentials_present: bool
    owner_confirmed_gateway_readiness_review: bool
    owner_operator_id: str = Field(min_length=1, max_length=128)
    owner_confirmation_reference: str | None = Field(
        default=None,
        max_length=240,
    )
    reason: str = Field(min_length=1, max_length=500)
    required_gateway_methods: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    not_live_action_authorization: Literal[True] = True
    gateway_injected: Literal[False] = False
    exchange_called: Literal[False] = False
    exchange_order_submitted: Literal[False] = False
    order_lifecycle_submit_called: Literal[False] = False
    execution_intent_status_changed: Literal[False] = False
    owner_bounded_execution_called: Literal[False] = False
    withdrawal_or_transfer_created: Literal[False] = False
    created_at_ms: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_readiness(
        self,
    ) -> "RuntimeExecutionExchangeGatewayReadiness":
        _reject_forbidden_execution_fields(
            "runtime exchange gateway readiness",
            {"metadata": self.metadata},
        )
        if (
            self.status
            == RuntimeExecutionExchangeGatewayReadinessStatus
            .READY_FOR_MANUAL_GATEWAY_BINDING
        ):
            if self.blockers:
                raise ValueError("ready gateway readiness cannot have blockers")
            if not self.owner_confirmed_gateway_readiness_review:
                raise ValueError("ready gateway readiness requires Owner review")
            if not self.runtime_exchange_submit_gateway_binding_enabled:
                raise ValueError("ready gateway readiness requires binding flag")
            if not self.exchange_credentials_present:
                raise ValueError("ready gateway readiness requires credentials")
        if (
            self.gateway_injected
            or self.exchange_called
            or self.exchange_order_submitted
            or self.order_lifecycle_submit_called
            or self.execution_intent_status_changed
            or self.owner_bounded_execution_called
            or self.withdrawal_or_transfer_created
        ):
            raise ValueError(
                "runtime exchange gateway readiness cannot perform execution"
            )
        return self


def build_runtime_execution_exchange_gateway_readiness(
    *,
    env: Mapping[str, str | None],
    owner_confirmed_gateway_readiness_review: bool,
    owner_operator_id: str,
    reason: str,
    now_ms: int,
    owner_confirmation_reference: str | None = None,
) -> RuntimeExecutionExchangeGatewayReadiness:
    exchange_name = _env(env, "EXCHANGE_NAME", "binance")
    trading_env = _env(env, "TRADING_ENV")
    exchange_testnet = _env(env, "EXCHANGE_TESTNET")
    permission_max = _env(env, "BRC_EXECUTION_PERMISSION_MAX")
    runtime_control = _env(env, "RUNTIME_CONTROL_API_ENABLED")
    signal_injection = _env(env, "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED")
    binding_enabled = _as_bool(_env(env, GATEWAY_BINDING_ENABLED_ENV))
    credentials_present = bool(
        _env(env, "EXCHANGE_API_KEY") and _env(env, "EXCHANGE_API_SECRET")
    )
    blockers: list[str] = []
    warnings: list[str] = []

    if trading_env != "live":
        blockers.append("trading_env_not_live")
    if exchange_testnet != "false":
        blockers.append("exchange_testnet_not_false")
    if permission_max != "order_allowed":
        blockers.append("brc_execution_permission_max_not_order_allowed")
    if runtime_control != "false":
        blockers.append("runtime_control_api_enabled_not_false")
    if signal_injection != "false":
        blockers.append("runtime_test_signal_injection_enabled_not_false")
    if exchange_name != "binance":
        blockers.append(f"unsupported_exchange:{exchange_name or 'missing'}")
    if not credentials_present:
        blockers.append("exchange_credentials_missing")
    if not binding_enabled:
        blockers.append("runtime_exchange_submit_gateway_binding_not_enabled")
    if not owner_confirmed_gateway_readiness_review:
        blockers.append("owner_gateway_readiness_review_missing")
    if not _present(owner_operator_id):
        blockers.append("owner_operator_id_missing")
    if not _present(reason):
        blockers.append("runtime_gateway_readiness_reason_missing")

    warnings.append("gateway_not_injected_by_readiness_evidence")
    warnings.append("not_live_action_authorization")
    status = (
        RuntimeExecutionExchangeGatewayReadinessStatus.BLOCKED
        if blockers
        else RuntimeExecutionExchangeGatewayReadinessStatus
        .READY_FOR_MANUAL_GATEWAY_BINDING
    )
    fingerprint = sha256(
        f"{now_ms}:{owner_operator_id}:{reason}".encode("utf-8")
    ).hexdigest()[:24]
    return RuntimeExecutionExchangeGatewayReadiness(
        readiness_id=f"runtime-exchange-gateway-readiness-{fingerprint}",
        status=status,
        exchange_name=exchange_name or "missing",
        trading_env=trading_env or "missing",
        exchange_testnet=exchange_testnet or "missing",
        execution_permission_max=permission_max or "missing",
        runtime_control_api_enabled=runtime_control or "missing",
        runtime_test_signal_injection_enabled=signal_injection or "missing",
        runtime_exchange_submit_gateway_binding_enabled=binding_enabled,
        exchange_credentials_present=credentials_present,
        owner_confirmed_gateway_readiness_review=(
            owner_confirmed_gateway_readiness_review
        ),
        owner_operator_id=str(owner_operator_id or "").strip() or "unknown",
        owner_confirmation_reference=_optional_str(owner_confirmation_reference),
        reason=str(reason or "").strip() or "missing_reason",
        required_gateway_methods=["place_order", "fetch_ticker_price", "get_market_info"],
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        created_at_ms=now_ms,
        metadata={
            "scope": "runtime_execution_exchange_gateway_readiness",
            "safe_env_values": {
                "TRADING_ENV": trading_env or "missing",
                "EXCHANGE_TESTNET": exchange_testnet or "missing",
                "BRC_EXECUTION_PERMISSION_MAX": permission_max or "missing",
                "RUNTIME_CONTROL_API_ENABLED": runtime_control or "missing",
                "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": (
                    signal_injection or "missing"
                ),
                GATEWAY_BINDING_ENABLED_ENV: (
                    "true" if binding_enabled else "false"
                ),
                "EXCHANGE_NAME": exchange_name or "missing",
                "EXCHANGE_CREDENTIALS_PRESENT": credentials_present,
            },
            "does_not_initialize_exchange_gateway": True,
            "does_not_inject_gateway": True,
            "does_not_call_exchange": True,
            "does_not_submit_exchange_order": True,
            "does_not_call_order_lifecycle": True,
            "does_not_change_execution_intent_status": True,
            "does_not_authorize_live_action": True,
            "does_not_create_withdrawal_or_transfer": True,
        },
    )


def _env(env: Mapping[str, str | None], key: str, default: str = "") -> str:
    value = env.get(key, default)
    return str(value or "").strip().lower()


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _present(value: Any) -> bool:
    return bool(str(value or "").strip())


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(getattr(value, "value", value)).strip()
    return text or None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _reject_forbidden_execution_fields(scope: str, value: dict[str, Any]) -> None:
    forbidden = {
        "api_key",
        "api_secret",
        "secret",
        "credential",
        "client_order_id",
        "exchange_payload",
        "place_order",
        "submit_order",
        "withdrawal_payload",
        "transfer_payload",
    }
    for key in _walk_keys(value):
        if key.lower() in forbidden:
            raise ValueError(f"{scope} contains forbidden execution field: {key}")


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_walk_keys(item))
    return keys
