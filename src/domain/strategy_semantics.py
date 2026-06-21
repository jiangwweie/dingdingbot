"""Strategy semantics binding models for BRC runtime governance.

These models describe how a strategy version is represented, fact-checked, and
reviewed before it may produce a shadow OrderCandidate. They do not create
orders, execution intents, routes, venue payloads, or exchange writes.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.strategy_candidate_semantics import StrategyPayoffProfile
from src.domain.strategy_contract_v2 import (
    EntryPolicy,
    EntryPolicyKind,
    LifecycleExitPolicy,
    LifecycleExitPolicyKind,
    StopPolicy,
    StopPolicyKind,
    TakeProfitLevel,
    TakeProfitPolicy,
    TakeProfitPolicyKind,
)


class StrategySemanticsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategyAdmissionLayer(str, Enum):
    SEMANTIC = "semantic"
    ECONOMIC = "economic"
    EXECUTION = "execution"


class StrategyImplementationKind(str, Enum):
    PRICE_ACTION = "price_action"
    REGIME_CLASSIFIER = "regime_classifier"
    DATA_DEPENDENT_BACKLOG = "data_dependent_backlog"


class StrategyCandidateMode(str, Enum):
    SHADOW_ORDER_CANDIDATE_ALLOWED = "shadow_order_candidate_allowed"
    REGIME_CLASSIFIER_ONLY = "regime_classifier_only"
    DATA_BACKLOG_ONLY = "data_backlog_only"


class StrategyRuntimeConfirmationMode(str, Enum):
    RUNTIME_BOUNDED_AUTO_ATTEMPTS = "runtime_bounded_auto_attempts"
    OWNER_CONFIRM_EACH_ENTRY = "owner_confirm_each_entry"
    OBSERVE_ONLY = "observe_only"
    DATA_BACKLOG_ONLY = "data_backlog_only"


class FactAvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    STALE = "stale"


class FactUnavailableBehavior(str, Enum):
    NO_ACTION = "NO_ACTION"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    BLOCK_MISSING_FACTS = "BLOCK_MISSING_FACTS"
    BLOCK_STALE_DATA = "BLOCK_STALE_DATA"


class StrategyFactCheckStatus(str, Enum):
    PASS = "PASS"
    NO_ACTION = "NO_ACTION"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    BLOCK_MISSING_FACTS = "BLOCK_MISSING_FACTS"
    BLOCK_STALE_DATA = "BLOCK_STALE_DATA"


class MarketState(str, Enum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    CHOP = "CHOP"
    RANGE = "RANGE"
    UNCERTAIN = "UNCERTAIN"


class StrategyFactRequirement(StrategySemanticsModel):
    fact_key: str = Field(min_length=1, max_length=128)
    required: bool = True
    description: str = Field(default="", max_length=1024)
    max_age_ms: Optional[int] = Field(default=None, ge=0)
    missing_behavior: FactUnavailableBehavior = (
        FactUnavailableBehavior.BLOCK_MISSING_FACTS
    )
    stale_behavior: FactUnavailableBehavior = FactUnavailableBehavior.BLOCK_STALE_DATA


class StrategyFactSnapshot(StrategySemanticsModel):
    fact_key: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    observed_at_ms: int = Field(ge=0)
    status: FactAvailabilityStatus = FactAvailabilityStatus.AVAILABLE
    freshness_ms: Optional[int] = Field(default=None, ge=0)
    evidence_ref: Optional[str] = Field(default=None, max_length=256)
    value_snapshot: dict[str, Any] = Field(default_factory=dict)


class StrategyEvaluationContext(StrategySemanticsModel):
    context_id: str = Field(min_length=1, max_length=128)
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=128)
    side: str = Field(min_length=1, max_length=32)
    evaluated_at_ms: int = Field(ge=0)
    facts: dict[str, StrategyFactSnapshot] = Field(default_factory=dict)
    market_state: MarketState = MarketState.UNCERTAIN
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _fact_keys_match_values(self) -> "StrategyEvaluationContext":
        for key, fact in self.facts.items():
            if key != fact.fact_key:
                raise ValueError("fact map key must match fact.fact_key")
        return self


class StrategyFactCheckResult(StrategySemanticsModel):
    status: StrategyFactCheckStatus
    missing_facts: list[str] = Field(default_factory=list)
    stale_facts: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    downgrade_notes: list[str] = Field(default_factory=list)

    @property
    def allows_shadow_order_candidate(self) -> bool:
        return self.status == StrategyFactCheckStatus.PASS


class ProtectionPolicy(StrategySemanticsModel):
    stop_policy: StopPolicy
    mandatory: bool = True
    max_loss_reference: Optional[str] = Field(default=None, max_length=256)
    failure_behavior: FactUnavailableBehavior = (
        FactUnavailableBehavior.BLOCK_MISSING_FACTS
    )
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _mandatory_requires_stop(self) -> "ProtectionPolicy":
        if self.mandatory and not self.stop_policy.required:
            raise ValueError("mandatory ProtectionPolicy requires stop_policy.required")
        return self


class ExitPolicy(StrategySemanticsModel):
    take_profit_policy: TakeProfitPolicy
    lifecycle_exit_policy: LifecycleExitPolicy
    runner_required: bool = True
    right_tail_notes: list[str] = Field(default_factory=list)


class StrategyImplementationBinding(StrategySemanticsModel):
    strategy_family_id: str = Field(min_length=1, max_length=128)
    strategy_family_version_id: str = Field(min_length=1, max_length=128)
    canonical_family_id: str = Field(min_length=1, max_length=128)
    implementation_id: str = Field(min_length=1, max_length=128)
    implementation_kind: StrategyImplementationKind
    candidate_mode: StrategyCandidateMode
    source_ref: str = Field(min_length=1, max_length=256)
    supported_sides: list[str] = Field(default_factory=list)
    required_facts: list[StrategyFactRequirement] = Field(default_factory=list)
    optional_facts: list[StrategyFactRequirement] = Field(default_factory=list)
    entry_policy: EntryPolicy
    protection_policy: ProtectionPolicy
    exit_policy: ExitPolicy
    review_metrics: list[str] = Field(default_factory=list)
    proven_alpha: bool = False
    reference_implementation: bool = True
    payoff_profile: StrategyPayoffProfile = StrategyPayoffProfile.RIGHT_TAIL
    runtime_confirmation_mode: StrategyRuntimeConfirmationMode = (
        StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
    )
    owner_confirm_each_entry_required: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _candidate_mode_matches_kind(self) -> "StrategyImplementationBinding":
        if (
            self.implementation_kind == StrategyImplementationKind.REGIME_CLASSIFIER
            and self.candidate_mode
            != StrategyCandidateMode.REGIME_CLASSIFIER_ONLY
        ):
            raise ValueError("regime classifier must use REGIME_CLASSIFIER_ONLY")
        if (
            self.implementation_kind
            == StrategyImplementationKind.DATA_DEPENDENT_BACKLOG
            and self.candidate_mode != StrategyCandidateMode.DATA_BACKLOG_ONLY
        ):
            raise ValueError("data backlog must use DATA_BACKLOG_ONLY")
        if (
            self.candidate_mode != StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED
            and self.runtime_confirmation_mode
            == StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
        ):
            raise ValueError(
                "non-candidate strategy bindings cannot use runtime-bounded auto attempts"
            )
        if (
            self.runtime_confirmation_mode
            == StrategyRuntimeConfirmationMode.OWNER_CONFIRM_EACH_ENTRY
            and not self.owner_confirm_each_entry_required
        ):
            raise ValueError(
                "OWNER_CONFIRM_EACH_ENTRY mode requires owner_confirm_each_entry_required"
            )
        return self

    @property
    def allows_shadow_order_candidate(self) -> bool:
        return self.candidate_mode == StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED

    def fact_check(self, context: StrategyEvaluationContext) -> StrategyFactCheckResult:
        return check_required_facts(
            requirements=[*self.required_facts, *self.optional_facts],
            context=context,
        )

    def candidate_order_type(self) -> str:
        if self.entry_policy.kind in {
            EntryPolicyKind.MARKET_AFTER_CONFIRMED_CLOSE,
            EntryPolicyKind.MARKET_NEXT_EXECUTABLE_OPPORTUNITY,
            EntryPolicyKind.MARKET_NEXT_OPEN,
        }:
            return "market"
        if self.entry_policy.kind == EntryPolicyKind.LIMIT:
            return "limit"
        if self.entry_policy.kind == EntryPolicyKind.STOP_MARKET:
            return "stop_market"
        return "signal_only"

    def semantic_snapshot(self) -> dict[str, Any]:
        return {
            "strategy_family_id": self.strategy_family_id,
            "strategy_family_version_id": self.strategy_family_version_id,
            "canonical_family_id": self.canonical_family_id,
            "implementation_id": self.implementation_id,
            "implementation_kind": self.implementation_kind.value,
            "candidate_mode": self.candidate_mode.value,
            "runtime_confirmation_mode": self.runtime_confirmation_mode.value,
            "payoff_profile": self.payoff_profile.value,
            "proven_alpha": self.proven_alpha,
            "reference_implementation": self.reference_implementation,
            "owner_confirm_each_entry_required": self.owner_confirm_each_entry_required,
        }


class StrategySemanticsCatalog(StrategySemanticsModel):
    bindings: list[StrategyImplementationBinding]

    @model_validator(mode="after")
    def _unique_bindings(self) -> "StrategySemanticsCatalog":
        seen: set[tuple[str, str]] = set()
        for binding in self.bindings:
            key = (binding.strategy_family_id, binding.strategy_family_version_id)
            if key in seen:
                raise ValueError(f"duplicate strategy semantics binding: {key}")
            seen.add(key)
        return self

    def get_binding(
        self,
        *,
        strategy_family_id: str,
        strategy_family_version_id: str,
    ) -> StrategyImplementationBinding:
        for binding in self.bindings:
            if (
                binding.strategy_family_id == strategy_family_id
                and binding.strategy_family_version_id == strategy_family_version_id
            ):
                return binding
        raise KeyError(
            f"strategy semantics binding not found: "
            f"{strategy_family_id}:{strategy_family_version_id}"
        )


def check_required_facts(
    *,
    requirements: list[StrategyFactRequirement],
    context: StrategyEvaluationContext,
) -> StrategyFactCheckResult:
    status = StrategyFactCheckStatus.PASS
    missing: list[str] = []
    stale: list[str] = []
    reason_codes: list[str] = []
    notes: list[str] = []

    for requirement in requirements:
        fact = context.facts.get(requirement.fact_key)
        if fact is None or fact.status == FactAvailabilityStatus.MISSING:
            if requirement.required:
                missing.append(requirement.fact_key)
                next_status = _status_from_behavior(requirement.missing_behavior)
                status = _max_fact_status(status, next_status)
                reason_codes.append(f"{requirement.fact_key}_missing")
            else:
                notes.append(f"optional fact missing: {requirement.fact_key}")
            continue

        is_stale = fact.status == FactAvailabilityStatus.STALE
        if (
            requirement.max_age_ms is not None
            and fact.freshness_ms is not None
            and fact.freshness_ms > requirement.max_age_ms
        ):
            is_stale = True
        if is_stale:
            stale.append(requirement.fact_key)
            next_status = _status_from_behavior(requirement.stale_behavior)
            status = _max_fact_status(status, next_status)
            reason_codes.append(f"{requirement.fact_key}_stale")

    return StrategyFactCheckResult(
        status=status,
        missing_facts=missing,
        stale_facts=stale,
        reason_codes=reason_codes,
        downgrade_notes=notes,
    )


def initial_strategy_semantics_catalog() -> StrategySemanticsCatalog:
    """Return the first B0 strategy semantics bindings.

    CPM/BRF are reference implementations, RMR is regime evidence, and FCO is a
    declared data dependency. None of these bindings is proven-alpha approval or
    execution authority.
    """

    return StrategySemanticsCatalog(
        bindings=[
            _cpm_binding(
                strategy_family_id="CPM-RO-001",
                strategy_family_version_id="CPM-RO-001-v0",
            ),
            _cpm_binding(
                strategy_family_id="CPM-001",
                strategy_family_version_id="CPM-001-v0",
            ),
            _mpg_binding(),
            _pilot_strategygroup_binding(
                strategy_family_id="TEQ-001",
                strategy_family_version_id="TEQ-001-v0",
                canonical_family_id="TEQ-001",
                implementation_id="teq-equity-like-momentum-pilot-v0",
                source_ref="src/domain/reference_price_action_evaluators.py",
                supported_sides=["long"],
                trigger="equity_like_momentum_breakout",
                stop_reference="recent_breakout_floor_or_atr_reference",
                reference_role="equity_like_long_momentum",
            ),
            _pilot_strategygroup_binding(
                strategy_family_id="FBS-001",
                strategy_family_version_id="FBS-001-v0",
                canonical_family_id="FBS-001",
                implementation_id="fbs-funding-basis-stress-pilot-v0",
                source_ref="src/domain/reference_price_action_evaluators.py",
                supported_sides=["long"],
                trigger="negative_funding_squeeze_followthrough",
                stop_reference="funding_stress_invalidation_or_atr_reference",
                reference_role="negative_funding_long_squeeze",
                optional_fact_key="funding_rate",
            ),
            _pilot_strategygroup_binding(
                strategy_family_id="PMR-001",
                strategy_family_version_id="PMR-001-v0",
                canonical_family_id="PMR-001",
                implementation_id="pmr-metal-breakdown-pilot-v0",
                source_ref="src/domain/reference_price_action_evaluators.py",
                supported_sides=["short"],
                trigger="metal_role_breakdown_short",
                stop_reference="recent_breakdown_reclaim_or_atr_reference",
                reference_role="precious_metal_short_overlay",
            ),
            _pilot_strategygroup_binding(
                strategy_family_id="SOR-001",
                strategy_family_version_id="SOR-001-v0",
                canonical_family_id="SOR-001",
                implementation_id="sor-opening-range-breakdown-pilot-v0",
                source_ref="src/domain/reference_price_action_evaluators.py",
                supported_sides=["short"],
                trigger="session_opening_range_breakdown",
                stop_reference="opening_range_reclaim_or_atr_reference",
                reference_role="session_opening_range_short",
                optional_fact_key="session_window_state",
            ),
            _brf_binding(),
            _btpc_binding(),
            _lsr_binding(),
            _rbr_binding(),
            _vcb_binding(),
            _rmr_binding(),
            _fco_binding(),
        ]
    )


def _cpm_binding(
    *,
    strategy_family_id: str,
    strategy_family_version_id: str,
) -> StrategyImplementationBinding:
    return StrategyImplementationBinding(
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        canonical_family_id="CPM-001",
        implementation_id="cpm-price-action-reference-v0",
        implementation_kind=StrategyImplementationKind.PRICE_ACTION,
        candidate_mode=StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED,
        source_ref="src/domain/cpm_historical_evaluator.py",
        supported_sides=["long"],
        required_facts=_price_action_required_facts(),
        optional_facts=[
            _fact(
                "funding_rate",
                required=False,
                description="Optional funding caveat for review, not a current blocker.",
                missing_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
                stale_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
            ),
        ],
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.MARKET_NEXT_EXECUTABLE_OPPORTUNITY,
            trigger="pullback_reclaim_confirmed",
            parameters={"reference_family": "CPM-001", "side": "long"},
        ),
        protection_policy=ProtectionPolicy(
            stop_policy=StopPolicy(
                kind=StopPolicyKind.STRUCTURE_REFERENCE,
                required=True,
                reference={"structure": "pullback_low_or_atr_reference"},
                risk_notes="bounded-loss stop; not the full strategy exit",
            ),
            max_loss_reference="runtime.max_loss_budget_per_attempt",
            notes=["CPM is long-only and must not run without concrete stop reference."],
        ),
        exit_policy=_right_tail_exit_policy("partial_tp_plus_runner"),
        review_metrics=_right_tail_review_metrics(),
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        runtime_confirmation_mode=(
            StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
        ),
        owner_confirm_each_entry_required=False,
        metadata={
            "semantic_admission_only": True,
            "not_proven_alpha": True,
            "reference_role": "long_pullback_continuation",
            "runtime_confirmation_note": (
                "Owner confirms bounded runtime/profile; entries may be attempted "
                "automatically within runtime boundaries."
            ),
        },
    )


def _mpg_binding() -> StrategyImplementationBinding:
    return StrategyImplementationBinding(
        strategy_family_id="MPG-001",
        strategy_family_version_id="MPG-001-v0",
        canonical_family_id="MPG-001",
        implementation_id="mpg-momentum-persistence-reference-v0",
        implementation_kind=StrategyImplementationKind.PRICE_ACTION,
        candidate_mode=StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED,
        source_ref="src/domain/mpg_momentum_persistence_evaluator.py",
        supported_sides=["long"],
        required_facts=_price_action_required_facts(),
        optional_facts=[
            _fact(
                "funding_rate",
                required=False,
                description="Optional momentum-crowding caveat for review.",
                missing_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
                stale_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
            ),
        ],
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.MARKET_NEXT_EXECUTABLE_OPPORTUNITY,
            trigger="momentum_persistence_confirmed",
            parameters={"reference_family": "MPG-001", "side": "long"},
        ),
        protection_policy=ProtectionPolicy(
            stop_policy=StopPolicy(
                kind=StopPolicyKind.STRUCTURE_REFERENCE,
                required=True,
                reference={"structure": "recent_momentum_floor_or_atr_reference"},
                risk_notes="momentum persistence requires a concrete hard stop",
            ),
            max_loss_reference="runtime.max_loss_budget_per_attempt",
            notes=[
                "MPG is a long momentum-persistence reference candidate.",
                "It is semantic admission only, not proof of profitable alpha.",
            ],
        ),
        exit_policy=_right_tail_exit_policy("partial_tp_plus_momentum_runner"),
        review_metrics=_right_tail_review_metrics()
        + ["momentum_follow_through", "breakout_failure_rate"],
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        runtime_confirmation_mode=(
            StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
        ),
        owner_confirm_each_entry_required=False,
        metadata={
            "semantic_admission_only": True,
            "not_proven_alpha": True,
            "reference_role": "long_momentum_persistence",
            "runtime_confirmation_note": (
                "Owner confirms bounded runtime/profile; entries may be attempted "
                "automatically within runtime boundaries."
            ),
        },
    )


def _pilot_strategygroup_binding(
    *,
    strategy_family_id: str,
    strategy_family_version_id: str,
    canonical_family_id: str,
    implementation_id: str,
    source_ref: str,
    supported_sides: list[str],
    trigger: str,
    stop_reference: str,
    reference_role: str,
    optional_fact_key: str | None = None,
) -> StrategyImplementationBinding:
    optional_facts = [
        _fact(
            optional_fact_key,
            required=False,
            description=(
                f"Optional {optional_fact_key} caveat for pilot review."
            ),
            missing_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
            stale_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
        )
    ] if optional_fact_key else []
    return StrategyImplementationBinding(
        strategy_family_id=strategy_family_id,
        strategy_family_version_id=strategy_family_version_id,
        canonical_family_id=canonical_family_id,
        implementation_id=implementation_id,
        implementation_kind=StrategyImplementationKind.PRICE_ACTION,
        candidate_mode=StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED,
        source_ref=source_ref,
        supported_sides=supported_sides,
        required_facts=_price_action_required_facts(),
        optional_facts=optional_facts,
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.MARKET_NEXT_EXECUTABLE_OPPORTUNITY,
            trigger=trigger,
            parameters={
                "reference_family": strategy_family_id,
                "supported_sides": supported_sides,
            },
        ),
        protection_policy=ProtectionPolicy(
            stop_policy=StopPolicy(
                kind=StopPolicyKind.STRUCTURE_REFERENCE,
                required=True,
                reference={"structure": stop_reference},
                risk_notes="pilot StrategyGroup actions require a concrete hard stop",
            ),
            max_loss_reference="runtime.max_loss_budget_per_attempt",
            notes=[
                f"{strategy_family_id} is a pilot StrategyGroup reference route.",
                "It is semantic admission only, not proof of profitable alpha.",
            ],
        ),
        exit_policy=_right_tail_exit_policy("partial_tp_plus_review_runner"),
        review_metrics=_right_tail_review_metrics()
        + ["strategygroup_pilot_follow_through", "false_signal_rate"],
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        runtime_confirmation_mode=(
            StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
        ),
        owner_confirm_each_entry_required=False,
        metadata={
            "semantic_admission_only": True,
            "not_proven_alpha": True,
            "reference_role": reference_role,
            "pilot_strategygroup_route": True,
            "runtime_confirmation_note": (
                "Owner confirms bounded runtime/profile; entries may be attempted "
                "automatically only within runtime boundaries and after FinalGate."
            ),
        },
    )


def _brf_binding() -> StrategyImplementationBinding:
    return StrategyImplementationBinding(
        strategy_family_id="BRF-001",
        strategy_family_version_id="BRF-001-v0",
        canonical_family_id="BRF-001",
        implementation_id="brf-price-action-reference-v0",
        implementation_kind=StrategyImplementationKind.PRICE_ACTION,
        candidate_mode=StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED,
        source_ref="src/domain/brf_price_action_evaluator.py",
        supported_sides=["short"],
        required_facts=[
            *_price_action_required_facts(),
            _fact(
                "short_squeeze_risk",
                description="Closed-candle or review evidence for rally squeeze risk.",
                missing_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
                stale_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
            ),
        ],
        optional_facts=[
            _fact(
                "funding_rate",
                required=False,
                description="Optional short-side crowding caveat.",
                missing_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
                stale_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
            ),
        ],
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.MARKET_NEXT_EXECUTABLE_OPPORTUNITY,
            trigger="bear_rally_failure_confirmed",
            parameters={"reference_family": "BRF-001", "side": "short"},
        ),
        protection_policy=ProtectionPolicy(
            stop_policy=StopPolicy(
                kind=StopPolicyKind.STRUCTURE_REFERENCE,
                required=True,
                reference={"structure": "rally_high_or_atr_reference"},
                risk_notes="short-side hard stop required because squeeze risk is asymmetric",
            ),
            max_loss_reference="runtime.max_loss_budget_per_attempt",
            notes=[
                "BRF uses the Owner-selected short-side profile boundary.",
                "BRF may auto-attempt inside that acknowledged profile without per-entry Owner confirmation.",
            ],
        ),
        exit_policy=_right_tail_exit_policy("partial_tp_plus_downside_runner"),
        review_metrics=_right_tail_review_metrics()
        + ["short_squeeze_excursion", "rally_failure_follow_through"],
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        runtime_confirmation_mode=(
            StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
        ),
        owner_confirm_each_entry_required=False,
        metadata={
            "semantic_admission_only": True,
            "not_proven_alpha": True,
            "reference_role": "short_bear_rally_failure",
            "allocated_short_profile_boundary_required": True,
            "short_side_conservative_profile_required": True,
            "runtime_confirmation_note": (
                "Owner confirms short-side runtime boundaries once; BRF entries "
                "do not require per-entry Owner confirmation after promotion."
            ),
        },
    )


def _btpc_binding() -> StrategyImplementationBinding:
    return StrategyImplementationBinding(
        strategy_family_id="BTPC-001",
        strategy_family_version_id="BTPC-001-v0",
        canonical_family_id="BTPC-001",
        implementation_id="btpc-price-action-reference-v0",
        implementation_kind=StrategyImplementationKind.PRICE_ACTION,
        candidate_mode=StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED,
        source_ref="src/domain/reference_price_action_evaluators.py",
        supported_sides=["short"],
        required_facts=_price_action_required_facts(),
        optional_facts=[
            _fact(
                "funding_rate",
                required=False,
                description="Optional short-side funding caveat for review.",
                missing_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
                stale_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
            ),
        ],
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.MARKET_NEXT_EXECUTABLE_OPPORTUNITY,
            trigger="bear_trend_pullback_loss_confirmed",
            parameters={"reference_family": "BTPC-001", "side": "short"},
        ),
        protection_policy=ProtectionPolicy(
            stop_policy=StopPolicy(
                kind=StopPolicyKind.STRUCTURE_REFERENCE,
                required=True,
                reference={"structure": "pullback_high_or_atr_reference"},
                risk_notes="short-side pullback continuation requires hard stop above pullback high",
            ),
            max_loss_reference="runtime.max_loss_budget_per_attempt",
            notes=[
                "BTPC is a short-side right-tail reference candidate.",
                "Use the Owner-selected short-side profile boundary until live review upgrades it.",
            ],
        ),
        exit_policy=_right_tail_exit_policy("partial_tp_plus_downside_runner"),
        review_metrics=_right_tail_review_metrics()
        + ["short_squeeze_excursion", "pullback_continuation_follow_through"],
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        runtime_confirmation_mode=(
            StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
        ),
        owner_confirm_each_entry_required=False,
        metadata={
            "semantic_admission_only": True,
            "not_proven_alpha": True,
            "reference_role": "short_bear_trend_pullback_continuation",
            "allocated_short_profile_boundary_required": True,
            "short_side_conservative_profile_required": True,
        },
    )


def _lsr_binding() -> StrategyImplementationBinding:
    return StrategyImplementationBinding(
        strategy_family_id="LSR-001",
        strategy_family_version_id="LSR-001-v0",
        canonical_family_id="LSR-001",
        implementation_id="lsr-price-action-reference-v0",
        implementation_kind=StrategyImplementationKind.PRICE_ACTION,
        candidate_mode=StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED,
        source_ref="src/domain/reference_price_action_evaluators.py",
        supported_sides=["long", "short"],
        required_facts=[
            *_price_action_required_facts(),
            _fact("range_structure", description="Range/sweep structure for mean reversion."),
        ],
        optional_facts=[
            _fact(
                "volatility_state",
                required=False,
                description="Optional volatility caveat for sweep reversals.",
                missing_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
                stale_behavior=FactUnavailableBehavior.OBSERVE_ONLY,
            ),
        ],
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.MARKET_NEXT_EXECUTABLE_OPPORTUNITY,
            trigger="liquidity_sweep_reclaim_confirmed",
            parameters={"reference_family": "LSR-001", "side": "long_or_short"},
        ),
        protection_policy=ProtectionPolicy(
            stop_policy=StopPolicy(
                kind=StopPolicyKind.STRUCTURE_REFERENCE,
                required=True,
                reference={"structure": "sweep_extreme_with_buffer"},
                risk_notes="mean-reversion setup invalidates beyond sweep extreme",
            ),
            max_loss_reference="runtime.max_loss_budget_per_attempt",
            notes=["LSR is a bounded mean-reversion candidate, not a right-tail trend runner by default."],
        ),
        exit_policy=_mean_reversion_exit_policy("fixed_rr_or_range_mid_target"),
        review_metrics=_mean_reversion_review_metrics(),
        payoff_profile=StrategyPayoffProfile.MEAN_REVERSION,
        runtime_confirmation_mode=(
            StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
        ),
        owner_confirm_each_entry_required=False,
        metadata={
            "semantic_admission_only": True,
            "not_proven_alpha": True,
            "reference_role": "liquidity_sweep_reversal",
        },
    )


def _rbr_binding() -> StrategyImplementationBinding:
    return StrategyImplementationBinding(
        strategy_family_id="RBR-001",
        strategy_family_version_id="RBR-001-v0",
        canonical_family_id="RBR-001",
        implementation_id="rbr-price-action-reference-v0",
        implementation_kind=StrategyImplementationKind.PRICE_ACTION,
        candidate_mode=StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED,
        source_ref="src/domain/reference_price_action_evaluators.py",
        supported_sides=["long", "short"],
        required_facts=[
            *_price_action_required_facts(),
            _fact("range_structure", description="Range boundary evidence."),
            _fact("volatility_state", description="Bounded volatility / chop evidence."),
        ],
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.MARKET_NEXT_EXECUTABLE_OPPORTUNITY,
            trigger="range_boundary_rejection_confirmed",
            parameters={"reference_family": "RBR-001", "side": "long_or_short"},
        ),
        protection_policy=ProtectionPolicy(
            stop_policy=StopPolicy(
                kind=StopPolicyKind.STRUCTURE_REFERENCE,
                required=True,
                reference={"structure": "range_boundary_with_buffer"},
                risk_notes="range reversion invalidates outside rejected boundary",
            ),
            max_loss_reference="runtime.max_loss_budget_per_attempt",
            notes=["RBR uses fixed RR/range exits; do not force a trend runner by default."],
        ),
        exit_policy=_mean_reversion_exit_policy("fixed_rr_or_opposite_range_target"),
        review_metrics=_mean_reversion_review_metrics()
        + ["range_boundary_quality", "time_in_range_after_entry"],
        payoff_profile=StrategyPayoffProfile.MEAN_REVERSION,
        runtime_confirmation_mode=(
            StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
        ),
        owner_confirm_each_entry_required=False,
        metadata={
            "semantic_admission_only": True,
            "not_proven_alpha": True,
            "reference_role": "range_boundary_reversion",
            "rmr_context_is_downgrade_not_hard_filter": True,
        },
    )


def _vcb_binding() -> StrategyImplementationBinding:
    return StrategyImplementationBinding(
        strategy_family_id="VCB-001",
        strategy_family_version_id="VCB-001-v0",
        canonical_family_id="VCB-001",
        implementation_id="vcb-price-action-reference-v0",
        implementation_kind=StrategyImplementationKind.PRICE_ACTION,
        candidate_mode=StrategyCandidateMode.SHADOW_ORDER_CANDIDATE_ALLOWED,
        source_ref="src/domain/reference_price_action_evaluators.py",
        supported_sides=["long", "short"],
        required_facts=[
            *_price_action_required_facts(),
            _fact("volatility_state", description="Compression / expansion state."),
        ],
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.MARKET_NEXT_EXECUTABLE_OPPORTUNITY,
            trigger="volatility_compression_breakout_confirmed",
            parameters={"reference_family": "VCB-001", "side": "long_or_short"},
        ),
        protection_policy=ProtectionPolicy(
            stop_policy=StopPolicy(
                kind=StopPolicyKind.STRUCTURE_REFERENCE,
                required=True,
                reference={"structure": "opposite_compression_boundary"},
                risk_notes="failed breakout invalidates back inside compression range",
            ),
            max_loss_reference="runtime.max_loss_budget_per_attempt",
            notes=["VCB is a right-tail breakout candidate but must keep hard stop concrete."],
        ),
        exit_policy=_right_tail_exit_policy("partial_tp_plus_breakout_runner"),
        review_metrics=_right_tail_review_metrics()
        + ["false_breakout_rate", "volatility_expansion_follow_through"],
        payoff_profile=StrategyPayoffProfile.RIGHT_TAIL,
        runtime_confirmation_mode=(
            StrategyRuntimeConfirmationMode.RUNTIME_BOUNDED_AUTO_ATTEMPTS
        ),
        owner_confirm_each_entry_required=False,
        metadata={
            "semantic_admission_only": True,
            "not_proven_alpha": True,
            "reference_role": "volatility_compression_breakout",
        },
    )


def _rmr_binding() -> StrategyImplementationBinding:
    return StrategyImplementationBinding(
        strategy_family_id="RMR-001",
        strategy_family_version_id="RMR-001-v0",
        canonical_family_id="RMR-001",
        implementation_id="rmr-regime-classifier-v0",
        implementation_kind=StrategyImplementationKind.REGIME_CLASSIFIER,
        candidate_mode=StrategyCandidateMode.REGIME_CLASSIFIER_ONLY,
        source_ref="docs/ops/srd-001-strategy-research-direction-refresh.md",
        supported_sides=["none"],
        required_facts=[
            _fact("ohlcv_1h", description="Closed 1h candles for range/chop evidence."),
            _fact("ohlcv_4h", description="Closed 4h candles for market-state context."),
            _fact("range_structure", description="Pre-observable range boundary evidence."),
            _fact("volatility_state", description="ATR/range compression or expansion state."),
        ],
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.SIGNAL_ONLY,
            trigger="regime_classification_only",
            parameters={"emits": [state.value for state in MarketState]},
        ),
        protection_policy=ProtectionPolicy(
            stop_policy=StopPolicy(
                kind=StopPolicyKind.NONE,
                required=False,
                risk_notes="RMR does not trade; protection is delegated to CPM/BRF if downgraded.",
            ),
            mandatory=False,
            notes=["RMR output is regime evidence, not execution authority."],
        ),
        exit_policy=ExitPolicy(
            take_profit_policy=TakeProfitPolicy(kind=TakeProfitPolicyKind.LIFECYCLE_ONLY),
            lifecycle_exit_policy=LifecycleExitPolicy(
                kind=LifecycleExitPolicyKind.CUSTOM_NAMED,
                parameters={"classifier_only": True},
            ),
            runner_required=False,
        ),
        review_metrics=["classifier_confidence", "market_state_accuracy", "downgrade_effect"],
        payoff_profile=StrategyPayoffProfile.REGIME_CONTEXT,
        runtime_confirmation_mode=StrategyRuntimeConfirmationMode.OBSERVE_ONLY,
        owner_confirm_each_entry_required=False,
        metadata={
            "semantic_admission_only": True,
            "not_trade_strategy": True,
            "must_not_hard_filter_before_review": True,
        },
    )


def _fco_binding() -> StrategyImplementationBinding:
    return StrategyImplementationBinding(
        strategy_family_id="FCO-001",
        strategy_family_version_id="FCO-001-v0",
        canonical_family_id="FCO-001",
        implementation_id="fco-data-backlog-v0",
        implementation_kind=StrategyImplementationKind.DATA_DEPENDENT_BACKLOG,
        candidate_mode=StrategyCandidateMode.DATA_BACKLOG_ONLY,
        source_ref="docs/canon/BRC_TARGET_SEMANTICS.md",
        supported_sides=["long", "short", "none"],
        required_facts=[
            _fact("funding_rate", description="Funding-rate snapshot with freshness."),
            _fact("open_interest", description="Open-interest snapshot with freshness."),
            _fact("crowding_proxy", description="Crowding proxy definition and coverage."),
        ],
        entry_policy=EntryPolicy(
            kind=EntryPolicyKind.SIGNAL_ONLY,
            trigger="data_dependency_backlog_only",
            parameters={"blocked_until": "funding_oi_required_facts_defined"},
        ),
        protection_policy=ProtectionPolicy(
            stop_policy=StopPolicy(
                kind=StopPolicyKind.NONE,
                required=False,
                risk_notes="FCO is not a trading strategy until data dependency is resolved.",
            ),
            mandatory=False,
        ),
        exit_policy=ExitPolicy(
            take_profit_policy=TakeProfitPolicy(kind=TakeProfitPolicyKind.LIFECYCLE_ONLY),
            lifecycle_exit_policy=LifecycleExitPolicy(
                kind=LifecycleExitPolicyKind.CUSTOM_NAMED,
                parameters={"data_backlog_only": True},
            ),
            runner_required=False,
        ),
        review_metrics=["data_coverage", "freshness", "missing_fact_rate"],
        payoff_profile=StrategyPayoffProfile.DATA_BACKLOG,
        runtime_confirmation_mode=StrategyRuntimeConfirmationMode.DATA_BACKLOG_ONLY,
        owner_confirm_each_entry_required=False,
        metadata={
            "semantic_admission_only": True,
            "data_dependency_backlog": True,
        },
    )


def _price_action_required_facts() -> list[StrategyFactRequirement]:
    return [
        _fact("ohlcv_1h", description="Closed 1h OHLCV window."),
        _fact("ohlcv_4h", description="Closed 4h OHLCV context window."),
        _fact("price_action_structure", description="Pullback/reclaim or rally-failure evidence."),
        _fact("account_facts", description="Read-only account facts snapshot."),
        _fact("runtime_boundary", description="Runtime attempts/budget/leverage boundary snapshot."),
        _fact("position_projection", description="Trusted local active-position projection."),
    ]


def _fact(
    fact_key: str,
    *,
    required: bool = True,
    description: str = "",
    max_age_ms: Optional[int] = None,
    missing_behavior: FactUnavailableBehavior = (
        FactUnavailableBehavior.BLOCK_MISSING_FACTS
    ),
    stale_behavior: FactUnavailableBehavior = FactUnavailableBehavior.BLOCK_STALE_DATA,
) -> StrategyFactRequirement:
    return StrategyFactRequirement(
        fact_key=fact_key,
        required=required,
        description=description,
        max_age_ms=max_age_ms,
        missing_behavior=missing_behavior,
        stale_behavior=stale_behavior,
    )


def _right_tail_exit_policy(note: str) -> ExitPolicy:
    return ExitPolicy(
        take_profit_policy=TakeProfitPolicy(
            kind=TakeProfitPolicyKind.MULTI_TP_RR,
            levels=[
                TakeProfitLevel(rr=Decimal("1"), position_ratio=Decimal("0.5")),
            ],
        ),
        lifecycle_exit_policy=LifecycleExitPolicy(
            kind=LifecycleExitPolicyKind.TRAILING_ATR,
            parameters={"runner": True, "note": note},
        ),
        runner_required=True,
        right_tail_notes=[
            "partial profit is allowed, but a runner must preserve right-tail exposure",
            "generic fixed TP must not replace lifecycle exit semantics",
        ],
    )


def _mean_reversion_exit_policy(note: str) -> ExitPolicy:
    return ExitPolicy(
        take_profit_policy=TakeProfitPolicy(
            kind=TakeProfitPolicyKind.MULTI_TP_RR,
            levels=[
                TakeProfitLevel(rr=Decimal("1"), position_ratio=Decimal("0.5")),
                TakeProfitLevel(rr=Decimal("2"), position_ratio=Decimal("0.5")),
            ],
        ),
        lifecycle_exit_policy=LifecycleExitPolicy(
            kind=LifecycleExitPolicyKind.TIME_STOP,
            parameters={"runner": False, "note": note},
        ),
        runner_required=False,
        right_tail_notes=[
            "mean-reversion candidates use fixed RR or range targets by default",
            "do not force right-tail runner semantics onto range trades",
        ],
    )


def _right_tail_review_metrics() -> list[str]:
    return [
        "MFE",
        "MAE",
        "R_multiple",
        "tail_win_size",
        "small_loss_count",
        "winner_hold_time",
        "runner_giveback",
        "runner_capped_too_early",
        "stop_effectiveness",
        "attempt_continuation_quality",
    ]


def _mean_reversion_review_metrics() -> list[str]:
    return [
        "MFE",
        "MAE",
        "R_multiple",
        "range_target_hit",
        "time_to_range_target",
        "small_loss_count",
        "stop_effectiveness",
        "time_stop_effectiveness",
        "attempt_quality",
    ]


def _status_from_behavior(
    behavior: FactUnavailableBehavior,
) -> StrategyFactCheckStatus:
    return StrategyFactCheckStatus(behavior.value)


def _max_fact_status(
    current: StrategyFactCheckStatus,
    candidate: StrategyFactCheckStatus,
) -> StrategyFactCheckStatus:
    severity = {
        StrategyFactCheckStatus.PASS: 0,
        StrategyFactCheckStatus.NO_ACTION: 1,
        StrategyFactCheckStatus.OBSERVE_ONLY: 2,
        StrategyFactCheckStatus.BLOCK_MISSING_FACTS: 3,
        StrategyFactCheckStatus.BLOCK_STALE_DATA: 3,
    }
    if severity[candidate] > severity[current]:
        return candidate
    return current
