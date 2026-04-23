"""
Backtest config profile resolver.

This module gives backtests their own configuration abstraction instead of
reading a Sim/Live runtime profile directly. The resolver keeps the existing
backtest precedence intact:

runtime_overrides > request > backtest profile > code defaults
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Literal, Mapping, Optional, Protocol

from pydantic import BaseModel, Field, model_validator

from src.application.backtester import resolve_backtest_params
from src.domain.logic_tree import FilterConfig, FilterLeaf, LogicNode, TriggerConfig, TriggerLeaf
from src.domain.models import (
    BacktestRequest,
    BacktestRuntimeOverrides,
    Direction,
    OrderStrategy,
    ResolvedBacktestParams,
    RiskConfig,
    StrategyDefinition,
)


BacktestInjectableSource = Literal["request", "runtime_overrides", "profile_kv"]
BacktestInjectableModule = Literal["market", "strategy", "risk", "execution", "engine", "diagnostic"]


class BacktestInjectableParam(BaseModel):
    """One explicit parameter that may be injected into a backtest run."""

    key: str
    module: BacktestInjectableModule
    value_type: str
    sources: list[BacktestInjectableSource]
    description: str
    optimizer_safe: bool = False


BACKTEST_INJECTABLE_PARAMS: tuple[BacktestInjectableParam, ...] = (
    BacktestInjectableParam(
        key="symbol",
        module="market",
        value_type="str",
        sources=["request"],
        description="Trading symbol for the backtest data scope.",
    ),
    BacktestInjectableParam(
        key="timeframe",
        module="market",
        value_type="str",
        sources=["request"],
        description="Primary timeframe for the backtest data scope.",
    ),
    BacktestInjectableParam(
        key="limit",
        module="market",
        value_type="int",
        sources=["request"],
        description="Maximum number of candles to fetch.",
    ),
    BacktestInjectableParam(
        key="strategy.atr.max_atr_ratio",
        module="strategy",
        value_type="Decimal",
        sources=["runtime_overrides", "profile_kv"],
        description="ATR volatility ceiling.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="strategy.ema.min_distance_pct",
        module="strategy",
        value_type="Decimal",
        sources=["runtime_overrides", "profile_kv"],
        description="Minimum price distance from EMA.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="strategy.ema.period",
        module="strategy",
        value_type="int",
        sources=["runtime_overrides", "profile_kv"],
        description="Primary EMA period.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="system.mtf_ema_period",
        module="strategy",
        value_type="int",
        sources=["runtime_overrides", "profile_kv"],
        description="Higher-timeframe EMA period.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="system.mtf_mapping",
        module="strategy",
        value_type="dict[str, str]",
        sources=["runtime_overrides", "profile_kv"],
        description="Primary timeframe to higher-timeframe mapping.",
    ),
    BacktestInjectableParam(
        key="strategies",
        module="strategy",
        value_type="list[StrategyDefinition]",
        sources=["request"],
        description="Full dynamic strategy definition override.",
    ),
    BacktestInjectableParam(
        key="risk_overrides",
        module="risk",
        value_type="RiskConfig",
        sources=["request"],
        description="Per-run risk sizing override.",
    ),
    BacktestInjectableParam(
        key="risk.max_loss_percent",
        module="risk",
        value_type="Decimal",
        sources=["request"],
        description="Per-run max loss percent used by Optuna/study trials.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="risk.max_total_exposure",
        module="risk",
        value_type="Decimal",
        sources=["request"],
        description="Per-run max exposure cap used by Optuna/study trials.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="risk.max_leverage",
        module="risk",
        value_type="int",
        sources=["request"],
        description="Per-run leverage cap. Fixed-param only by default.",
    ),
    BacktestInjectableParam(
        key="execution.tp_ratios",
        module="execution",
        value_type="list[Decimal]",
        sources=["runtime_overrides", "profile_kv"],
        description="Take-profit quantity split.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="execution.tp_targets",
        module="execution",
        value_type="list[Decimal]",
        sources=["runtime_overrides", "profile_kv"],
        description="Take-profit target RR levels.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="order_strategy",
        module="execution",
        value_type="OrderStrategy",
        sources=["request"],
        description="Full order strategy override for a request.",
    ),
    BacktestInjectableParam(
        key="backtest.breakeven_enabled",
        module="execution",
        value_type="bool",
        sources=["runtime_overrides", "profile_kv"],
        description="Breakeven stop toggle.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="backtest.initial_balance",
        module="engine",
        value_type="Decimal",
        sources=["request", "profile_kv"],
        description="Initial balance for the backtest account.",
    ),
    BacktestInjectableParam(
        key="backtest.slippage_rate",
        module="engine",
        value_type="Decimal",
        sources=["request", "profile_kv"],
        description="Entry/stop slippage rate.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="backtest.tp_slippage_rate",
        module="engine",
        value_type="Decimal",
        sources=["request", "profile_kv"],
        description="Take-profit slippage rate.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="backtest.fee_rate",
        module="engine",
        value_type="Decimal",
        sources=["request", "profile_kv"],
        description="Trading fee rate.",
    ),
    BacktestInjectableParam(
        key="backtest.same_bar_policy",
        module="engine",
        value_type="str",
        sources=["runtime_overrides", "profile_kv"],
        description="Same-bar TP/SL conflict policy.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="backtest.same_bar_tp_first_prob",
        module="engine",
        value_type="Decimal",
        sources=["runtime_overrides", "profile_kv"],
        description="TP-first probability when same_bar_policy=random.",
        optimizer_safe=True,
    ),
    BacktestInjectableParam(
        key="backtest.random_seed",
        module="engine",
        value_type="int",
        sources=["runtime_overrides", "profile_kv"],
        description="Deterministic seed for random same-bar matching.",
    ),
    BacktestInjectableParam(
        key="backtest.allowed_directions",
        module="diagnostic",
        value_type="list[str]",
        sources=["runtime_overrides", "profile_kv"],
        description="Diagnostic direction allow-list.",
        optimizer_safe=True,
    ),
)


def list_backtest_injectable_params(
    *,
    module: Optional[BacktestInjectableModule] = None,
    optimizer_safe: Optional[bool] = None,
) -> list[BacktestInjectableParam]:
    """Return the explicit injectable parameter contract for API/UI/Optuna."""
    params = list(BACKTEST_INJECTABLE_PARAMS)
    if module is not None:
        params = [param for param in params if param.module == module]
    if optimizer_safe is not None:
        params = [param for param in params if param.optimizer_safe is optimizer_safe]
    return [param.model_copy(deep=True) for param in params]


class BacktestMarketProfile(BaseModel):
    """Backtest market/data scope."""

    symbol: str
    timeframe: str
    mtf_timeframe: Optional[str] = None
    limit: int = Field(default=100, ge=10, le=30000)


class BacktestStrategyProfile(BaseModel):
    """Backtest strategy contract."""

    allowed_directions: Optional[list[Direction]] = None
    trigger: TriggerConfig
    filters: list[FilterConfig] = Field(default_factory=list)

    def to_strategy_definition(
        self,
        *,
        strategy_id: str,
        name: str,
        market: BacktestMarketProfile,
    ) -> StrategyDefinition:
        apply_to = [f"{market.symbol}:{market.timeframe}"]
        children = [TriggerLeaf(type="trigger", id=self.trigger.id or "backtest_trigger", config=self.trigger)]
        children.extend(
            FilterLeaf(type="filter", id=filter_config.id or f"backtest_filter_{idx}", config=filter_config)
            for idx, filter_config in enumerate(self.filters)
        )
        logic_tree = children[0] if len(children) == 1 else LogicNode(gate="AND", children=children)

        return StrategyDefinition(
            id=strategy_id,
            name=name,
            logic_tree=logic_tree,
            trigger=self.trigger,
            filters=self.filters,
            is_global=False,
            apply_to=apply_to,
        )

    def to_kv_defaults(self, market: BacktestMarketProfile) -> dict[str, object]:
        kv_defaults: dict[str, object] = {}
        if self.allowed_directions is not None:
            kv_defaults["backtest.allowed_directions"] = [direction.value for direction in self.allowed_directions]

        if market.mtf_timeframe:
            kv_defaults["system.mtf_mapping"] = {market.timeframe: market.mtf_timeframe}

        for filter_config in self.filters:
            params = filter_config.params
            if not filter_config.enabled:
                continue
            if filter_config.type in {"ema", "ema_trend"}:
                if "period" in params:
                    kv_defaults["strategy.ema.period"] = params["period"]
                if "min_distance_pct" in params:
                    kv_defaults["strategy.ema.min_distance_pct"] = params["min_distance_pct"]
            elif filter_config.type == "mtf":
                if "ema_period" in params:
                    kv_defaults["system.mtf_ema_period"] = params["ema_period"]
                if "source_timeframe" in params:
                    kv_defaults["system.mtf_mapping"] = {market.timeframe: str(params["source_timeframe"])}
            elif filter_config.type == "atr" and "max_atr_ratio" in params:
                kv_defaults["strategy.atr.max_atr_ratio"] = params["max_atr_ratio"]

        return kv_defaults


class BacktestRiskProfile(BaseModel):
    """Backtest risk sizing baseline."""

    max_loss_percent: Decimal
    max_leverage: int = Field(ge=1, le=125)
    max_total_exposure: Decimal = Field(default=Decimal("1.0"), ge=0, le=10)
    daily_max_trades: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="before")
    @classmethod
    def convert_decimal_inputs(cls, data: object) -> object:
        if isinstance(data, dict):
            converted = dict(data)
            for key in ("max_loss_percent", "max_total_exposure"):
                if key in converted and converted[key] is not None and not isinstance(converted[key], Decimal):
                    converted[key] = Decimal(str(converted[key]))
            return converted
        return data

    def to_risk_config(self) -> RiskConfig:
        return RiskConfig(
            max_loss_percent=self.max_loss_percent,
            max_leverage=self.max_leverage,
            max_total_exposure=self.max_total_exposure,
            daily_max_trades=self.daily_max_trades,
        )


class BacktestExecutionProfile(BaseModel):
    """Backtest order/execution baseline."""

    tp_levels: int = Field(ge=1, le=5)
    tp_ratios: list[Decimal]
    tp_targets: list[Decimal]
    initial_stop_loss_rr: Decimal = Decimal("-1.0")
    breakeven_enabled: bool = False
    trailing_stop_enabled: bool = False
    oco_enabled: bool = True

    @model_validator(mode="before")
    @classmethod
    def convert_decimal_inputs(cls, data: object) -> object:
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
    def validate_execution_profile(self) -> "BacktestExecutionProfile":
        if len(self.tp_ratios) != self.tp_levels:
            raise ValueError("tp_ratios length must match tp_levels")
        if len(self.tp_targets) != self.tp_levels:
            raise ValueError("tp_targets length must match tp_levels")
        if any(ratio <= Decimal("0") for ratio in self.tp_ratios):
            raise ValueError("tp_ratios must all be positive")
        if any(target <= Decimal("0") for target in self.tp_targets):
            raise ValueError("tp_targets must all be positive")
        if abs(sum(self.tp_ratios, Decimal("0")) - Decimal("1.0")) > Decimal("0.0001"):
            raise ValueError("tp_ratios must sum to 1.0")
        return self

    def to_kv_defaults(self) -> dict[str, object]:
        return {
            "execution.tp_ratios": self.tp_ratios,
            "execution.tp_targets": self.tp_targets,
            "backtest.breakeven_enabled": self.breakeven_enabled,
        }

    def to_order_strategy(
        self,
        *,
        strategy_id: str,
        resolved_params: ResolvedBacktestParams,
    ) -> OrderStrategy:
        return OrderStrategy(
            id=strategy_id,
            name=strategy_id,
            tp_levels=len(resolved_params.tp_ratios),
            tp_ratios=resolved_params.tp_ratios,
            tp_targets=resolved_params.tp_targets,
            initial_stop_loss_rr=self.initial_stop_loss_rr,
            trailing_stop_enabled=self.trailing_stop_enabled,
            oco_enabled=self.oco_enabled,
        )


class BacktestEngineProfile(BaseModel):
    """Backtest engine/cost baseline."""

    initial_balance: Decimal = Decimal("10000")
    slippage_rate: Decimal = Decimal("0.001")
    tp_slippage_rate: Decimal = Decimal("0.0005")
    fee_rate: Decimal = Decimal("0.0004")
    same_bar_policy: str = "pessimistic"
    same_bar_tp_first_prob: Decimal = Decimal("0.5")
    random_seed: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def convert_decimal_inputs(cls, data: object) -> object:
        if isinstance(data, dict):
            converted = dict(data)
            for key in ("initial_balance", "slippage_rate", "tp_slippage_rate", "fee_rate", "same_bar_tp_first_prob"):
                if key in converted and converted[key] is not None and not isinstance(converted[key], Decimal):
                    converted[key] = Decimal(str(converted[key]))
            return converted
        return data

    def to_kv_defaults(self) -> dict[str, object]:
        return {
            "backtest.initial_balance": self.initial_balance,
            "backtest.slippage_rate": self.slippage_rate,
            "backtest.tp_slippage_rate": self.tp_slippage_rate,
            "backtest.fee_rate": self.fee_rate,
            "backtest.same_bar_policy": self.same_bar_policy,
            "backtest.same_bar_tp_first_prob": self.same_bar_tp_first_prob,
            "backtest.random_seed": self.random_seed,
        }


class BacktestProfile(BaseModel):
    """Named backtest profile, independent from Sim/Live runtime profiles."""

    name: str
    version: int = Field(default=1, ge=1)
    description: str = ""
    market: BacktestMarketProfile
    strategy: BacktestStrategyProfile
    risk: BacktestRiskProfile
    execution: BacktestExecutionProfile
    engine: BacktestEngineProfile = Field(default_factory=BacktestEngineProfile)

    def to_kv_defaults(self) -> dict[str, object]:
        kv_defaults: dict[str, object] = {}
        kv_defaults.update(self.strategy.to_kv_defaults(self.market))
        kv_defaults.update(self.execution.to_kv_defaults())
        kv_defaults.update(self.engine.to_kv_defaults())
        return kv_defaults

    def config_hash(self) -> str:
        payload = self.model_dump(mode="json")
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class ResolvedBacktestConfig(BaseModel):
    """Fully resolved backtest config envelope."""

    profile_name: str
    profile_version: int
    config_hash: str
    symbol: str
    timeframe: str
    limit: int
    params: ResolvedBacktestParams
    strategy_definition: StrategyDefinition
    risk_config: RiskConfig
    order_strategy: OrderStrategy

    def to_backtest_request(self, request: Optional[BacktestRequest] = None) -> BacktestRequest:
        """Build a BacktestRequest with missing config filled from the profile."""
        request_data = request.model_dump() if request else {}
        request_data.update(
            {
                "symbol": request_data.get("symbol") or self.symbol,
                "timeframe": request_data.get("timeframe") or self.timeframe,
                "limit": request_data.get("limit") or self.limit,
                "strategies": request_data.get("strategies") or [self.strategy_definition.model_dump(mode="python")],
                "risk_overrides": request_data.get("risk_overrides") or self.risk_config,
                "order_strategy": request_data.get("order_strategy") or self.order_strategy,
                "initial_balance": request_data.get("initial_balance") or self.params.initial_balance,
                "slippage_rate": request_data.get("slippage_rate") or self.params.slippage_rate,
                "tp_slippage_rate": request_data.get("tp_slippage_rate") or self.params.tp_slippage_rate,
                "fee_rate": request_data.get("fee_rate") or self.params.fee_rate,
            }
        )
        return BacktestRequest(**request_data)


class BacktestProfileProvider(Protocol):
    """Read-only profile provider boundary for future SQLite/PG implementation."""

    async def get_backtest_profile(self, profile_name: str) -> Optional[BacktestProfile]:
        ...


class StaticBacktestProfileProvider:
    """In-memory provider used by scripts/tests and as the first baseline source."""

    def __init__(self, profiles: Mapping[str, BacktestProfile]) -> None:
        self._profiles = dict(profiles)

    async def get_backtest_profile(self, profile_name: str) -> Optional[BacktestProfile]:
        profile = self._profiles.get(profile_name)
        return profile.model_copy(deep=True) if profile else None


class BacktestConfigResolver:
    """Resolve a named backtest profile plus request/runtime overrides."""

    def __init__(self, profile_provider: BacktestProfileProvider) -> None:
        self._profile_provider = profile_provider

    def list_injectable_params(
        self,
        *,
        module: Optional[BacktestInjectableModule] = None,
        optimizer_safe: Optional[bool] = None,
    ) -> list[BacktestInjectableParam]:
        return list_backtest_injectable_params(module=module, optimizer_safe=optimizer_safe)

    async def resolve(
        self,
        profile_name: str = "backtest_eth_baseline",
        *,
        request: Optional[BacktestRequest] = None,
        runtime_overrides: Optional[BacktestRuntimeOverrides] = None,
    ) -> ResolvedBacktestConfig:
        profile = await self._profile_provider.get_backtest_profile(profile_name)
        if profile is None:
            raise ValueError(f"backtest profile not found: {profile_name}")

        params = resolve_backtest_params(
            runtime_overrides=runtime_overrides,
            request=request,
            kv_configs=profile.to_kv_defaults(),
        )
        symbol = request.symbol if request else profile.market.symbol
        timeframe = request.timeframe if request else profile.market.timeframe
        limit = request.limit if request else profile.market.limit

        strategy_definition = (
            StrategyDefinition.model_validate(request.strategies[0])
            if request and request.strategies
            else profile.strategy.to_strategy_definition(
                strategy_id=f"{profile.name}_strategy",
                name=f"{profile.name}_strategy",
                market=profile.market,
            )
        )
        risk_config = request.risk_overrides if request and request.risk_overrides else profile.risk.to_risk_config()

        has_runtime_tp_override = bool(
            runtime_overrides
            and (runtime_overrides.tp_ratios is not None or runtime_overrides.tp_targets is not None)
        )
        if request and request.order_strategy and not has_runtime_tp_override:
            order_strategy = request.order_strategy.model_copy(deep=True)
        else:
            order_strategy = profile.execution.to_order_strategy(
                strategy_id=f"{profile.name}_execution",
                resolved_params=params,
            )

        return ResolvedBacktestConfig(
            profile_name=profile.name,
            profile_version=profile.version,
            config_hash=profile.config_hash(),
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            params=params,
            strategy_definition=strategy_definition,
            risk_config=risk_config,
            order_strategy=order_strategy,
        )


BACKTEST_ETH_BASELINE_PROFILE = BacktestProfile(
    name="backtest_eth_baseline",
    version=1,
    description="ETH 1h backtest baseline aligned with Sim-1 business semantics, but independent from live runtime profile.",
    market=BacktestMarketProfile(
        symbol="ETH/USDT:USDT",
        timeframe="1h",
        mtf_timeframe="4h",
        limit=1000,
    ),
    strategy=BacktestStrategyProfile(
        allowed_directions=[Direction.LONG],
        trigger=TriggerConfig(
            id="backtest_eth_pinbar",
            type="pinbar",
            enabled=True,
            params={
                "min_wick_ratio": "0.6",
                "max_body_ratio": "0.3",
                "body_position_tolerance": "0.1",
            },
        ),
        filters=[
            FilterConfig(
                id="backtest_eth_ema",
                type="ema",
                enabled=True,
                params={"period": 50, "min_distance_pct": "0.005"},
            ),
            FilterConfig(
                id="backtest_eth_mtf",
                type="mtf",
                enabled=True,
                params={"source_timeframe": "4h", "ema_period": 60},
            ),
            FilterConfig(
                id="backtest_eth_atr",
                type="atr",
                enabled=False,
                params={},
            ),
        ],
    ),
    risk=BacktestRiskProfile(
        max_loss_percent=Decimal("0.01"),
        max_leverage=20,
        max_total_exposure=Decimal("1.0"),
        daily_max_trades=10,
    ),
    execution=BacktestExecutionProfile(
        tp_levels=2,
        tp_ratios=[Decimal("0.5"), Decimal("0.5")],
        tp_targets=[Decimal("1.0"), Decimal("3.5")],
        initial_stop_loss_rr=Decimal("-1.0"),
        breakeven_enabled=False,
        trailing_stop_enabled=False,
        oco_enabled=True,
    ),
)


DEFAULT_BACKTEST_PROFILE_PROVIDER = StaticBacktestProfileProvider(
    {BACKTEST_ETH_BASELINE_PROFILE.name: BACKTEST_ETH_BASELINE_PROFILE}
)
