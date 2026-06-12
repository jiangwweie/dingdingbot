"""Small-capital experimental runtime profile proposals.

These proposals translate Owner risk-capital intent into reviewable runtime
boundaries. They are not runtime records, authorizations, orders, or execution
permission.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_candidate_semantics import StrategyPayoffProfile
from src.domain.strategy_runtime import StrategyRuntimeBoundary
from src.domain.strategy_semantics import (
    StrategyCandidateMode,
    StrategyImplementationBinding,
    StrategyImplementationKind,
    StrategyRuntimeConfirmationMode,
    StrategySemanticsCatalog,
    initial_strategy_semantics_catalog,
)


class ExperimentalRuntimeProfileProposalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExperimentalRuntimeProfileProposalStatus(str, Enum):
    BLOCKED = "blocked"
    READY_FOR_OWNER_CODEX_CONFIRMATION = "ready_for_owner_codex_confirmation"


class ExperimentalRuntimeProfileKind(str, Enum):
    SMALL_CAPITAL_RIGHT_TAIL_LONG = "small_capital_right_tail_long"
    SMALL_CAPITAL_CONSERVATIVE_SHORT = "small_capital_conservative_short"
    SMALL_CAPITAL_MEAN_REVERSION = "small_capital_mean_reversion"


class ExperimentalRuntimeProfileProposal(ExperimentalRuntimeProfileProposalModel):
    proposal_id: str = Field(min_length=1, max_length=260)
    status: ExperimentalRuntimeProfileProposalStatus
    profile_kind: ExperimentalRuntimeProfileKind
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    canonical_family_id: str = Field(min_length=1, max_length=128)
    implementation_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    capital_base: Decimal = Field(gt=Decimal("0"))
    total_loss_budget: Decimal = Field(ge=Decimal("0"))
    max_loss_per_attempt: Decimal = Field(ge=Decimal("0"))
    max_notional_per_attempt: Decimal = Field(ge=Decimal("0"))
    max_attempts: int = Field(ge=1)
    max_active_positions: int = Field(ge=0)
    max_leverage: Decimal = Field(ge=Decimal("0"))
    max_margin_per_attempt: Decimal = Field(ge=Decimal("0"))
    min_liquidation_stop_buffer: Decimal = Field(ge=Decimal("0"))
    requires_protection: bool = True
    requires_review: bool = True
    runtime_confirmation_mode: StrategyRuntimeConfirmationMode
    payoff_profile: StrategyPayoffProfile
    reference_implementation: bool
    proven_alpha: bool
    boundary: StrategyRuntimeBoundary
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    owner_confirmation_keys: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    not_runtime_record: Literal[True] = True
    not_execution_authority: Literal[True] = True
    execution_enabled: Literal[False] = False
    shadow_mode: Literal[True] = True
    creates_runtime: Literal[False] = False
    creates_execution_intent: Literal[False] = False
    order_created: Literal[False] = False
    exchange_called: Literal[False] = False

    @model_validator(mode="after")
    def _status_consistency(self) -> "ExperimentalRuntimeProfileProposal":
        if (
            self.status
            == ExperimentalRuntimeProfileProposalStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
            and self.blockers
        ):
            raise ValueError("ready experimental runtime profile proposal cannot have blockers")
        if self.boundary.total_budget != self.total_loss_budget:
            raise ValueError("boundary total_budget must match total_loss_budget")
        if self.boundary.max_notional_per_attempt != self.max_notional_per_attempt:
            raise ValueError("boundary max_notional_per_attempt mismatch")
        return self


def build_experimental_runtime_profile_proposal(
    *,
    strategy_family_id: str,
    strategy_family_version_id: str,
    symbol: str,
    side: str,
    capital_base: Decimal = Decimal("30"),
    catalog: StrategySemanticsCatalog | None = None,
) -> ExperimentalRuntimeProfileProposal:
    catalog = catalog or initial_strategy_semantics_catalog()
    normalized_side = side.strip().lower() or "unknown"
    blockers: list[str] = []
    warnings: list[str] = []
    try:
        binding = catalog.get_binding(
            strategy_family_id=strategy_family_id,
            strategy_family_version_id=strategy_family_version_id,
        )
    except KeyError:
        binding = None
        blockers.append("strategy_semantics_binding_not_found")

    if capital_base <= Decimal("0"):
        blockers.append("capital_base_must_be_positive")
    effective_capital_base = (
        capital_base if capital_base > Decimal("0") else Decimal("0.00000001")
    )

    if binding is None:
        profile_kind = ExperimentalRuntimeProfileKind.SMALL_CAPITAL_RIGHT_TAIL_LONG
        boundary = _boundary(
            symbol=symbol,
            side=normalized_side,
            max_attempts=1,
            total_loss_budget=Decimal("0"),
            max_notional_per_attempt=Decimal("0"),
            max_leverage=Decimal("0"),
            max_margin_per_attempt=Decimal("0"),
        )
        return _proposal(
            binding=None,
            strategy_family_id=strategy_family_id,
            strategy_family_version_id=strategy_family_version_id,
            symbol=symbol,
            side=normalized_side,
            capital_base=effective_capital_base,
            profile_kind=profile_kind,
            total_loss_budget=Decimal("0"),
            max_loss_per_attempt=Decimal("0"),
            max_notional_per_attempt=Decimal("0"),
            max_attempts=1,
            max_leverage=Decimal("0"),
            max_margin_per_attempt=Decimal("0"),
            boundary=boundary,
            blockers=blockers,
            warnings=warnings,
        )

    _check_binding(binding=binding, side=normalized_side, blockers=blockers, warnings=warnings)
    sizing = _profile_sizing(
        binding=binding,
        side=normalized_side,
        capital_base=effective_capital_base,
    )
    boundary = _boundary(
        symbol=symbol,
        side=normalized_side,
        max_attempts=sizing["max_attempts"],
        total_loss_budget=sizing["total_loss_budget"],
        max_notional_per_attempt=sizing["max_notional_per_attempt"],
        max_leverage=sizing["max_leverage"],
        max_margin_per_attempt=sizing["max_margin_per_attempt"],
    )
    return _proposal(
        binding=binding,
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        symbol=symbol,
        side=normalized_side,
        capital_base=effective_capital_base,
        profile_kind=sizing["profile_kind"],
        total_loss_budget=sizing["total_loss_budget"],
        max_loss_per_attempt=sizing["max_loss_per_attempt"],
        max_notional_per_attempt=sizing["max_notional_per_attempt"],
        max_attempts=sizing["max_attempts"],
        max_leverage=sizing["max_leverage"],
        max_margin_per_attempt=sizing["max_margin_per_attempt"],
        boundary=boundary,
        blockers=blockers,
        warnings=warnings,
    )


def _check_binding(
    *,
    binding: StrategyImplementationBinding,
    side: str,
    blockers: list[str],
    warnings: list[str],
) -> None:
    if binding.candidate_mode != StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED:
        blockers.append("strategy_binding_not_trade_candidate")
    if binding.implementation_kind == StrategyImplementationKind.REGIME_CLASSIFIER:
        blockers.append("regime_classifier_not_runtime_trade_strategy")
    if binding.implementation_kind == StrategyImplementationKind.DATA_DEPENDENT_BACKLOG:
        blockers.append("data_backlog_not_runtime_trade_strategy")
    if side not in {item.lower() for item in binding.supported_sides}:
        blockers.append("strategy_side_not_supported")
    if binding.reference_implementation:
        warnings.append("reference_implementation_not_proven_production_strategy")
    if not binding.proven_alpha:
        warnings.append("strategy_not_proven_alpha_limits_budget_and_autonomy")
    if binding.metadata.get("short_side_conservative_profile_required"):
        warnings.append("short_side_conservative_profile_required")
    if binding.payoff_profile == StrategyPayoffProfile.MEAN_REVERSION:
        warnings.append("mean_reversion_profile_needs_tighter_attempt_review")


def _profile_sizing(
    *,
    binding: StrategyImplementationBinding,
    side: str,
    capital_base: Decimal,
) -> dict[str, Any]:
    max_attempts = 3
    max_leverage = Decimal("1")
    if side == "short" or binding.metadata.get("short_side_conservative_profile_required"):
        profile_kind = ExperimentalRuntimeProfileKind.SMALL_CAPITAL_CONSERVATIVE_SHORT
        total_loss_budget = min(capital_base * Decimal("0.20"), Decimal("6"))
        max_notional = min(capital_base * Decimal("0.2666666667"), Decimal("8"))
    elif binding.payoff_profile == StrategyPayoffProfile.MEAN_REVERSION:
        profile_kind = ExperimentalRuntimeProfileKind.SMALL_CAPITAL_MEAN_REVERSION
        total_loss_budget = min(capital_base * Decimal("0.20"), Decimal("6"))
        max_notional = min(capital_base * Decimal("0.2666666667"), Decimal("8"))
    else:
        profile_kind = ExperimentalRuntimeProfileKind.SMALL_CAPITAL_RIGHT_TAIL_LONG
        total_loss_budget = min(capital_base * Decimal("0.30"), Decimal("9"))
        max_notional = min(capital_base / Decimal("3"), Decimal("10"))
    total_loss_budget = _money(total_loss_budget)
    max_notional = _money(max_notional)
    return {
        "profile_kind": profile_kind,
        "total_loss_budget": total_loss_budget,
        "max_loss_per_attempt": _money(total_loss_budget / Decimal(max_attempts)),
        "max_notional_per_attempt": max_notional,
        "max_attempts": max_attempts,
        "max_leverage": max_leverage,
        "max_margin_per_attempt": max_notional / max_leverage,
    }


def _boundary(
    *,
    symbol: str,
    side: str,
    max_attempts: int,
    total_loss_budget: Decimal,
    max_notional_per_attempt: Decimal,
    max_leverage: Decimal,
    max_margin_per_attempt: Decimal,
) -> StrategyRuntimeBoundary:
    return StrategyRuntimeBoundary(
        max_attempts=max_attempts,
        attempts_used=0,
        budget_reserved=Decimal("0"),
        max_active_positions=1,
        max_notional_per_attempt=max_notional_per_attempt,
        total_budget=total_loss_budget,
        allowed_symbols=[symbol],
        allowed_sides=[side],
        max_leverage=max_leverage,
        max_margin_per_attempt=max_margin_per_attempt,
        min_liquidation_stop_buffer=Decimal("25"),
        requires_protection=True,
        requires_review=True,
    )


def _proposal(
    *,
    binding: StrategyImplementationBinding | None,
    strategy_family_id: str,
    strategy_family_version_id: str,
    symbol: str,
    side: str,
    capital_base: Decimal,
    profile_kind: ExperimentalRuntimeProfileKind,
    total_loss_budget: Decimal,
    max_loss_per_attempt: Decimal,
    max_notional_per_attempt: Decimal,
    max_attempts: int,
    max_leverage: Decimal,
    max_margin_per_attempt: Decimal,
    boundary: StrategyRuntimeBoundary,
    blockers: list[str],
    warnings: list[str],
) -> ExperimentalRuntimeProfileProposal:
    return ExperimentalRuntimeProfileProposal(
        proposal_id=(
            "experimental-runtime-profile:"
            f"{strategy_family_id}:{strategy_family_version_id}:{symbol}:{side}"
        ),
        status=(
            ExperimentalRuntimeProfileProposalStatus.BLOCKED
            if blockers
            else ExperimentalRuntimeProfileProposalStatus.READY_FOR_OWNER_CODEX_CONFIRMATION
        ),
        profile_kind=profile_kind,
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        canonical_family_id=binding.canonical_family_id if binding else strategy_family_id,
        implementation_id=binding.implementation_id if binding else "unresolved",
        symbol=symbol,
        side=side,
        capital_base=capital_base,
        total_loss_budget=total_loss_budget,
        max_loss_per_attempt=max_loss_per_attempt,
        max_notional_per_attempt=max_notional_per_attempt,
        max_attempts=max_attempts,
        max_active_positions=1,
        max_leverage=max_leverage,
        max_margin_per_attempt=max_margin_per_attempt,
        min_liquidation_stop_buffer=Decimal("25"),
        runtime_confirmation_mode=(
            binding.runtime_confirmation_mode
            if binding
            else StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
        ),
        payoff_profile=(
            binding.payoff_profile if binding else StrategyPayoffProfile.RIGHT_TAIL
        ),
        reference_implementation=binding.reference_implementation if binding else True,
        proven_alpha=binding.proven_alpha if binding else False,
        boundary=boundary,
        blockers=_dedupe(blockers),
        warnings=_dedupe(warnings),
        owner_confirmation_keys=_owner_confirmation_keys(binding=binding, side=side),
        metadata={
            "objective": "small_capital_bounded_runtime_right_tail_experiment",
            "capital_base_source": "owner_supplied_or_default_30u",
            "loss_inside_budget_is_accepted": True,
            "runaway_behavior_is_forbidden": True,
            "manual_withdrawal_only": True,
            "not_proven_alpha": not (binding.proven_alpha if binding else False),
        },
    )


def _owner_confirmation_keys(
    *,
    binding: StrategyImplementationBinding | None,
    side: str,
) -> list[str]:
    keys = [
            "runtime_profile_confirmed",
            "symbol_side_boundary_confirmed",
            "max_loss_budget_confirmed",
            "max_notional_boundary_confirmed",
            "max_active_positions_boundary_confirmed",
            "max_leverage_boundary_confirmed",
            "margin_usage_boundary_confirmed",
            "liquidation_buffer_boundary_confirmed",
            "protection_readiness_source_confirmed",
            "attempt_consumption_rule_confirmed",
            "budget_reservation_rule_confirmed",
            "trusted_active_position_source_confirmed",
            "trusted_account_fact_source_confirmed",
            "stale_fact_behavior_confirmed",
    ]
    if side == "short" or (
        binding is not None
        and binding.metadata.get("short_side_conservative_profile_required")
    ):
        keys.append("short_side_conservative_profile_confirmed")
    return keys


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
