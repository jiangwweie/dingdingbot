"""PostgreSQL authority for product, calendar, and corporate-event admission."""

from __future__ import annotations

from hashlib import sha256
import json

import sqlalchemy as sa
from pydantic import JsonValue
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.corporate_events import (
    CorporateEvent,
    CorporateEventCertainty,
    CorporateEventCoverage,
    CorporateEventKind,
)
from src.trading_kernel.domain.product_admission import (
    ProductAdmissionAuthority,
    ProductAdmissionPolicy,
    ProductProfile,
    SessionLiquidityThreshold,
)
from src.trading_kernel.domain.us_equity_session import (
    USMarketCalendar,
    USMarketCalendarSession,
    USSessionCode,
)
from src.trading_kernel.infrastructure.pg_models import (
    corporate_event_coverage,
    corporate_event_versions,
    instrument_product_current,
    instrument_product_profiles,
    market_calendar_sessions,
    market_calendar_versions,
    product_admission_policies,
)


class PostgresProductAdmissionRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def seed_calendar(
        self,
        calendar: USMarketCalendar,
        *,
        source_name: str,
        created_at_ms: int,
    ) -> bool:
        result = await self._connection.execute(
            pg_insert(market_calendar_versions)
            .values(
                calendar_version_id=calendar.calendar_version_id,
                calendar_version=1,
                source_name=source_name,
                timezone_name=calendar.timezone_name,
                horizon_start_date=calendar.horizon_start_date,
                horizon_end_date=calendar.horizon_end_date,
                semantic_digest=calendar.semantic_digest,
                status="active",
                created_at_ms=created_at_ms,
            )
            .on_conflict_do_nothing(
                index_elements=[market_calendar_versions.c.calendar_version_id]
            )
        )
        if result.rowcount != 1:
            existing = await self._load_calendar(calendar.calendar_version_id)
            if existing != calendar:
                raise ValueError("calendar seed identity conflict")
            return False
        await self._connection.execute(
            sa.insert(market_calendar_sessions),
            [
                {
                    "calendar_version_id": calendar.calendar_version_id,
                    **session.model_dump(mode="python"),
                }
                for session in calendar.sessions
            ],
        )
        return True

    async def seed_policy(
        self,
        policy: ProductAdmissionPolicy,
        *,
        created_at_ms: int,
    ) -> bool:
        threshold_payload = {
            "market_fact_max_age_ms": policy.market_fact_max_age_ms,
            "funding_max_age_ms": policy.funding_max_age_ms,
            "thresholds": [
                item.model_dump(mode="json") for item in policy.thresholds
            ],
        }
        semantic_digest = _digest(
            {
                "product_policy_version_id": policy.product_policy_version_id,
                "configured_leverage": policy.configured_leverage,
                **threshold_payload,
            }
        )
        result = await self._connection.execute(
            pg_insert(product_admission_policies)
            .values(
                product_policy_version_id=policy.product_policy_version_id,
                policy_version=1,
                asset_class="us_equity",
                session_thresholds=threshold_payload,
                earnings_policy={
                    "pre_release_hours": 4,
                    "post_release_closed_15m_bars": 2,
                    "date_only_full_day": True,
                },
                configured_leverage=policy.configured_leverage,
                semantic_digest=semantic_digest,
                status="active",
                created_at_ms=created_at_ms,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    product_admission_policies.c.product_policy_version_id
                ]
            )
        )
        return result.rowcount == 1

    async def upsert_product_profile(
        self,
        profile: ProductProfile,
        *,
        source_payload: dict[str, JsonValue],
        updated_at_ms: int,
    ) -> bool:
        result = await self._connection.execute(
            pg_insert(instrument_product_profiles)
            .values(
                product_profile_id=profile.product_profile_id,
                exchange_instrument_id=profile.exchange_instrument_id,
                profile_version=profile.profile_version,
                venue_id=profile.venue_id,
                contract_type=profile.contract_type,
                underlying_type=profile.underlying_type,
                margin_asset=profile.margin_asset,
                product_status=profile.product_status,
                configured_leverage=profile.configured_leverage,
                margin_mode=profile.margin_mode,
                source_payload=source_payload,
                semantic_digest=profile.semantic_digest,
                observed_at_ms=profile.observed_at_ms,
                valid_until_ms=profile.valid_until_ms,
                created_at_ms=updated_at_ms,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    instrument_product_profiles.c.product_profile_id
                ]
            )
        )
        if result.rowcount != 1:
            existing = await self._load_profile(profile.exchange_instrument_id)
            if existing != profile:
                raise ValueError("product profile identity conflict")
            return False
        await self._connection.execute(
            pg_insert(instrument_product_current)
            .values(
                exchange_instrument_id=profile.exchange_instrument_id,
                product_profile_id=profile.product_profile_id,
                updated_at_ms=updated_at_ms,
            )
            .on_conflict_do_update(
                index_elements=[
                    instrument_product_current.c.exchange_instrument_id
                ],
                set_={
                    "product_profile_id": profile.product_profile_id,
                    "updated_at_ms": updated_at_ms,
                },
            )
        )
        return True

    async def replace_corporate_event_authority(
        self,
        *,
        coverage: CorporateEventCoverage,
        events: tuple[CorporateEvent, ...],
        source_name: str,
        observed_at_ms: int,
    ) -> None:
        if any(
            event.exchange_instrument_id != coverage.exchange_instrument_id
            for event in events
        ):
            raise ValueError("corporate events differ from coverage instrument")
        for event in events:
            await self._connection.execute(
                pg_insert(corporate_event_versions)
                .values(
                    corporate_event_version_id=event.corporate_event_version_id,
                    exchange_instrument_id=event.exchange_instrument_id,
                    source_event_id=event.corporate_event_version_id,
                    event_kind=event.event_kind.value,
                    certainty=event.certainty.value,
                    event_date=event.event_date,
                    effective_at_ms=event.effective_at_ms,
                    payload_digest=_digest(event.model_dump(mode="json")),
                    status=event.status,
                    observed_at_ms=observed_at_ms,
                    valid_until_ms=coverage.valid_until_ms,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        corporate_event_versions.c.corporate_event_version_id
                    ]
                )
            )
        await self._connection.execute(
            pg_insert(corporate_event_coverage)
            .values(
                coverage_id=coverage.coverage_id,
                exchange_instrument_id=coverage.exchange_instrument_id,
                source_name=source_name,
                coverage_start_ms=coverage.coverage_start_ms,
                coverage_end_ms=coverage.coverage_end_ms,
                coverage_status=coverage.coverage_status,
                coverage_digest=coverage.coverage_digest,
                observed_at_ms=observed_at_ms,
                valid_until_ms=coverage.valid_until_ms,
            )
            .on_conflict_do_nothing(
                index_elements=[corporate_event_coverage.c.coverage_id]
            )
        )

    async def load_current_authority(
        self,
        exchange_instrument_id: str,
    ) -> ProductAdmissionAuthority | None:
        profile = await self._load_profile(exchange_instrument_id)
        calendar_row = (
            await self._connection.execute(
                sa.select(market_calendar_versions.c.calendar_version_id)
                .where(market_calendar_versions.c.status == "active")
                .order_by(market_calendar_versions.c.calendar_version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        policy_row = (
            await self._connection.execute(
                sa.select(product_admission_policies)
                .where(
                    product_admission_policies.c.asset_class == "us_equity",
                    product_admission_policies.c.status == "active",
                )
                .order_by(product_admission_policies.c.policy_version.desc())
                .limit(1)
            )
        ).mappings().one_or_none()
        if profile is None or calendar_row is None or policy_row is None:
            return None
        coverage_row = (
            await self._connection.execute(
                sa.select(corporate_event_coverage)
                .where(
                    corporate_event_coverage.c.exchange_instrument_id
                    == exchange_instrument_id
                )
                .order_by(
                    corporate_event_coverage.c.observed_at_ms.desc(),
                    corporate_event_coverage.c.coverage_id.desc(),
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        event_rows = (
            await self._connection.execute(
                sa.select(corporate_event_versions)
                .where(
                    corporate_event_versions.c.exchange_instrument_id
                    == exchange_instrument_id,
                    corporate_event_versions.c.status == "active",
                )
                .order_by(
                    corporate_event_versions.c.event_date,
                    corporate_event_versions.c.corporate_event_version_id,
                )
            )
        ).mappings().all()
        thresholds_payload = dict(policy_row["session_thresholds"])
        return ProductAdmissionAuthority(
            profile=profile,
            calendar=await self._load_calendar(str(calendar_row)),
            coverage=(
                None
                if coverage_row is None
                else CorporateEventCoverage(
                    coverage_id=str(coverage_row["coverage_id"]),
                    exchange_instrument_id=str(
                        coverage_row["exchange_instrument_id"]
                    ),
                    coverage_start_ms=int(coverage_row["coverage_start_ms"]),
                    coverage_end_ms=int(coverage_row["coverage_end_ms"]),
                    coverage_status=str(coverage_row["coverage_status"]),
                    valid_until_ms=int(coverage_row["valid_until_ms"]),
                    coverage_digest=str(coverage_row["coverage_digest"]),
                )
            ),
            events=tuple(_corporate_event(row) for row in event_rows),
            policy=ProductAdmissionPolicy(
                product_policy_version_id=str(
                    policy_row["product_policy_version_id"]
                ),
                configured_leverage=int(policy_row["configured_leverage"]),
                market_fact_max_age_ms=int(
                    thresholds_payload["market_fact_max_age_ms"]
                ),
                funding_max_age_ms=int(
                    thresholds_payload["funding_max_age_ms"]
                ),
                thresholds=tuple(
                    SessionLiquidityThreshold(
                        session_code=USSessionCode(item["session_code"]),
                        max_spread_bps=item["max_spread_bps"],
                        max_mark_index_deviation_bps=item[
                            "max_mark_index_deviation_bps"
                        ],
                        minimum_top5_depth_ratio=item[
                            "minimum_top5_depth_ratio"
                        ],
                    )
                    for item in thresholds_payload["thresholds"]
                ),
            ),
        )

    async def _load_calendar(self, calendar_version_id: str) -> USMarketCalendar:
        row = (
            await self._connection.execute(
                sa.select(market_calendar_versions).where(
                    market_calendar_versions.c.calendar_version_id
                    == calendar_version_id
                )
            )
        ).mappings().one()
        sessions = (
            await self._connection.execute(
                sa.select(market_calendar_sessions)
                .where(
                    market_calendar_sessions.c.calendar_version_id
                    == calendar_version_id
                )
                .order_by(market_calendar_sessions.c.session_date)
            )
        ).mappings().all()
        return USMarketCalendar(
            calendar_version_id=calendar_version_id,
            timezone_name=str(row["timezone_name"]),
            horizon_start_date=row["horizon_start_date"],
            horizon_end_date=row["horizon_end_date"],
            semantic_digest=str(row["semantic_digest"]),
            sessions=tuple(
                USMarketCalendarSession(
                    session_date=item["session_date"],
                    holiday=bool(item["holiday"]),
                    regular_open_at_ms=(
                        None
                        if item["regular_open_at_ms"] is None
                        else int(item["regular_open_at_ms"])
                    ),
                    regular_close_at_ms=(
                        None
                        if item["regular_close_at_ms"] is None
                        else int(item["regular_close_at_ms"])
                    ),
                    early_close=bool(item["early_close"]),
                    source_ref=str(item["source_ref"]),
                )
                for item in sessions
            ),
        )

    async def _load_profile(
        self,
        exchange_instrument_id: str,
    ) -> ProductProfile | None:
        row = (
            await self._connection.execute(
                sa.select(instrument_product_profiles)
                .join(
                    instrument_product_current,
                    instrument_product_current.c.product_profile_id
                    == instrument_product_profiles.c.product_profile_id,
                )
                .where(
                    instrument_product_current.c.exchange_instrument_id
                    == exchange_instrument_id
                )
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        return ProductProfile(
            product_profile_id=str(row["product_profile_id"]),
            profile_version=int(row["profile_version"]),
            exchange_instrument_id=str(row["exchange_instrument_id"]),
            venue_id=str(row["venue_id"]),
            contract_type=str(row["contract_type"]),
            underlying_type=str(row["underlying_type"]),
            margin_asset=str(row["margin_asset"]),
            product_status=str(row["product_status"]),
            configured_leverage=int(row["configured_leverage"]),
            margin_mode=str(row["margin_mode"]),
            observed_at_ms=int(row["observed_at_ms"]),
            valid_until_ms=int(row["valid_until_ms"]),
            semantic_digest=str(row["semantic_digest"]),
        )


def _corporate_event(row) -> CorporateEvent:
    return CorporateEvent(
        corporate_event_version_id=str(row["corporate_event_version_id"]),
        exchange_instrument_id=str(row["exchange_instrument_id"]),
        event_kind=CorporateEventKind(str(row["event_kind"])),
        certainty=CorporateEventCertainty(str(row["certainty"])),
        event_date=row["event_date"],
        effective_at_ms=(
            None if row["effective_at_ms"] is None else int(row["effective_at_ms"])
        ),
        status=str(row["status"]),
    )


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"
