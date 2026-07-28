"""PostgreSQL persistence for immutable, unordered StrategyUniverses."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, cast

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationReadiness,
    UniverseActivationRequest,
    UniverseActivationResult,
    UniverseActivationStatus,
    activation_readiness_blocker,
)
from src.trading_kernel.application.install_strategy_universe import (
    UniverseCurrent,
    UniverseInstallPolicyScope,
    UniverseInstallRequest,
    UniverseInstallResult,
    UniverseInstallStatus,
)
from src.trading_kernel.application.ports import InstrumentCertificationTarget
from src.trading_kernel.application.project_comparative_universe import (
    ComparativeProjectionFailure,
    ComparativeProjectionOutcome,
    ComparativeUniverseProjection,
    comparative_member_set_digest,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.instrument_certification import (
    InstrumentCertification,
)
from src.trading_kernel.domain.instrument_identity import (
    parse_binance_usdm_instrument_id,
)
from src.trading_kernel.domain.strategy_universe import (
    MAX_UNIVERSE_MEMBERS,
    StrategyUniverseVersion,
    build_strategy_universe,
)
from src.trading_kernel.infrastructure.pg_models import (
    comparative_projection_current,
    event_specs,
    instrument_certification_current,
    instruments,
    owner_policy_current,
    runtime_profiles,
    runtime_scopes_current,
    strategy_groups,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    strategy_versions,
)

_INSTALL_LOCK_KEY = "brc-strategy-universe-install"


class UniverseInstallConflict(RuntimeError):
    """Persisted authority conflicts with a requested immutable install."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class _InstallAuthority:
    strategy_group_id: str
    strategy_version_id: str
    position_side: Literal["long", "short"]


class PostgresStrategyUniverseRepository:
    """Own version/member/current persistence; certification remains elsewhere."""

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def install(
        self,
        request: UniverseInstallRequest,
    ) -> UniverseInstallResult:
        await self._lock_installs()
        authority = await self._load_authority(request)
        requested = build_strategy_universe(
            universe_version_id="universe:pending",
            strategy_group_id=authority.strategy_group_id,
            event_spec_id=request.event_spec_id,
            universe_version=1,
            exchange_instrument_ids=request.exchange_instrument_ids,
            installed_at_ms=request.installed_at_ms,
        )
        existing = await self._get_current_semantic_version(
            event_spec_id=request.event_spec_id,
            semantic_digest=requested.semantic_digest,
        )
        if existing is not None:
            await self._assert_existing_scopes(
                existing,
                request=request,
                authority=authority,
            )
            lifecycle_state = cast(
                Literal["warming", "active"],
                existing["lifecycle_state"],
            )
            return _result(
                status=(
                    UniverseInstallStatus.ALREADY_ACTIVE
                    if lifecycle_state == "active"
                    else UniverseInstallStatus.ALREADY_WARMING
                ),
                universe=await self._universe_from_row(existing),
                lifecycle_state=lifecycle_state,
            )

        if await self._warming_exists():
            return _result(
                status=UniverseInstallStatus.WARMING_UNIVERSE_ALREADY_EXISTS,
                universe=None,
                lifecycle_state=None,
            )

        universe_version = await self._next_version(request.event_spec_id)
        universe = build_strategy_universe(
            universe_version_id=_universe_version_id(
                request.event_spec_id,
                universe_version,
            ),
            strategy_group_id=authority.strategy_group_id,
            event_spec_id=request.event_spec_id,
            universe_version=universe_version,
            exchange_instrument_ids=request.exchange_instrument_ids,
            installed_at_ms=request.installed_at_ms,
        )
        inserted_instruments = await self._install_instruments(universe)
        await self._connection.execute(
            sa.insert(strategy_universe_versions).values(
                universe_version_id=universe.universe_version_id,
                strategy_group_id=universe.strategy_group_id,
                event_spec_id=universe.event_spec_id,
                universe_version=universe.universe_version,
                semantic_digest=universe.semantic_digest,
                lifecycle_state="warming",
                installed_at_ms=universe.installed_at_ms,
                activated_at_ms=None,
                retired_at_ms=None,
            )
        )
        await self._connection.execute(
            sa.insert(strategy_universe_members),
            [
                {
                    "universe_version_id": universe.universe_version_id,
                    "exchange_instrument_id": exchange_instrument_id,
                }
                for exchange_instrument_id in universe.exchange_instrument_ids
            ],
        )
        await self._connection.execute(
            sa.insert(runtime_scopes_current),
            [
                _warming_scope_values(
                    universe=universe,
                    authority=authority,
                    request=request,
                    exchange_instrument_id=exchange_instrument_id,
                )
                for exchange_instrument_id in universe.exchange_instrument_ids
            ],
        )
        return _result(
            status=UniverseInstallStatus.INSTALLED,
            universe=universe,
            lifecycle_state="warming",
            inserted_instrument_count=inserted_instruments,
            inserted_version_count=1,
            inserted_member_count=len(universe.exchange_instrument_ids),
            inserted_scope_count=len(universe.exchange_instrument_ids),
        )

    async def get_current(
        self,
        event_spec_id: str,
    ) -> UniverseCurrent | None:
        row = (
            await self._connection.execute(
                sa.select(
                    strategy_universe_current.c.event_spec_id,
                    strategy_universe_current.c.universe_version_id,
                    strategy_universe_current.c.semantic_digest,
                    strategy_universe_current.c.activation_generation,
                    strategy_universe_current.c.activated_at_ms,
                )
                .where(strategy_universe_current.c.event_spec_id == event_spec_id)
                .limit(1)
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        return UniverseCurrent(
            event_spec_id=str(row["event_spec_id"]),
            universe_version_id=str(row["universe_version_id"]),
            semantic_digest=str(row["semantic_digest"]),
            activation_generation=int(row["activation_generation"]),
            activated_at_ms=int(row["activated_at_ms"]),
        )

    async def get_members(
        self,
        universe_version_id: str,
    ) -> tuple[str, ...]:
        rows = (
            await self._connection.execute(
                sa.select(strategy_universe_members.c.exchange_instrument_id)
                .where(
                    strategy_universe_members.c.universe_version_id
                    == universe_version_id
                )
                .order_by(strategy_universe_members.c.exchange_instrument_id)
                .limit(MAX_UNIVERSE_MEMBERS + 1)
            )
        ).all()
        if len(rows) > MAX_UNIVERSE_MEMBERS:
            raise UniverseInstallConflict("UNIVERSE_MEMBER_CARDINALITY_CONFLICT")
        return tuple(str(row[0]) for row in rows)

    async def try_activate(
        self,
        request: UniverseActivationRequest,
    ) -> UniverseActivationResult:
        target = (
            await self._connection.execute(
                sa.select(strategy_universe_versions)
                .where(
                    strategy_universe_versions.c.universe_version_id
                    == request.universe_version_id
                )
                .with_for_update(of=strategy_universe_versions)
                .limit(1)
            )
        ).mappings().one_or_none()
        if target is None:
            raise UniverseInstallConflict("UNIVERSE_ACTIVATION_TARGET_NOT_FOUND")

        event_spec_id = str(target["event_spec_id"])
        current = (
            await self._connection.execute(
                sa.select(strategy_universe_current)
                .where(
                    strategy_universe_current.c.event_spec_id
                    == event_spec_id
                )
                .with_for_update(of=strategy_universe_current)
                .limit(1)
            )
        ).mappings().one_or_none()
        if target["lifecycle_state"] == "active":
            if (
                current is None
                or current["universe_version_id"]
                != request.universe_version_id
                or current["semantic_digest"] != target["semantic_digest"]
            ):
                raise UniverseInstallConflict(
                    "CURRENT_UNIVERSE_IDENTITY_CONFLICT"
                )
            return UniverseActivationResult(
                status=UniverseActivationStatus.ALREADY_ACTIVE,
                reason_code=None,
                event_spec_id=event_spec_id,
                universe_version_id=request.universe_version_id,
                previous_universe_version_id=None,
                activation_generation=int(
                    current["activation_generation"]
                ),
                activated_at_ms=int(current["activated_at_ms"]),
            )
        current_is_complete = (
            current is None
            or await self._current_universe_identity_is_complete(current)
        )
        event = (
            await self._connection.execute(
                sa.select(
                    event_specs.c.event_id,
                    event_specs.c.timeframe,
                    event_specs.c.status,
                )
                .where(
                    event_specs.c.event_spec_id == event_spec_id
                )
                .with_for_update(of=event_specs)
                .limit(1)
            )
        ).mappings().one_or_none()
        event_is_active = not (
            event is None
            or event["status"] != "active"
            or event["timeframe"] not in {"15m", "1h"}
        )
        readiness = await self._activation_readiness(
            target=target,
            attempted_at_ms=request.attempted_at_ms,
            current_is_complete=current_is_complete,
            event_is_active=event_is_active,
            comparative_event=(
                event is not None
                and event["event_id"] in {"MPG-LONG", "MI-LONG"}
            ),
        )
        readiness_blocker = activation_readiness_blocker(readiness)
        if readiness_blocker is not None:
            return _not_ready_activation(
                target=target,
                current=current,
                reason_code=readiness_blocker,
            )
        if event is None:
            raise UniverseInstallConflict("EVENT_AUTHORITY_CONFLICT")

        previous_universe_version_id = (
            None
            if current is None
            else str(current["universe_version_id"])
        )
        interval_ms = (
            900_000 if event["timeframe"] == "15m" else 3_600_000
        )
        next_observation_due_at_ms = (
            request.attempted_at_ms
            - (request.attempted_at_ms % interval_ms)
            + interval_ms
        )
        if previous_universe_version_id is not None:
            await self._connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.universe_version_id
                    == previous_universe_version_id
                )
                .values(
                    lifecycle_state="retired",
                    observation_enabled=False,
                    entry_enabled=False,
                    scope_version=runtime_scopes_current.c.scope_version + 1,
                    next_observation_due_at_ms=None,
                    lease_owner=None,
                    lease_expires_at_ms=None,
                    observation_generation=(
                        runtime_scopes_current.c.observation_generation + 1
                    ),
                    updated_at_ms=request.attempted_at_ms,
                )
            )
        await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.universe_version_id
                == request.universe_version_id
            )
            .values(
                lifecycle_state="active",
                observation_enabled=True,
                entry_enabled=True,
                scope_version=runtime_scopes_current.c.scope_version + 1,
                next_observation_due_at_ms=next_observation_due_at_ms,
                lease_owner=None,
                lease_expires_at_ms=None,
                observation_generation=(
                    runtime_scopes_current.c.observation_generation + 1
                ),
                updated_at_ms=request.attempted_at_ms,
            )
        )
        if previous_universe_version_id is not None:
            await self._connection.execute(
                sa.update(strategy_universe_versions)
                .where(
                    strategy_universe_versions.c.universe_version_id
                    == previous_universe_version_id
                )
                .values(
                    lifecycle_state="retired",
                    retired_at_ms=request.attempted_at_ms,
                )
            )
        await self._connection.execute(
            sa.update(strategy_universe_versions)
            .where(
                strategy_universe_versions.c.universe_version_id
                == request.universe_version_id
            )
            .values(
                lifecycle_state="active",
                activated_at_ms=request.attempted_at_ms,
            )
        )
        if current is None:
            generation = 1
            await self._connection.execute(
                sa.insert(strategy_universe_current).values(
                    event_spec_id=event_spec_id,
                    universe_version_id=request.universe_version_id,
                    semantic_digest=target["semantic_digest"],
                    lifecycle_state="active",
                    activation_generation=generation,
                    activated_at_ms=request.attempted_at_ms,
                )
            )
        else:
            generation = int(current["activation_generation"]) + 1
            pointer = await self._connection.execute(
                sa.update(strategy_universe_current)
                .where(
                    strategy_universe_current.c.event_spec_id
                    == event_spec_id,
                    strategy_universe_current.c.universe_version_id
                    == previous_universe_version_id,
                    strategy_universe_current.c.activation_generation
                    == current["activation_generation"],
                )
                .values(
                    universe_version_id=request.universe_version_id,
                    semantic_digest=target["semantic_digest"],
                    activation_generation=generation,
                    activated_at_ms=request.attempted_at_ms,
                )
            )
            if pointer.rowcount != 1:
                raise UniverseInstallConflict(
                    "CURRENT_UNIVERSE_GENERATION_CONFLICT"
                )
        return UniverseActivationResult(
            status=UniverseActivationStatus.ACTIVATED,
            reason_code=None,
            event_spec_id=event_spec_id,
            universe_version_id=request.universe_version_id,
            previous_universe_version_id=previous_universe_version_id,
            activation_generation=generation,
            activated_at_ms=request.attempted_at_ms,
        )

    async def _current_universe_identity_is_complete(
        self,
        current: RowMapping,
    ) -> bool:
        universe_version_id = str(current["universe_version_id"])
        version = (
            await self._connection.execute(
                sa.select(strategy_universe_versions)
                .where(
                    strategy_universe_versions.c.universe_version_id
                    == universe_version_id
                )
                .with_for_update(of=strategy_universe_versions)
                .limit(1)
            )
        ).mappings().one_or_none()
        if (
            version is None
            or version["event_spec_id"] != current["event_spec_id"]
            or version["semantic_digest"] != current["semantic_digest"]
            or version["lifecycle_state"] != "active"
        ):
            return False
        members = tuple(
            str(row[0])
            for row in (
                await self._connection.execute(
                    sa.select(
                        strategy_universe_members.c.exchange_instrument_id
                    )
                    .where(
                        strategy_universe_members.c.universe_version_id
                        == universe_version_id
                    )
                    .order_by(
                        strategy_universe_members.c.exchange_instrument_id
                    )
                    .limit(MAX_UNIVERSE_MEMBERS + 1)
                )
            ).all()
        )
        scopes = (
            await self._connection.execute(
                sa.select(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.universe_version_id
                    == universe_version_id
                )
                .order_by(
                    runtime_scopes_current.c.exchange_instrument_id
                )
                .with_for_update(of=runtime_scopes_current)
                .limit(MAX_UNIVERSE_MEMBERS + 1)
            )
        ).mappings().all()
        return (
            1 <= len(members) <= MAX_UNIVERSE_MEMBERS
            and len(scopes) == len(members)
            and tuple(
                str(scope["exchange_instrument_id"])
                for scope in scopes
            )
            == members
            and all(
                scope["event_spec_id"] == current["event_spec_id"]
                and scope["universe_semantic_digest"]
                == current["semantic_digest"]
                and scope["lifecycle_state"] == "active"
                and scope["observation_enabled"]
                and scope["entry_enabled"]
                for scope in scopes
            )
        )

    async def _activation_readiness(
        self,
        *,
        target: RowMapping,
        attempted_at_ms: int,
        current_is_complete: bool,
        event_is_active: bool,
        comparative_event: bool,
    ) -> UniverseActivationReadiness:
        universe_version_id = str(target["universe_version_id"])
        members = tuple(
            str(row[0])
            for row in (
                await self._connection.execute(
                    sa.select(
                        strategy_universe_members.c.exchange_instrument_id
                    )
                    .where(
                        strategy_universe_members.c.universe_version_id
                        == universe_version_id
                    )
                    .order_by(
                        strategy_universe_members.c.exchange_instrument_id
                    )
                    .limit(MAX_UNIVERSE_MEMBERS + 1)
                )
            ).all()
        )
        members_are_complete = (
            1 <= len(members) <= MAX_UNIVERSE_MEMBERS
            and members == tuple(sorted(set(members)))
        )
        scopes = (
            await self._connection.execute(
                sa.select(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.universe_version_id
                    == universe_version_id
                )
                .order_by(
                    runtime_scopes_current.c.exchange_instrument_id
                )
                .with_for_update(of=runtime_scopes_current)
                .limit(MAX_UNIVERSE_MEMBERS + 1)
            )
        ).mappings().all()
        scopes_are_complete = (
            members_are_complete
            and len(scopes) == len(members)
            and tuple(
                str(scope["exchange_instrument_id"])
                for scope in scopes
            )
            == members
            and all(
                scope["event_spec_id"] == target["event_spec_id"]
                and scope["universe_semantic_digest"]
                == target["semantic_digest"]
                and scope["lifecycle_state"] == "warming"
                and scope["observation_enabled"]
                and not scope["entry_enabled"]
                for scope in scopes
            )
        )

        instrument_rows = (
            await self._connection.execute(
                sa.select(
                    instruments.c.exchange_instrument_id,
                    instruments.c.status,
                )
                .where(
                    instruments.c.exchange_instrument_id.in_(members)
                )
                .with_for_update(of=instruments)
                .limit(MAX_UNIVERSE_MEMBERS + 1)
            )
        ).mappings().all()
        instrument_statuses = {
            str(row["exchange_instrument_id"]): str(row["status"])
            for row in instrument_rows
        }
        certification_keys = tuple(
            (
                str(scope["runtime_profile_id"]),
                str(scope["exchange_instrument_id"]),
            )
            for scope in scopes
        )
        certifications = (
            await self._connection.execute(
                sa.select(instrument_certification_current)
                .where(
                    sa.tuple_(
                        instrument_certification_current.c.runtime_profile_id,
                        instrument_certification_current.c.exchange_instrument_id,
                    ).in_(certification_keys)
                )
                .with_for_update(of=instrument_certification_current)
                .limit(MAX_UNIVERSE_MEMBERS + 1)
            )
        ).mappings().all()
        certifications_by_key = {
            (
                str(row["runtime_profile_id"]),
                str(row["exchange_instrument_id"]),
            ): row
            for row in certifications
        }
        certifications_are_complete = bool(certification_keys) and all(
            key in certifications_by_key for key in certification_keys
        )
        certifications_are_eligible = (
            certifications_are_complete
            and all(
                certifications_by_key[key]["status"] == "eligible"
                and certifications_by_key[key]["blocker_code"] is None
                and certifications_by_key[key]["product_rules_digest"]
                is not None
                and certifications_by_key[key]["configured_leverage"] == 5
                and certifications_by_key[key]["margin_mode"] == "cross"
                and certifications_by_key[key]["position_mode"]
                == "independent_sides"
                and instrument_statuses.get(key[1]) == "active"
                for key in certification_keys
            )
        )
        certifications_are_fresh = (
            certifications_are_complete
            and all(
                int(certifications_by_key[key]["observed_at_ms"])
                <= attempted_at_ms
                < int(certifications_by_key[key]["valid_until_ms"])
                for key in certification_keys
            )
        )
        warm_readiness_is_complete = bool(scopes) and all(
            scope["warm_ready_at_ms"] is not None
            and scope["warm_readiness_digest"] is not None
            and scope["warm_valid_until_ms"] is not None
            for scope in scopes
        )
        warm_readiness_is_fresh = (
            warm_readiness_is_complete
            and all(
                int(scope["warm_ready_at_ms"])
                <= attempted_at_ms
                < int(scope["warm_valid_until_ms"])
                for scope in scopes
            )
        )
        comparative_projection_is_complete = not comparative_event
        if (
            comparative_event
            and members_are_complete
            and scopes_are_complete
            and warm_readiness_is_complete
            and warm_readiness_is_fresh
        ):
            warm_close_times = {
                int(scope["warm_ready_at_ms"]) for scope in scopes
            }
            if len(warm_close_times) == 1:
                closed_bar_time_ms = next(iter(warm_close_times))
                member_set_digest = comparative_member_set_digest(
                    members
                )
                projection_row = (
                    await self._connection.execute(
                        sa.select(comparative_projection_current)
                        .where(
                            comparative_projection_current.c.event_spec_id
                            == target["event_spec_id"],
                            comparative_projection_current.c.universe_version_id
                            == universe_version_id,
                            comparative_projection_current.c.closed_bar_time_ms
                            == closed_bar_time_ms,
                            comparative_projection_current.c.member_set_digest
                            == member_set_digest,
                        )
                        .with_for_update(
                            of=comparative_projection_current
                        )
                        .limit(1)
                    )
                ).mappings().one_or_none()
                comparative_projection_is_complete = (
                    _ready_comparative_projection_is_valid(
                        projection_row,
                        attempted_at_ms=attempted_at_ms,
                    )
                )
        return UniverseActivationReadiness(
            target_is_warming=target["lifecycle_state"] == "warming",
            current_is_complete=current_is_complete,
            event_is_active=event_is_active,
            members_are_complete=members_are_complete,
            scopes_are_complete=scopes_are_complete,
            certifications_are_complete=certifications_are_complete,
            certifications_are_eligible=certifications_are_eligible,
            certifications_are_fresh=certifications_are_fresh,
            warm_readiness_is_complete=warm_readiness_is_complete,
            warm_readiness_is_fresh=warm_readiness_is_fresh,
            comparative_projection_is_required=comparative_event,
            comparative_projection_is_complete=(
                comparative_projection_is_complete
            ),
        )

    async def get_comparative_projection(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
        closed_bar_time_ms: int,
        member_set_digest: str,
    ) -> ComparativeProjectionOutcome | None:
        row = (
            await self._connection.execute(
                sa.select(comparative_projection_current).where(
                    comparative_projection_current.c.event_spec_id
                    == event_spec_id,
                    comparative_projection_current.c.universe_version_id
                    == universe_version_id,
                    comparative_projection_current.c.closed_bar_time_ms
                    == closed_bar_time_ms,
                    comparative_projection_current.c.member_set_digest
                    == member_set_digest,
                )
            )
        ).mappings().one_or_none()
        if row is None:
            return None
        try:
            authoritative = {
                **dict(row["projection"]),
                "event_spec_id": row["event_spec_id"],
                "universe_version_id": row["universe_version_id"],
                "member_set_digest": row["member_set_digest"],
                "closed_bar_time_ms": row["closed_bar_time_ms"],
                "observed_at_ms": row["observed_at_ms"],
                "projection_version": row["projection_version"],
            }
            if row["projection_status"] == "ready":
                return ComparativeUniverseProjection.model_validate(
                    {
                        **authoritative,
                        "valid_until_ms": row["valid_until_ms"],
                    }
                )
            if row["projection_status"] == "unavailable":
                return ComparativeProjectionFailure.model_validate(
                    {
                        **authoritative,
                        "reason_code": row["failure_reason"],
                        "retry_after_ms": row["valid_until_ms"],
                    }
                )
            raise ValueError("unknown comparative projection status")
        except ValidationError as exc:
            raise RuntimeError(
                "comparative projection payload is invalid"
            ) from exc
        except ValueError as exc:
            raise RuntimeError(
                "comparative projection status is invalid"
            ) from exc

    async def save_comparative_projection(
        self,
        projection: ComparativeUniverseProjection,
    ) -> ComparativeUniverseProjection:
        statement = (
            pg_insert(comparative_projection_current)
            .values(
                event_spec_id=projection.event_spec_id,
                universe_version_id=projection.universe_version_id,
                closed_bar_time_ms=projection.closed_bar_time_ms,
                member_set_digest=projection.member_set_digest,
                projection_status="ready",
                failure_reason=None,
                projection=projection.model_dump(mode="json"),
                observed_at_ms=projection.observed_at_ms,
                valid_until_ms=projection.valid_until_ms,
                projection_version=1,
            )
            .on_conflict_do_update(
                index_elements=[
                    comparative_projection_current.c.event_spec_id,
                    comparative_projection_current.c.universe_version_id,
                ],
                set_={
                    "closed_bar_time_ms": projection.closed_bar_time_ms,
                    "member_set_digest": projection.member_set_digest,
                    "projection_status": "ready",
                    "failure_reason": None,
                    "projection": projection.model_dump(mode="json"),
                    "observed_at_ms": projection.observed_at_ms,
                    "valid_until_ms": projection.valid_until_ms,
                    "projection_version": (
                        comparative_projection_current.c.projection_version + 1
                    ),
                },
                where=sa.or_(
                    comparative_projection_current.c.closed_bar_time_ms
                    < projection.closed_bar_time_ms,
                    sa.and_(
                        comparative_projection_current.c.closed_bar_time_ms
                        == projection.closed_bar_time_ms,
                        comparative_projection_current.c.projection_status
                        == "unavailable",
                    ),
                ),
            )
        )
        await self._connection.execute(statement)
        persisted = await self.get_comparative_projection(
            event_spec_id=projection.event_spec_id,
            universe_version_id=projection.universe_version_id,
            closed_bar_time_ms=projection.closed_bar_time_ms,
            member_set_digest=projection.member_set_digest,
        )
        if not isinstance(persisted, ComparativeUniverseProjection):
            raise RuntimeError(
                "comparative projection authority changed"
            )
        return persisted

    async def save_comparative_projection_failure(
        self,
        failure: ComparativeProjectionFailure,
    ) -> ComparativeProjectionOutcome:
        statement = (
            pg_insert(comparative_projection_current)
            .values(
                event_spec_id=failure.event_spec_id,
                universe_version_id=failure.universe_version_id,
                closed_bar_time_ms=failure.closed_bar_time_ms,
                member_set_digest=failure.member_set_digest,
                projection_status="unavailable",
                failure_reason=failure.reason_code,
                projection=failure.model_dump(mode="json"),
                observed_at_ms=failure.observed_at_ms,
                valid_until_ms=failure.retry_after_ms,
                projection_version=1,
            )
            .on_conflict_do_update(
                index_elements=[
                    comparative_projection_current.c.event_spec_id,
                    comparative_projection_current.c.universe_version_id,
                ],
                set_={
                    "closed_bar_time_ms": failure.closed_bar_time_ms,
                    "member_set_digest": failure.member_set_digest,
                    "projection_status": "unavailable",
                    "failure_reason": failure.reason_code,
                    "projection": failure.model_dump(mode="json"),
                    "observed_at_ms": failure.observed_at_ms,
                    "valid_until_ms": failure.retry_after_ms,
                    "projection_version": (
                        comparative_projection_current.c.projection_version + 1
                    ),
                },
                where=sa.or_(
                    comparative_projection_current.c.closed_bar_time_ms
                    < failure.closed_bar_time_ms,
                    sa.and_(
                        comparative_projection_current.c.closed_bar_time_ms
                        == failure.closed_bar_time_ms,
                        comparative_projection_current.c.projection_status
                        == "unavailable",
                        comparative_projection_current.c.valid_until_ms
                        <= failure.observed_at_ms,
                    ),
                ),
            )
        )
        await self._connection.execute(statement)
        persisted = await self.get_comparative_projection(
            event_spec_id=failure.event_spec_id,
            universe_version_id=failure.universe_version_id,
            closed_bar_time_ms=failure.closed_bar_time_ms,
            member_set_digest=failure.member_set_digest,
        )
        if persisted is None:
            raise RuntimeError("comparative projection authority changed")
        return persisted

    async def claim_due_instrument_certification(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
    ) -> InstrumentCertificationTarget | None:
        if not worker_id.strip():
            raise ValueError("certification claim worker must be non-blank")
        if now_ms <= 0 or lease_until_ms <= now_ms:
            raise ValueError("certification claim lease must be future-dated")
        certification = instrument_certification_current
        row = (
            await self._connection.execute(
                sa.select(
                    runtime_scopes_current.c.runtime_profile_id,
                    runtime_profiles.c.venue_id,
                    runtime_profiles.c.account_id,
                    runtime_scopes_current.c.universe_version_id,
                    runtime_scopes_current.c.exchange_instrument_id,
                )
                .select_from(
                    runtime_scopes_current.join(
                        strategy_universe_versions,
                        strategy_universe_versions.c.universe_version_id
                        == runtime_scopes_current.c.universe_version_id,
                    )
                    .join(
                        runtime_profiles,
                        runtime_profiles.c.runtime_profile_id
                        == runtime_scopes_current.c.runtime_profile_id,
                    )
                    .join(
                        instruments,
                        instruments.c.exchange_instrument_id
                        == runtime_scopes_current.c.exchange_instrument_id,
                    )
                    .outerjoin(
                        certification,
                        sa.and_(
                            certification.c.runtime_profile_id
                            == runtime_scopes_current.c.runtime_profile_id,
                            certification.c.exchange_instrument_id
                            == runtime_scopes_current.c.exchange_instrument_id,
                        ),
                    )
                )
                .where(
                    strategy_universe_versions.c.lifecycle_state.in_(
                        ("warming", "active")
                    ),
                    runtime_scopes_current.c.lifecycle_state.in_(("warming", "active")),
                    sa.or_(
                        certification.c.runtime_profile_id.is_(None),
                        sa.and_(
                            certification.c.next_check_at_ms <= now_ms,
                            sa.or_(
                                certification.c.lease_expires_at_ms.is_(None),
                                certification.c.lease_expires_at_ms <= now_ms,
                            ),
                        ),
                    ),
                )
                .order_by(
                    sa.case(
                        (
                            strategy_universe_versions.c.lifecycle_state == "warming",
                            0,
                        ),
                        else_=1,
                    ),
                    sa.func.coalesce(certification.c.next_check_at_ms, 0),
                    runtime_scopes_current.c.exchange_instrument_id,
                    runtime_scopes_current.c.runtime_profile_id,
                )
                .with_for_update(of=instruments, skip_locked=True)
                .limit(1)
            )
        ).mappings().one_or_none()
        if row is None:
            return None

        key = {
            "runtime_profile_id": str(row["runtime_profile_id"]),
            "exchange_instrument_id": str(row["exchange_instrument_id"]),
        }
        existing = (
            await self._connection.execute(
                sa.select(certification)
                .where(
                    certification.c.runtime_profile_id
                    == key["runtime_profile_id"],
                    certification.c.exchange_instrument_id
                    == key["exchange_instrument_id"],
                )
                .with_for_update(of=certification)
                .limit(1)
            )
        ).mappings().one_or_none()
        if existing is None:
            await self._connection.execute(
                sa.insert(certification).values(
                    **key,
                    status="temporarily_unavailable",
                    blocker_code=None,
                    facts_digest=canonical_digest(
                        {
                            **key,
                            "status": "pending_readonly_certification",
                        }
                    ),
                    product_rules_digest=None,
                    configured_leverage=None,
                    margin_mode=None,
                    position_mode=None,
                    observed_at_ms=now_ms,
                    valid_until_ms=now_ms + 1,
                    next_check_at_ms=now_ms,
                    lease_owner=worker_id,
                    lease_expires_at_ms=lease_until_ms,
                    projection_version=1,
                )
            )
        else:
            await self._connection.execute(
                sa.update(certification)
                .where(
                    certification.c.runtime_profile_id
                    == key["runtime_profile_id"],
                    certification.c.exchange_instrument_id
                    == key["exchange_instrument_id"],
                    sa.or_(
                        certification.c.lease_expires_at_ms.is_(None),
                        certification.c.lease_expires_at_ms <= now_ms,
                    ),
                )
                .values(
                    lease_owner=worker_id,
                    lease_expires_at_ms=lease_until_ms,
                )
            )
        return InstrumentCertificationTarget(
            runtime_profile_id=key["runtime_profile_id"],
            venue_id=str(row["venue_id"]),
            account_id=str(row["account_id"]),
            universe_version_id=str(row["universe_version_id"]),
            exchange_instrument_id=key["exchange_instrument_id"],
            lease_owner=worker_id,
            lease_expires_at_ms=lease_until_ms,
        )

    async def save_instrument_certification(
        self,
        *,
        target: InstrumentCertificationTarget,
        certification: InstrumentCertification,
        product_rules_digest: str | None,
        configured_leverage: int | None,
        margin_mode: str | None,
        position_mode: str | None,
        next_check_at_ms: int,
    ) -> None:
        if next_check_at_ms < certification.observed_at_ms:
            raise ValueError("certification next check precedes observation")
        if certification.status == "eligible" and product_rules_digest is None:
            raise ValueError("eligible certification requires product rules digest")
        result = await self._connection.execute(
            sa.update(instrument_certification_current)
            .where(
                instrument_certification_current.c.runtime_profile_id
                == target.runtime_profile_id,
                instrument_certification_current.c.exchange_instrument_id
                == target.exchange_instrument_id,
                instrument_certification_current.c.lease_owner
                == target.lease_owner,
                instrument_certification_current.c.lease_expires_at_ms
                == target.lease_expires_at_ms,
            )
            .values(
                status=certification.status,
                blocker_code=certification.blocker_code,
                facts_digest=certification.facts_digest,
                product_rules_digest=product_rules_digest,
                configured_leverage=configured_leverage,
                margin_mode=margin_mode,
                position_mode=position_mode,
                observed_at_ms=certification.observed_at_ms,
                valid_until_ms=certification.valid_until_ms,
                next_check_at_ms=next_check_at_ms,
                lease_owner=None,
                lease_expires_at_ms=None,
                projection_version=(
                    instrument_certification_current.c.projection_version + 1
                ),
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("instrument certification claim is stale")
        await self._connection.execute(
            sa.update(instruments)
            .where(
                instruments.c.exchange_instrument_id
                == target.exchange_instrument_id
            )
            .values(
                status=(
                    "active"
                    if certification.status == "eligible"
                    else "pending_certification"
                )
            )
        )

    async def _lock_installs(self) -> None:
        await self._connection.execute(
            sa.select(
                sa.func.pg_advisory_xact_lock(
                    sa.func.hashtext(_INSTALL_LOCK_KEY)
                )
            )
        )

    async def _load_authority(
        self,
        request: UniverseInstallRequest,
    ) -> _InstallAuthority:
        resolved_identity = (
            await self._connection.execute(
                sa.select(
                    event_specs.c.strategy_version_id,
                    strategy_versions.c.strategy_group_id,
                )
                .join(
                    strategy_versions,
                    strategy_versions.c.strategy_version_id
                    == event_specs.c.strategy_version_id,
                )
                .where(event_specs.c.event_spec_id == request.event_spec_id)
                .limit(1)
            )
        ).mappings().one_or_none()
        if resolved_identity is None:
            raise UniverseInstallConflict("EVENT_AUTHORITY_CONFLICT")

        strategy_version_id = str(resolved_identity["strategy_version_id"])
        strategy_group_id = str(resolved_identity["strategy_group_id"])

        # Every install acquires mutable authority rows in this global order.
        # FOR UPDATE is required because status/scope changes are non-key updates
        # and therefore are not blocked by FOR KEY SHARE.
        group_row = (
            await self._connection.execute(
                sa.select(
                    strategy_groups.c.active_version_id,
                    strategy_groups.c.status,
                )
                .where(
                    strategy_groups.c.strategy_group_id == strategy_group_id
                )
                .with_for_update(of=strategy_groups)
                .limit(1)
            )
        ).mappings().one_or_none()
        version_row = (
            await self._connection.execute(
                sa.select(
                    strategy_versions.c.strategy_group_id,
                    strategy_versions.c.status,
                )
                .where(
                    strategy_versions.c.strategy_version_id
                    == strategy_version_id
                )
                .with_for_update(of=strategy_versions)
                .limit(1)
            )
        ).mappings().one_or_none()
        event_row = (
            await self._connection.execute(
                sa.select(
                    event_specs.c.strategy_version_id,
                    event_specs.c.position_side,
                    event_specs.c.status,
                )
                .where(event_specs.c.event_spec_id == request.event_spec_id)
                .with_for_update(of=event_specs)
                .limit(1)
            )
        ).mappings().one_or_none()
        profile_row = (
            await self._connection.execute(
                sa.select(
                    runtime_profiles.c.venue_id,
                    runtime_profiles.c.status,
                )
                .where(
                    runtime_profiles.c.runtime_profile_id
                    == request.runtime_profile_id
                )
                .with_for_update(of=runtime_profiles)
                .limit(1)
            )
        ).mappings().one_or_none()
        policy_row = (
            await self._connection.execute(
                sa.select(
                    owner_policy_current.c.enabled,
                    owner_policy_current.c.scope,
                )
                .where(
                    owner_policy_current.c.owner_policy_id
                    == request.owner_policy_id
                )
                .with_for_update(of=owner_policy_current)
                .limit(1)
            )
        ).mappings().one_or_none()
        if (
            group_row is None
            or group_row["status"] != "active"
            or group_row["active_version_id"] != strategy_version_id
            or version_row is None
            or version_row["status"] != "active"
            or version_row["strategy_group_id"] != strategy_group_id
            or event_row is None
            or event_row["status"] != "active"
            or event_row["strategy_version_id"] != strategy_version_id
        ):
            raise UniverseInstallConflict("EVENT_AUTHORITY_CONFLICT")
        if (
            profile_row is None
            or profile_row["status"] != "active"
            or profile_row["venue_id"] != "binance-usdm"
        ):
            raise UniverseInstallConflict("RUNTIME_PROFILE_AUTHORITY_CONFLICT")
        if policy_row is None or not policy_row["enabled"]:
            raise UniverseInstallConflict("OWNER_POLICY_AUTHORITY_CONFLICT")
        try:
            scope = UniverseInstallPolicyScope.model_validate(policy_row["scope"])
        except ValidationError as exc:
            raise UniverseInstallConflict(
                "OWNER_POLICY_AUTHORITY_CONFLICT"
            ) from exc
        if (
            scope.runtime_profile_id != request.runtime_profile_id
            or request.event_spec_id not in scope.allowed_event_spec_ids
        ):
            raise UniverseInstallConflict("OWNER_POLICY_AUTHORITY_CONFLICT")
        position_side = str(event_row["position_side"])
        if position_side not in {"long", "short"}:
            raise UniverseInstallConflict("EVENT_AUTHORITY_CONFLICT")
        return _InstallAuthority(
            strategy_group_id=strategy_group_id,
            strategy_version_id=strategy_version_id,
            position_side=cast(Literal["long", "short"], position_side),
        )

    async def _get_current_semantic_version(
        self,
        *,
        event_spec_id: str,
        semantic_digest: str,
    ) -> RowMapping | None:
        rows = (
            await self._connection.execute(
                sa.select(strategy_universe_versions)
                .where(
                    strategy_universe_versions.c.event_spec_id == event_spec_id,
                    strategy_universe_versions.c.semantic_digest == semantic_digest,
                    strategy_universe_versions.c.lifecycle_state.in_(
                        ("warming", "active")
                    ),
                )
                .limit(2)
            )
        ).mappings().all()
        if len(rows) > 1:
            raise UniverseInstallConflict("CURRENT_UNIVERSE_IDENTITY_CONFLICT")
        return rows[0] if rows else None

    async def _warming_exists(self) -> bool:
        rows = (
            await self._connection.execute(
                sa.select(strategy_universe_versions.c.universe_version_id)
                .where(
                    strategy_universe_versions.c.lifecycle_state == "warming"
                )
                .limit(2)
            )
        ).all()
        if len(rows) > 1:
            raise UniverseInstallConflict("GLOBAL_WARMING_IDENTITY_CONFLICT")
        return bool(rows)

    async def _next_version(self, event_spec_id: str) -> int:
        latest = (
            await self._connection.execute(
                sa.select(strategy_universe_versions.c.universe_version)
                .where(
                    strategy_universe_versions.c.event_spec_id == event_spec_id
                )
                .order_by(strategy_universe_versions.c.universe_version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return 1 if latest is None else int(latest) + 1

    async def _install_instruments(
        self,
        universe: StrategyUniverseVersion,
    ) -> int:
        inserted = 0
        for exchange_instrument_id in universe.exchange_instrument_ids:
            identity = parse_binance_usdm_instrument_id(exchange_instrument_id)
            rows = (
                await self._connection.execute(
                    sa.select(instruments)
                    .where(
                        sa.or_(
                            instruments.c.exchange_instrument_id
                            == exchange_instrument_id,
                            sa.and_(
                                instruments.c.venue_id == identity.venue_id,
                                instruments.c.venue_symbol == identity.symbol,
                            ),
                        )
                    )
                    .with_for_update()
                    .limit(2)
                )
            ).mappings().all()
            if rows:
                if len(rows) != 1 or not _instrument_identity_matches(
                    rows[0],
                    exchange_instrument_id=exchange_instrument_id,
                    venue_symbol=identity.symbol,
                ):
                    raise UniverseInstallConflict(
                        "CANONICAL_INSTRUMENT_IDENTITY_CONFLICT"
                    )
                continue
            await self._connection.execute(
                sa.insert(instruments).values(
                    exchange_instrument_id=exchange_instrument_id,
                    venue_id=identity.venue_id,
                    asset_class="crypto",
                    venue_symbol=identity.symbol,
                    contract_kind=identity.product_type,
                    status="pending_certification",
                )
            )
            inserted += 1
        return inserted

    async def _universe_from_row(
        self,
        row: RowMapping,
    ) -> StrategyUniverseVersion:
        members = await self.get_members(str(row["universe_version_id"]))
        return StrategyUniverseVersion(
            universe_version_id=str(row["universe_version_id"]),
            strategy_group_id=str(row["strategy_group_id"]),
            event_spec_id=str(row["event_spec_id"]),
            universe_version=int(row["universe_version"]),
            exchange_instrument_ids=members,
            semantic_digest=str(row["semantic_digest"]),
            installed_at_ms=int(row["installed_at_ms"]),
        )

    async def _assert_existing_scopes(
        self,
        row: RowMapping,
        *,
        request: UniverseInstallRequest,
        authority: _InstallAuthority,
    ) -> None:
        universe = await self._universe_from_row(row)
        if universe.exchange_instrument_ids != request.exchange_instrument_ids:
            raise UniverseInstallConflict("UNIVERSE_MEMBER_IDENTITY_CONFLICT")
        scopes = (
            await self._connection.execute(
                sa.select(
                    runtime_scopes_current.c.strategy_group_id,
                    runtime_scopes_current.c.strategy_version_id,
                    runtime_scopes_current.c.runtime_profile_id,
                    runtime_scopes_current.c.owner_policy_id,
                    runtime_scopes_current.c.exchange_instrument_id,
                    runtime_scopes_current.c.position_side,
                    runtime_scopes_current.c.universe_semantic_digest,
                )
                .where(
                    runtime_scopes_current.c.universe_version_id
                    == universe.universe_version_id
                )
                .order_by(runtime_scopes_current.c.exchange_instrument_id)
                .limit(MAX_UNIVERSE_MEMBERS + 1)
            )
        ).mappings().all()
        expected_members = universe.exchange_instrument_ids
        if (
            len(scopes) != len(expected_members)
            or tuple(str(scope["exchange_instrument_id"]) for scope in scopes)
            != expected_members
            or any(
                scope["strategy_group_id"] != authority.strategy_group_id
                or scope["strategy_version_id"] != authority.strategy_version_id
                or scope["runtime_profile_id"] != request.runtime_profile_id
                or scope["owner_policy_id"] != request.owner_policy_id
                or scope["position_side"] != authority.position_side
                or scope["universe_semantic_digest"] != universe.semantic_digest
                for scope in scopes
            )
        ):
            raise UniverseInstallConflict("UNIVERSE_SCOPE_IDENTITY_CONFLICT")
        if row["lifecycle_state"] == "active":
            current = await self.get_current(request.event_spec_id)
            if (
                current is None
                or current.universe_version_id != universe.universe_version_id
                or current.semantic_digest != universe.semantic_digest
            ):
                raise UniverseInstallConflict("CURRENT_UNIVERSE_IDENTITY_CONFLICT")


def _result(
    *,
    status: UniverseInstallStatus,
    universe: StrategyUniverseVersion | None,
    lifecycle_state: Literal["warming", "active"] | None,
    inserted_instrument_count: int = 0,
    inserted_version_count: int = 0,
    inserted_member_count: int = 0,
    inserted_scope_count: int = 0,
) -> UniverseInstallResult:
    return UniverseInstallResult(
        status=status,
        universe=universe,
        lifecycle_state=lifecycle_state,
        inserted_instrument_count=inserted_instrument_count,
        inserted_version_count=inserted_version_count,
        inserted_member_count=inserted_member_count,
        inserted_scope_count=inserted_scope_count,
    )


def _not_ready_activation(
    *,
    target: RowMapping,
    current: RowMapping | None,
    reason_code: str,
) -> UniverseActivationResult:
    return UniverseActivationResult(
        status=UniverseActivationStatus.NOT_READY,
        reason_code=reason_code,
        event_spec_id=str(target["event_spec_id"]),
        universe_version_id=str(target["universe_version_id"]),
        previous_universe_version_id=(
            None
            if current is None
            else str(current["universe_version_id"])
        ),
        activation_generation=(
            None
            if current is None
            else int(current["activation_generation"])
        ),
        activated_at_ms=None,
    )


def _ready_comparative_projection_is_valid(
    row: RowMapping | None,
    *,
    attempted_at_ms: int,
) -> bool:
    if (
        row is None
        or row["projection_status"] != "ready"
        or row["failure_reason"] is not None
        or int(row["valid_until_ms"]) <= attempted_at_ms
    ):
        return False
    try:
        ComparativeUniverseProjection.model_validate(
            {
                **dict(row["projection"]),
                "event_spec_id": row["event_spec_id"],
                "universe_version_id": row["universe_version_id"],
                "member_set_digest": row["member_set_digest"],
                "closed_bar_time_ms": row["closed_bar_time_ms"],
                "observed_at_ms": row["observed_at_ms"],
                "valid_until_ms": row["valid_until_ms"],
                "projection_version": row["projection_version"],
            }
        )
    except ValidationError:
        return False
    return True


def _universe_version_id(event_spec_id: str, universe_version: int) -> str:
    event_key = sha256(event_spec_id.encode("utf-8")).hexdigest()[:24]
    return f"universe:{event_key}:v{universe_version}"


def _runtime_scope_id(
    *,
    universe_version_id: str,
    runtime_profile_id: str,
    exchange_instrument_id: str,
    position_side: str,
) -> str:
    identity = ":".join(
        (
            universe_version_id,
            runtime_profile_id,
            exchange_instrument_id,
            position_side,
        )
    )
    return f"scope:universe:{sha256(identity.encode('utf-8')).hexdigest()}"


def _warming_scope_values(
    *,
    universe: StrategyUniverseVersion,
    authority: _InstallAuthority,
    request: UniverseInstallRequest,
    exchange_instrument_id: str,
) -> dict[str, object]:
    return {
        "runtime_scope_id": _runtime_scope_id(
            universe_version_id=universe.universe_version_id,
            runtime_profile_id=request.runtime_profile_id,
            exchange_instrument_id=exchange_instrument_id,
            position_side=authority.position_side,
        ),
        "strategy_group_id": authority.strategy_group_id,
        "strategy_version_id": authority.strategy_version_id,
        "event_spec_id": universe.event_spec_id,
        "runtime_profile_id": request.runtime_profile_id,
        "owner_policy_id": request.owner_policy_id,
        "exchange_instrument_id": exchange_instrument_id,
        "position_side": authority.position_side,
        "universe_version_id": universe.universe_version_id,
        "universe_semantic_digest": universe.semantic_digest,
        "lifecycle_state": "warming",
        "observation_enabled": True,
        "entry_enabled": False,
        "scope_version": 1,
        "warm_ready_at_ms": None,
        "warm_readiness_digest": None,
        "warm_valid_until_ms": None,
        "next_observation_due_at_ms": request.installed_at_ms,
        "lease_expires_at_ms": None,
        "lease_owner": None,
        "observation_generation": 0,
        "updated_at_ms": request.installed_at_ms,
    }


def _instrument_identity_matches(
    row: RowMapping,
    *,
    exchange_instrument_id: str,
    venue_symbol: str,
) -> bool:
    return (
        row["exchange_instrument_id"] == exchange_instrument_id
        and row["venue_id"] == "binance-usdm"
        and row["asset_class"] == "crypto"
        and row["venue_symbol"] == venue_symbol
        and row["contract_kind"] == "perpetual"
        and row["status"] in {"pending_certification", "active"}
    )
