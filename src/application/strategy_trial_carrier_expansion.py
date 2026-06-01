"""Read-only second-carrier expansion bootstrap models.

The objects here represent StrategyFamily -> Carrier -> RiskCapProfile ->
ProtectionPlan -> Trial readiness metadata only. They do not create execution
intents, permissions, runtime state, orders, or exchange requests.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


FIRST_CARRIER_ID = "MI-001-BNB-LONG"
SECOND_CARRIER_ID = "TB-BTC-SHORT"


class CarrierRiskCapDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    cap_profile_id: str
    per_carrier_cap: Decimal = Field(gt=Decimal("0"))
    max_trial_attempts: int = Field(gt=0)
    max_daily_attempts: int = Field(gt=0)
    max_concurrent_positions: int = Field(gt=0)
    daily_loss_limit: Decimal = Field(gt=Decimal("0"))
    leverage: Decimal = Field(gt=Decimal("0"))
    status: Literal["draft_metadata_only"] = "draft_metadata_only"


class ProtectionFeasibility(BaseModel):
    model_config = ConfigDict(frozen=True)

    protection_plan_type: Literal["single_tp_plus_sl"]
    feasibility: Literal["feasible_pending_testnet_rehearsal", "comparison_only_not_ready"]
    required_before_live: list[str]
    live_ready: Literal[False] = False


class CarrierExpansionCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    carrier_id: str
    strategy_family: str
    symbol: str
    runtime_symbol: str
    side: Literal["long", "short"]
    role: Literal["first_carrier", "second_carrier_bootstrap", "comparison_only"]
    regime_fit: str
    risk_cap_draft: CarrierRiskCapDraft
    protection_feasibility: ProtectionFeasibility
    observation_readiness_state: str
    testnet_rehearsal_gap_summary: list[str]
    api_visibility: str
    owner_console_visibility: str
    budget_foundation_eligible: bool
    evidence_gap_warning: bool
    live_ready: Literal[False] = False
    auto_execution_enabled: Literal[False] = False
    order_permission_granted: Literal[False] = False
    execution_intent_created: Literal[False] = False
    order_created: Literal[False] = False


class SecondCarrierExpansionResponse(BaseModel):
    generated_from: Literal["second_carrier_expansion_bootstrap_v1"] = (
        "second_carrier_expansion_bootstrap_v1"
    )
    final_state: Literal["second_carrier_represented_generically"] = (
        "second_carrier_represented_generically"
    )
    first_carrier_id: Literal["MI-001-BNB-LONG"] = FIRST_CARRIER_ID
    selected_second_carrier_id: Literal["TB-BTC-SHORT"] = SECOND_CARRIER_ID
    owner_market_view: str
    generic_chain: list[str]
    carriers: list[CarrierExpansionCandidate]
    warnings: list[str]
    non_permissions: dict[str, bool]


def build_second_carrier_expansion_bootstrap() -> SecondCarrierExpansionResponse:
    """Build the generic, non-live second-carrier expansion read model."""

    return SecondCarrierExpansionResponse(
        owner_market_view="bearish_1_2_months_then_range; symbols BTC/ETH/SOL/BNB",
        generic_chain=[
            "StrategyFamily",
            "Carrier",
            "RiskCapProfile",
            "ProtectionPlan",
            "Trial",
        ],
        carriers=[
            _bnb_first_carrier(),
            _tb_btc_short_second_carrier(),
            _vb_sol_short_comparison(),
            _cpm_pc_eth_short_comparison(),
            _mi001_sol_long_comparison(),
        ],
        warnings=[
            "TB-BTC-SHORT is represented as metadata/readiness bootstrap only.",
            "No controlled testnet rehearsal is recorded for TB-BTC-SHORT.",
            "Range regime can reduce short-followthrough quality; this is a disclosure gap, not a hidden failure.",
            "No carrier in this response is live-ready or auto-executable.",
        ],
        non_permissions=_non_permissions(),
    )


def budget_eligible_carrier_ids() -> set[str]:
    """Finite carrier ids allowed in budget metadata foundation."""

    return {
        FIRST_CARRIER_ID,
        SECOND_CARRIER_ID,
    }


def carrier_by_id(carrier_id: str) -> CarrierExpansionCandidate | None:
    for carrier in build_second_carrier_expansion_bootstrap().carriers:
        if carrier.carrier_id == carrier_id:
            return carrier
    return None


def _bnb_first_carrier() -> CarrierExpansionCandidate:
    return CarrierExpansionCandidate(
        carrier_id=FIRST_CARRIER_ID,
        strategy_family="MI-001",
        symbol="BNBUSDT",
        runtime_symbol="BNB/USDT:USDT",
        side="long",
        role="first_carrier",
        regime_fit=(
            "first execution carrier already exercised through BNB-specific "
            "observation/readiness/testnet rehearsal; not used as architecture center"
        ),
        risk_cap_draft=CarrierRiskCapDraft(
            cap_profile_id="MI-001-BNB-LONG-controlled-testnet-carrier-cap-v0",
            per_carrier_cap=Decimal("20"),
            max_trial_attempts=1,
            max_daily_attempts=1,
            max_concurrent_positions=1,
            daily_loss_limit=Decimal("20"),
            leverage=Decimal("1"),
        ),
        protection_feasibility=ProtectionFeasibility(
            protection_plan_type="single_tp_plus_sl",
            feasibility="feasible_pending_testnet_rehearsal",
            required_before_live=["final hard safety preflight", "explicit Owner live authorization"],
        ),
        observation_readiness_state="first_carrier_observed_and_rehearsed_but_not_live_ready",
        testnet_rehearsal_gap_summary=[
            "BNB same-path testnet rehearsal is recorded.",
            "BNB evidence does not satisfy second-carrier rehearsal.",
        ],
        api_visibility="/api/brc/strategy-trial-architecture/bnb-first-carrier",
        owner_console_visibility="/trial-confirmation primary carrier",
        budget_foundation_eligible=True,
        evidence_gap_warning=False,
    )


def _tb_btc_short_second_carrier() -> CarrierExpansionCandidate:
    return CarrierExpansionCandidate(
        carrier_id=SECOND_CARRIER_ID,
        strategy_family="TB",
        symbol="BTCUSDT",
        runtime_symbol="BTC/USDT:USDT",
        side="short",
        role="second_carrier_bootstrap",
        regime_fit=(
            "best fit for Owner bearish 1-2 month view; later range regime requires "
            "cooldown and no-chase constraints before any rehearsal"
        ),
        risk_cap_draft=CarrierRiskCapDraft(
            cap_profile_id="TB-BTC-SHORT-budget-foundation-cap-v0",
            per_carrier_cap=Decimal("20"),
            max_trial_attempts=1,
            max_daily_attempts=1,
            max_concurrent_positions=1,
            daily_loss_limit=Decimal("20"),
            leverage=Decimal("1"),
        ),
        protection_feasibility=ProtectionFeasibility(
            protection_plan_type="single_tp_plus_sl",
            feasibility="feasible_pending_testnet_rehearsal",
            required_before_live=[
                "carrier-specific controlled testnet profile",
                "BTC short protection rehearsal",
                "final hard safety preflight",
                "explicit Owner live authorization",
            ],
        ),
        observation_readiness_state="metadata_ready_observation_gap_disclosed",
        testnet_rehearsal_gap_summary=[
            "No TB-BTC-SHORT controlled testnet entry rehearsal is recorded.",
            "No BTC short cleanup-close rehearsal is recorded.",
            "No BTC short runtime profile allowlist is enabled.",
            "No live authorization, ExecutionIntent, or order exists.",
        ],
        api_visibility="/api/brc/strategy-trial-architecture/second-carrier-expansion",
        owner_console_visibility="/trial-confirmation read-only expansion panel",
        budget_foundation_eligible=True,
        evidence_gap_warning=True,
    )


def _vb_sol_short_comparison() -> CarrierExpansionCandidate:
    return _comparison_candidate(
        carrier_id="VB-SOL-SHORT",
        strategy_family="VB",
        symbol="SOLUSDT",
        runtime_symbol="SOL/USDT:USDT",
        side="short",
        regime_fit="possible bearish-volatility comparison; evidence and rehearsal not promoted",
    )


def _cpm_pc_eth_short_comparison() -> CarrierExpansionCandidate:
    return _comparison_candidate(
        carrier_id="CPM-PC-ETH-SHORT",
        strategy_family="CPM/PC",
        symbol="ETHUSDT",
        runtime_symbol="ETH/USDT:USDT",
        side="short",
        regime_fit="possible ETH short pullback/continuation comparison; not selected for budget foundation",
    )


def _mi001_sol_long_comparison() -> CarrierExpansionCandidate:
    return _comparison_candidate(
        carrier_id="MI-001-SOL-LONG",
        strategy_family="MI-001",
        symbol="SOLUSDT",
        runtime_symbol="SOL/USDT:USDT",
        side="long",
        regime_fit="long-only comparison conflicts with near-term bearish owner view; kept for comparison only",
    )


def _comparison_candidate(
    *,
    carrier_id: str,
    strategy_family: str,
    symbol: str,
    runtime_symbol: str,
    side: Literal["long", "short"],
    regime_fit: str,
) -> CarrierExpansionCandidate:
    return CarrierExpansionCandidate(
        carrier_id=carrier_id,
        strategy_family=strategy_family,
        symbol=symbol,
        runtime_symbol=runtime_symbol,
        side=side,
        role="comparison_only",
        regime_fit=regime_fit,
        risk_cap_draft=CarrierRiskCapDraft(
            cap_profile_id=f"{carrier_id}-comparison-cap-v0",
            per_carrier_cap=Decimal("20"),
            max_trial_attempts=1,
            max_daily_attempts=1,
            max_concurrent_positions=1,
            daily_loss_limit=Decimal("20"),
            leverage=Decimal("1"),
        ),
        protection_feasibility=ProtectionFeasibility(
            protection_plan_type="single_tp_plus_sl",
            feasibility="comparison_only_not_ready",
            required_before_live=[
                "promotion out of comparison-only state",
                "carrier-specific controlled testnet rehearsal",
                "explicit Owner live authorization",
            ],
        ),
        observation_readiness_state="comparison_only_not_budget_authorizable",
        testnet_rehearsal_gap_summary=[
            "Comparison metadata only.",
            "No controlled testnet rehearsal is recorded.",
            "No authorization or execution surface is enabled.",
        ],
        api_visibility="/api/brc/strategy-trial-architecture/second-carrier-expansion",
        owner_console_visibility="/trial-confirmation read-only expansion panel",
        budget_foundation_eligible=False,
        evidence_gap_warning=True,
    )


def _non_permissions() -> dict[str, bool]:
    return {
        "live_ready": False,
        "auto_execution_enabled": False,
        "order_permission_granted": False,
        "execution_permission_granted": False,
        "execution_intent_created": False,
        "order_created": False,
        "exchange_write_api_called": False,
        "real_funds_authorized": False,
    }
