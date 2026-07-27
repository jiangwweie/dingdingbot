"""Action-time product, session, basis, and depth admission."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
import json

from pydantic import BaseModel, ConfigDict, model_validator

from src.trading_kernel.domain.corporate_events import (
    CorporateEvent,
    CorporateEventAdmission,
    CorporateEventCoverage,
)
from src.trading_kernel.domain.us_equity_session import (
    USMarketCalendar,
    USSessionClassification,
    USSessionCode,
    classify_us_equity_session,
)


class ProductProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    product_profile_id: str
    profile_version: int = 1
    exchange_instrument_id: str
    venue_id: str
    contract_type: str
    underlying_type: str
    margin_asset: str
    product_status: str
    configured_leverage: int
    margin_mode: str
    observed_at_ms: int
    valid_until_ms: int
    semantic_digest: str

    @model_validator(mode="after")
    def _validate_profile(self) -> "ProductProfile":
        if (
            self.profile_version <= 0
            or self.configured_leverage <= 0
            or self.observed_at_ms <= 0
            or self.valid_until_ms <= self.observed_at_ms
        ):
            raise ValueError("product profile validity is invalid")
        return self


class ProductMarketFacts(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    exchange_instrument_id: str
    best_bid: Decimal
    best_ask: Decimal
    mark_price: Decimal
    index_price: Decimal
    top5_bid_depth: Decimal
    top5_ask_depth: Decimal
    funding_rate: Decimal
    funding_observed_at_ms: int
    observed_at_ms: int

    @model_validator(mode="after")
    def _validate_facts(self) -> "ProductMarketFacts":
        if (
            min(
                self.best_bid,
                self.best_ask,
                self.mark_price,
                self.index_price,
            )
            <= 0
            or self.best_ask <= self.best_bid
            or self.top5_bid_depth < 0
            or self.top5_ask_depth < 0
            or self.funding_observed_at_ms <= 0
            or self.observed_at_ms <= 0
        ):
            raise ValueError("product market facts are invalid")
        return self


class SessionLiquidityThreshold(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_code: USSessionCode
    max_spread_bps: Decimal
    max_mark_index_deviation_bps: Decimal
    minimum_top5_depth_ratio: Decimal


class ProductAdmissionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    product_policy_version_id: str
    configured_leverage: int
    market_fact_max_age_ms: int
    funding_max_age_ms: int
    thresholds: tuple[SessionLiquidityThreshold, ...]

    def threshold(
        self,
        session_code: USSessionCode,
    ) -> SessionLiquidityThreshold | None:
        for threshold in self.thresholds:
            if threshold.session_code is session_code:
                return threshold
        return None

    @classmethod
    def initial_us_equity_policy(cls) -> "ProductAdmissionPolicy":
        values = (
            (USSessionCode.REGULAR, "25", "50"),
            (USSessionCode.PREMARKET, "50", "75"),
            (USSessionCode.AFTERHOURS, "50", "75"),
            (USSessionCode.OVERNIGHT, "75", "100"),
            (USSessionCode.WEEKEND_HOLIDAY, "100", "150"),
        )
        return cls(
            product_policy_version_id="product-policy:us-equity:v1",
            configured_leverage=5,
            market_fact_max_age_ms=60_000,
            funding_max_age_ms=900_000,
            thresholds=tuple(
                SessionLiquidityThreshold(
                    session_code=session_code,
                    max_spread_bps=Decimal(spread),
                    max_mark_index_deviation_bps=Decimal(deviation),
                    minimum_top5_depth_ratio=Decimal("5"),
                )
                for session_code, spread, deviation in values
            ),
        )


class ProductAdmissionDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    reason_code: str
    session_code: str
    session_multiplier: Decimal
    spread_bps: Decimal | None
    mark_index_deviation_bps: Decimal | None
    top5_depth_ratio: Decimal | None
    product_admission_digest: str


class ProductAdmissionContext(BaseModel):
    """All versioned action-time authority needed for one US product decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: ProductProfile
    market_facts: ProductMarketFacts
    calendar: USMarketCalendar
    corporate_event_admission: CorporateEventAdmission
    policy: ProductAdmissionPolicy

    def classify(self, *, action_time_ms: int) -> USSessionClassification:
        return classify_us_equity_session(
            calendar=self.calendar,
            action_time_ms=action_time_ms,
        )


class ProductAdmissionAuthority(BaseModel):
    """Database-backed current authority before adding live market facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: ProductProfile
    calendar: USMarketCalendar
    coverage: CorporateEventCoverage | None
    events: tuple[CorporateEvent, ...]
    policy: ProductAdmissionPolicy


def evaluate_product_admission(
    *,
    action_time_ms: int,
    order_notional: Decimal,
    profile: ProductProfile,
    market_facts: ProductMarketFacts,
    calendar: USMarketCalendar,
    corporate_event_admission: CorporateEventAdmission,
    policy: ProductAdmissionPolicy,
) -> ProductAdmissionDecision:
    if action_time_ms <= 0 or order_notional <= 0:
        raise ValueError("product admission action time/notional is invalid")
    session = classify_us_equity_session(
        calendar=calendar,
        action_time_ms=action_time_ms,
    )
    base = {
        "action_time_ms": action_time_ms,
        "calendar_version_id": calendar.calendar_version_id,
        "calendar_digest": calendar.semantic_digest,
        "exchange_instrument_id": profile.exchange_instrument_id,
        "product_profile_id": profile.product_profile_id,
        "product_profile_digest": profile.semantic_digest,
        "product_policy_version_id": policy.product_policy_version_id,
        "session_code": session.session_code.value,
        "session_multiplier": str(session.stop_risk_multiplier),
    }
    if (
        profile.exchange_instrument_id != market_facts.exchange_instrument_id
        or profile.venue_id != "binance-usdm"
        or profile.contract_type != "TRADIFI_PERPETUAL"
        or profile.underlying_type != "EQUITY"
        or profile.margin_asset != "USDT"
        or profile.product_status != "TRADING"
        or profile.configured_leverage != policy.configured_leverage
        or profile.configured_leverage != 5
        or profile.margin_mode != "cross"
    ):
        return _decision(
            base,
            session=session,
            reason="product_identity_ineligible",
        )
    if (
        action_time_ms < profile.observed_at_ms
        or action_time_ms >= profile.valid_until_ms
        or action_time_ms < market_facts.observed_at_ms
        or action_time_ms - market_facts.observed_at_ms
        > policy.market_fact_max_age_ms
        or action_time_ms < market_facts.funding_observed_at_ms
        or action_time_ms - market_facts.funding_observed_at_ms
        > policy.funding_max_age_ms
    ):
        return _decision(
            base,
            session=session,
            reason="product_facts_stale",
        )
    if session.session_code is USSessionCode.UNKNOWN:
        return _decision(base, session=session, reason="session_unknown")
    if not corporate_event_admission.allowed:
        return _decision(
            base,
            session=session,
            reason=corporate_event_admission.reason_code,
        )
    threshold = policy.threshold(session.session_code)
    if threshold is None:
        return _decision(base, session=session, reason="session_policy_missing")
    midpoint = (market_facts.best_bid + market_facts.best_ask) / Decimal("2")
    spread_bps = (
        (market_facts.best_ask - market_facts.best_bid)
        / midpoint
        * Decimal("10000")
    )
    deviation_bps = (
        abs(market_facts.mark_price - market_facts.index_price)
        / market_facts.index_price
        * Decimal("10000")
    )
    depth_ratio = min(
        market_facts.top5_bid_depth,
        market_facts.top5_ask_depth,
    ) / order_notional
    metrics = {
        **base,
        "spread_bps": str(spread_bps),
        "mark_index_deviation_bps": str(deviation_bps),
        "top5_depth_ratio": str(depth_ratio),
    }
    if spread_bps > threshold.max_spread_bps:
        return _decision(
            metrics,
            session=session,
            reason="spread_limit_exceeded",
            spread_bps=spread_bps,
            deviation_bps=deviation_bps,
            depth_ratio=depth_ratio,
        )
    if deviation_bps > threshold.max_mark_index_deviation_bps:
        return _decision(
            metrics,
            session=session,
            reason="mark_index_deviation_exceeded",
            spread_bps=spread_bps,
            deviation_bps=deviation_bps,
            depth_ratio=depth_ratio,
        )
    if depth_ratio < threshold.minimum_top5_depth_ratio:
        return _decision(
            metrics,
            session=session,
            reason="top5_depth_insufficient",
            spread_bps=spread_bps,
            deviation_bps=deviation_bps,
            depth_ratio=depth_ratio,
        )
    return _decision(
        metrics,
        session=session,
        reason="product_admission_passed",
        allowed=True,
        spread_bps=spread_bps,
        deviation_bps=deviation_bps,
        depth_ratio=depth_ratio,
    )


def _decision(
    payload: dict[str, object],
    *,
    session: USSessionClassification,
    reason: str,
    allowed: bool = False,
    spread_bps: Decimal | None = None,
    deviation_bps: Decimal | None = None,
    depth_ratio: Decimal | None = None,
) -> ProductAdmissionDecision:
    session_code = session.session_code
    multiplier = session.stop_risk_multiplier
    digest_payload = {
        **payload,
        "allowed": allowed,
        "reason": reason,
    }
    digest = f"sha256:{sha256(json.dumps(digest_payload, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()}"
    return ProductAdmissionDecision(
        allowed=allowed,
        reason_code=reason,
        session_code=session_code.value,
        session_multiplier=multiplier,
        spread_bps=spread_bps,
        mark_index_deviation_bps=deviation_bps,
        top5_depth_ratio=depth_ratio,
        product_admission_digest=digest,
    )
