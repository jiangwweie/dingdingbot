"""
Runtime config resolver for Sim/Live execution.

This module defines the frozen runtime configuration contract used before
entering Sim-1. It deliberately does not replace ConfigManager yet; the first
step is to make runtime configuration resolvable, hashable, and auditable.
"""

from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal
from typing import Any, Mapping, Optional

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from src.domain.models import Direction, OrderStrategy, RiskConfig


class EnvironmentRuntimeConfig(BaseModel):
    """Process-level runtime configuration sourced from environment variables."""

    pg_database_url: SecretStr
    core_execution_intent_backend: str = Field(default="postgres")
    core_order_backend: str = Field(default="sqlite")
    core_position_backend: str = Field(default="sqlite")
    exchange_name: str = Field(default="binance")
    exchange_testnet: bool = Field(default=True)
    exchange_api_key: SecretStr
    exchange_api_secret: SecretStr
    feishu_webhook_url: SecretStr
    backend_port: int = Field(default=8000, ge=1, le=65535)

    @field_validator(
        "core_execution_intent_backend",
        "core_order_backend",
        "core_position_backend",
    )
    @classmethod
    def validate_backend(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"sqlite", "postgres"}:
            raise ValueError("backend must be sqlite or postgres")
        return normalized

    @model_validator(mode="after")
    def validate_sim1_backend_policy(self) -> "EnvironmentRuntimeConfig":
        if self.core_execution_intent_backend != "postgres":
            raise ValueError("Sim-1 requires CORE_EXECUTION_INTENT_BACKEND=postgres")
        return self


class MarketRuntimeConfig(BaseModel):
    """Market universe and subscription scope for the frozen runtime profile."""

    primary_symbol: str
    primary_timeframe: str
    mtf_timeframe: str
    warmup_history_bars: int = Field(default=100, ge=1)
    asset_polling_interval: int = Field(default=60, ge=1)

    @property
    def symbols(self) -> list[str]:
        return [self.primary_symbol]

    @property
    def timeframes(self) -> list[str]:
        return sorted({self.primary_timeframe, self.mtf_timeframe})

    @property
    def subscribed_pairs(self) -> list[tuple[str, str]]:
        return [
            (self.primary_symbol, self.primary_timeframe),
            (self.primary_symbol, self.mtf_timeframe),
        ]


class StrategyRuntimeConfig(BaseModel):
    """Strategy trigger and filter contract for runtime execution."""

    allowed_directions: list[Direction]
    trigger: dict[str, Any]
    filters: list[dict[str, Any]]
    atr_enabled: bool = False

    @model_validator(mode="after")
    def validate_sim1_strategy(self) -> "StrategyRuntimeConfig":
        if self.allowed_directions != [Direction.LONG]:
            raise ValueError("Sim-1 strategy must be LONG-only")
        if self.atr_enabled:
            raise ValueError("Sim-1 strategy requires ATR disabled")
        return self


class RiskRuntimeConfig(BaseModel):
    """Risk contract for runtime execution."""

    max_loss_percent: Decimal
    max_leverage: int = Field(ge=1, le=125)
    max_total_exposure: Decimal
    daily_max_trades: Optional[int] = Field(default=None, ge=1)
    daily_max_loss_percent: Decimal

    @model_validator(mode="before")
    @classmethod
    def convert_decimal_inputs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            converted = dict(data)
            for key in ("max_loss_percent", "max_total_exposure", "daily_max_loss_percent"):
                if key in converted and converted[key] is not None and not isinstance(converted[key], Decimal):
                    converted[key] = Decimal(str(converted[key]))
            return converted
        return data

    def to_risk_config(self, daily_max_loss_amount: Optional[Decimal] = None) -> RiskConfig:
        return RiskConfig(
            max_loss_percent=self.max_loss_percent,
            max_leverage=self.max_leverage,
            max_total_exposure=self.max_total_exposure,
            daily_max_trades=self.daily_max_trades,
            daily_max_loss=daily_max_loss_amount,
        )


class ExecutionRuntimeConfig(BaseModel):
    """Execution contract used to build the OrderStrategy snapshot."""

    tp_levels: int = Field(ge=1, le=5)
    tp_ratios: list[Decimal]
    tp_targets: list[Decimal]
    initial_stop_loss_rr: Decimal = Decimal("-1.0")
    breakeven_enabled: bool = False
    trailing_stop_enabled: bool = False
    oco_enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def convert_decimal_inputs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            converted = dict(data)
            for key in ("tp_ratios", "tp_targets"):
                if key in converted and converted[key] is not None:
                    converted[key] = [
                        value if isinstance(value, Decimal) else Decimal(str(value))
                        for value in converted[key]
                    ]
            if "initial_stop_loss_rr" in converted and converted["initial_stop_loss_rr"] is not None:
                value = converted["initial_stop_loss_rr"]
                converted["initial_stop_loss_rr"] = value if isinstance(value, Decimal) else Decimal(str(value))
            return converted
        return data

    @model_validator(mode="after")
    def validate_execution_contract(self) -> "ExecutionRuntimeConfig":
        if len(self.tp_ratios) != self.tp_levels:
            raise ValueError("tp_ratios length must match tp_levels")
        if len(self.tp_targets) != self.tp_levels:
            raise ValueError("tp_targets length must match tp_levels")
        if abs(sum(self.tp_ratios, Decimal("0")) - Decimal("1.0")) > Decimal("0.0001"):
            raise ValueError("tp_ratios must sum to 1.0")
        return self

    def to_order_strategy(self, strategy_id: str = "sim1_eth_runtime") -> OrderStrategy:
        return OrderStrategy(
            id=strategy_id,
            name=strategy_id,
            tp_levels=self.tp_levels,
            tp_ratios=self.tp_ratios,
            tp_targets=self.tp_targets,
            initial_stop_loss_rr=self.initial_stop_loss_rr,
            trailing_stop_enabled=self.trailing_stop_enabled,
            oco_enabled=self.oco_enabled,
        )


class ResolvedRuntimeConfig(BaseModel):
    """Frozen, fully-resolved runtime config consumed by Sim/Live runtime."""

    profile_name: str
    version: int
    config_hash: str
    environment: EnvironmentRuntimeConfig
    market: MarketRuntimeConfig
    strategy: StrategyRuntimeConfig
    risk: RiskRuntimeConfig
    execution: ExecutionRuntimeConfig

    def to_safe_summary(self) -> dict[str, Any]:
        """Return a log-safe summary without secrets."""
        return {
            "profile_name": self.profile_name,
            "version": self.version,
            "config_hash": self.config_hash,
            "environment": {
                "core_execution_intent_backend": self.environment.core_execution_intent_backend,
                "core_order_backend": self.environment.core_order_backend,
                "core_position_backend": self.environment.core_position_backend,
                "exchange_name": self.environment.exchange_name,
                "exchange_testnet": self.environment.exchange_testnet,
                "backend_port": self.environment.backend_port,
            },
            "market": self.market.model_dump(mode="json"),
            "strategy": self.strategy.model_dump(mode="json"),
            "risk": self.risk.model_dump(mode="json"),
            "execution": self.execution.model_dump(mode="json"),
        }


class RuntimeConfigResolver:
    """Resolve environment + SQLite runtime profile into ResolvedRuntimeConfig."""

    def __init__(
        self,
        profile_repository: Any,
        env: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._profile_repository = profile_repository
        self._env = env or os.environ

    async def resolve(self, profile_name: str = "sim1_eth_runtime") -> ResolvedRuntimeConfig:
        profile = await self._profile_repository.get_profile(profile_name)
        if profile is None:
            raise ValueError(f"runtime profile not found: {profile_name}")

        environment = self._resolve_environment()
        payload = profile.profile_payload
        version = profile.version
        config_hash = self._build_config_hash(environment, payload, profile_name, version)

        return ResolvedRuntimeConfig(
            profile_name=profile_name,
            version=version,
            config_hash=config_hash,
            environment=environment,
            market=MarketRuntimeConfig.model_validate(payload["market"]),
            strategy=StrategyRuntimeConfig.model_validate(payload["strategy"]),
            risk=RiskRuntimeConfig.model_validate(payload["risk"]),
            execution=ExecutionRuntimeConfig.model_validate(payload["execution"]),
        )

    def _resolve_environment(self) -> EnvironmentRuntimeConfig:
        return EnvironmentRuntimeConfig(
            pg_database_url=self._required_env("PG_DATABASE_URL"),
            core_execution_intent_backend=self._env.get("CORE_EXECUTION_INTENT_BACKEND", "postgres"),
            core_order_backend=self._env.get("CORE_ORDER_BACKEND", "sqlite"),
            core_position_backend=self._env.get("CORE_POSITION_BACKEND", "sqlite"),
            exchange_name=self._env.get("EXCHANGE_NAME", "binance"),
            exchange_testnet=self._parse_bool(self._env.get("EXCHANGE_TESTNET", "true")),
            exchange_api_key=self._required_env("EXCHANGE_API_KEY"),
            exchange_api_secret=self._required_env("EXCHANGE_API_SECRET"),
            feishu_webhook_url=self._required_env("FEISHU_WEBHOOK_URL"),
            backend_port=int(self._env.get("BACKEND_PORT", "8000")),
        )

    def _required_env(self, name: str) -> str:
        value = self._env.get(name)
        if not value:
            raise ValueError(f"required environment variable missing: {name}")
        return value

    @staticmethod
    def _parse_bool(value: str) -> bool:
        return value.lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _build_config_hash(
        environment: EnvironmentRuntimeConfig,
        profile_payload: dict[str, Any],
        profile_name: str,
        version: int,
    ) -> str:
        hash_payload = {
            "profile_name": profile_name,
            "version": version,
            "environment": {
                "core_execution_intent_backend": environment.core_execution_intent_backend,
                "core_order_backend": environment.core_order_backend,
                "core_position_backend": environment.core_position_backend,
                "exchange_name": environment.exchange_name,
                "exchange_testnet": environment.exchange_testnet,
                "backend_port": environment.backend_port,
            },
            "profile": profile_payload,
        }
        raw = json.dumps(hash_payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

