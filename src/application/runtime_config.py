"""
Runtime config resolver for Sim/Live execution.

This module defines the frozen runtime configuration contract used before
entering Sim-1. It deliberately does not replace ConfigManager yet; the first
step is to make runtime configuration resolvable, hashable, and auditable.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from src.domain.logic_tree import FilterConfig, FilterLeaf, LogicNode, TriggerConfig, TriggerLeaf
from src.domain.models import CapitalProtectionConfig, Direction, OrderStrategy, RiskConfig, StrategyDefinition
from src.domain.validators import coerce_decimal_fields, coerce_decimal_list_fields, stable_config_hash, validate_tp_contract


class EnvironmentRuntimeConfig(BaseModel):
    """Process-level runtime configuration sourced from environment variables."""

    model_config = ConfigDict(frozen=True)

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

    model_config = ConfigDict(frozen=True)

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

    model_config = ConfigDict(frozen=True)

    allowed_directions: tuple[Direction, ...]
    trigger: TriggerConfig
    filters: tuple[FilterConfig, ...]
    atr_enabled: bool = False

    @model_validator(mode="after")
    def validate_sim1_strategy(self) -> "StrategyRuntimeConfig":
        if self.allowed_directions != (Direction.LONG,):
            raise ValueError("Sim-1 strategy must be LONG-only")
        if self.atr_enabled:
            raise ValueError("Sim-1 strategy requires ATR disabled")
        return self

    def to_strategy_definition(
        self,
        *,
        strategy_id: str = "sim1_eth_runtime_strategy",
        name: str = "sim1_eth_runtime_strategy",
        primary_symbol: Optional[str] = None,
        primary_timeframe: Optional[str] = None,
    ) -> StrategyDefinition:
        """Build the dynamic strategy definition consumed by SignalPipeline."""
        apply_to = []
        is_global = True
        if primary_symbol and primary_timeframe:
            apply_to = [f"{primary_symbol}:{primary_timeframe}"]
            is_global = False

        children = [TriggerLeaf(type="trigger", id=self.trigger.id or "runtime_trigger", config=self.trigger)]
        children.extend(
            FilterLeaf(type="filter", id=filter_config.id or f"runtime_filter_{idx}", config=filter_config)
            for idx, filter_config in enumerate(self.filters)
        )
        logic_tree = children[0] if len(children) == 1 else LogicNode(gate="AND", children=children)

        return StrategyDefinition(
            id=strategy_id,
            name=name,
            logic_tree=logic_tree,
            trigger=self.trigger,
            filters=self.filters,
            is_global=is_global,
            apply_to=apply_to,
        )

    def get_mtf_ema_period(self, default: int = 60) -> int:
        """Return the runtime MTF EMA period, falling back to the legacy default."""
        for filter_config in self.filters:
            if filter_config.type == "mtf" and filter_config.enabled:
                value = filter_config.params.get("ema_period", default)
                return int(value)
        return default


class RiskRuntimeConfig(BaseModel):
    """Risk contract for runtime execution."""

    model_config = ConfigDict(frozen=True)

    max_loss_percent: Decimal
    max_leverage: int = Field(ge=1, le=125)
    max_total_exposure: Decimal
    daily_max_trades: Optional[int] = Field(default=None, ge=1)
    daily_max_loss_percent: Decimal

    @model_validator(mode="before")
    @classmethod
    def convert_decimal_inputs(cls, data: Any) -> Any:
        return coerce_decimal_fields(data, ("max_loss_percent", "max_total_exposure", "daily_max_loss_percent"))

    def to_risk_config(self, daily_max_loss_amount: Optional[Decimal] = None) -> RiskConfig:
        return RiskConfig(
            max_loss_percent=self.max_loss_percent,
            max_leverage=self.max_leverage,
            max_total_exposure=self.max_total_exposure,
            daily_max_trades=self.daily_max_trades,
            daily_max_loss=daily_max_loss_amount,
        )

    def to_capital_protection_config(
        self,
        *,
        account_equity: Optional[Decimal] = None,
        base: Optional[CapitalProtectionConfig] = None,
    ) -> CapitalProtectionConfig:
        """Derive account-level protection from the resolved runtime risk module.

        Sim-1 uses `daily_max_loss_percent` as the business profile value. If a
        startup equity snapshot is available, freeze it into an amount so daily
        loss checks do not drift with balance changes during the session. When
        no snapshot exists yet, keep the existing percentage fallback.
        """
        protection = base or CapitalProtectionConfig()

        single_trade = dict(protection.single_trade)
        single_trade["max_loss_percent"] = self.max_loss_percent * Decimal("100")

        daily = dict(protection.daily)
        daily["max_loss_percent"] = self.daily_max_loss_percent * Decimal("100")
        daily["max_loss_amount"] = (
            account_equity * self.daily_max_loss_percent
            if account_equity is not None
            else None
        )
        if self.daily_max_trades is not None:
            daily["max_trade_count"] = self.daily_max_trades

        account = dict(protection.account)
        account["max_leverage"] = self.max_leverage

        return CapitalProtectionConfig(
            enabled=protection.enabled,
            min_notional=protection.min_notional,
            price_deviation_threshold=protection.price_deviation_threshold,
            extreme_price_deviation_threshold=protection.extreme_price_deviation_threshold,
            single_trade=single_trade,
            daily=daily,
            account=account,
        )


class ExecutionRuntimeConfig(BaseModel):
    """Execution contract used to build the OrderStrategy snapshot."""

    model_config = ConfigDict(frozen=True)

    tp_levels: int = Field(ge=1, le=5)
    tp_ratios: tuple[Decimal, ...]
    tp_targets: tuple[Decimal, ...]
    initial_stop_loss_rr: Decimal = Decimal("-1.0")
    breakeven_enabled: bool = False
    trailing_stop_enabled: bool = False
    oco_enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def convert_decimal_inputs(cls, data: Any) -> Any:
        converted = coerce_decimal_list_fields(data, ("tp_ratios", "tp_targets"))
        return coerce_decimal_fields(converted, ("initial_stop_loss_rr",))

    @model_validator(mode="after")
    def validate_execution_contract(self) -> "ExecutionRuntimeConfig":
        validate_tp_contract(
            tp_levels=self.tp_levels,
            tp_ratios=self.tp_ratios,
            tp_targets=self.tp_targets,
        )
        return self

    def to_order_strategy(self, strategy_id: str = "sim1_eth_runtime") -> OrderStrategy:
        return OrderStrategy(
            id=strategy_id,
            name=strategy_id,
            tp_levels=self.tp_levels,
            tp_ratios=list(self.tp_ratios),
            tp_targets=list(self.tp_targets),
            initial_stop_loss_rr=self.initial_stop_loss_rr,
            trailing_stop_enabled=self.trailing_stop_enabled,
            oco_enabled=self.oco_enabled,
        )


class ResolvedRuntimeConfig(BaseModel):
    """Frozen, fully-resolved runtime config consumed by Sim/Live runtime."""

    model_config = ConfigDict(frozen=True)

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


class RuntimeConfigProvider:
    """Process-local holder for the resolved runtime config.

    The provider is intentionally tiny: it gives startup code a stable place to
    store and expose the resolved profile before execution modules start
    consuming it directly.
    """

    def __init__(self, resolved_config: ResolvedRuntimeConfig) -> None:
        self._resolved_config = resolved_config

    @property
    def resolved_config(self) -> ResolvedRuntimeConfig:
        return self._resolved_config

    @property
    def config_hash(self) -> str:
        return self._resolved_config.config_hash

    def to_safe_summary(self) -> dict[str, Any]:
        return self._resolved_config.to_safe_summary()


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
        return stable_config_hash(
            {
                "profile_name": profile_name,
                "version": version,
                # Only execution-affecting environment semantics belong in the business hash.
                # Infra details such as DB DSN, backend port, and repository backend switches
                # stay out so operational changes do not fork the strategy/risk baseline.
                "environment": {
                    "exchange_name": environment.exchange_name,
                    "exchange_testnet": environment.exchange_testnet,
                },
                "profile": profile_payload,
            }
        )
