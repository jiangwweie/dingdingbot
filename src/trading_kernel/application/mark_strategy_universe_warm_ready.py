"""Persist complete warm-readiness evidence for one candidate scope."""

from __future__ import annotations

from hashlib import sha256
import json
import re

from pydantic import BaseModel, ConfigDict, field_validator

from src.trading_kernel.application.ports import KernelUnitOfWork


_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class MarkStrategyUniverseWarmReadyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime_scope_id: str
    universe_version_id: str
    observation_fact_digest: str
    ready_at_ms: int

    @field_validator(
        "runtime_scope_id",
        "universe_version_id",
        mode="before",
    )
    @classmethod
    def _require_identity(cls, value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("warm-readiness identity must be non-blank")
        return normalized

    @field_validator("observation_fact_digest")
    @classmethod
    def _require_digest(cls, value: str) -> str:
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("warm-readiness observation digest is invalid")
        return value

    @field_validator("ready_at_ms")
    @classmethod
    def _require_time(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("warm-readiness time must be positive")
        return value


async def mark_strategy_universe_warm_ready(
    uow: KernelUnitOfWork,
    request: MarkStrategyUniverseWarmReadyRequest,
) -> str:
    stored = await uow.strategy_universes.get(request.universe_version_id)
    scope = await uow.signals.get_runtime_scope(request.runtime_scope_id)
    if stored is None or scope is None:
        raise ValueError("warm-readiness authority is missing")
    universe, _ = stored
    if (
        scope.universe_version_id != universe.universe_version_id
        or scope.event_spec_id != universe.event_spec_id
        or not universe.contains_candidate(scope.exchange_instrument_id)
    ):
        raise ValueError("warm-readiness scope differs from Universe")

    product_profile_id: str | None = None
    product_profile_digest: str | None = None
    projection_run_id: str | None = None
    instrument_rules_projection_version: int | None = None
    if universe.asset_class == "us_equity":
        authority = await uow.product_admission.load_current_authority(
            scope.exchange_instrument_id
        )
        projection = await uow.strategy_universes.get_latest_projection(
            event_spec_id=universe.event_spec_id,
            universe_version_id=universe.universe_version_id,
            at_or_before_close_time_ms=request.ready_at_ms,
        )
        if (
            authority is None
            or projection is None
            or projection.universe_digest != universe.semantic_digest()
            or authority.profile.observed_at_ms > request.ready_at_ms
            or authority.profile.valid_until_ms <= request.ready_at_ms
            or authority.coverage is None
            or authority.coverage.coverage_status != "complete"
            or not authority.coverage.coverage_start_ms
            <= request.ready_at_ms
            <= authority.coverage.coverage_end_ms
            or authority.coverage.valid_until_ms <= request.ready_at_ms
        ):
            raise ValueError("US scope warm-readiness evidence is incomplete")
        if scope.reprofile_required_at_ms is not None:
            rules = await uow.signals.get_instrument_rules(
                authority.profile.venue_id,
                scope.exchange_instrument_id,
            )
            if (
                authority.profile.observed_at_ms
                <= scope.reprofile_required_at_ms
                or projection.as_of_close_time_ms
                < scope.reprofile_required_at_ms
                or rules is None
                or rules.observed_at_ms <= scope.reprofile_required_at_ms
                or rules.valid_until_ms <= request.ready_at_ms
            ):
                raise ValueError(
                    "corporate-action reprofile evidence is incomplete"
                )
            instrument_rules_projection_version = rules.projection_version
        product_profile_id = authority.profile.product_profile_id
        product_profile_digest = authority.profile.semantic_digest
        projection_run_id = projection.projection_run_id

    payload = {
        "runtime_scope_id": request.runtime_scope_id,
        "universe_version_id": request.universe_version_id,
        "universe_digest": universe.semantic_digest(),
        "observation_fact_digest": request.observation_fact_digest,
        "product_profile_id": product_profile_id,
        "product_profile_digest": product_profile_digest,
        "projection_run_id": projection_run_id,
        "instrument_rules_projection_version": (
            instrument_rules_projection_version
        ),
        "ready_at_ms": request.ready_at_ms,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    readiness_digest = f"sha256:{sha256(encoded).hexdigest()}"
    await uow.strategy_universes.mark_scope_warm_ready(
        runtime_scope_id=request.runtime_scope_id,
        universe_version_id=request.universe_version_id,
        observation_fact_digest=request.observation_fact_digest,
        product_profile_id=product_profile_id,
        product_profile_digest=product_profile_digest,
        projection_run_id=projection_run_id,
        instrument_rules_projection_version=(
            instrument_rules_projection_version
        ),
        readiness_digest=readiness_digest,
        ready_at_ms=request.ready_at_ms,
    )
    return readiness_digest
