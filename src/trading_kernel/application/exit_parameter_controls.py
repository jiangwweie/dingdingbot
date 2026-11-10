"""Owner publication of independent per-Event exit profiles in one transaction."""

from __future__ import annotations

from decimal import Decimal
from hashlib import sha256
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, JsonValue, field_validator, model_validator

from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    OwnerControlBlocked,
    OwnerControlConflict,
    _authorization,
    _require_matching_authorization,
)
from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.entry_regime import REGIME_EVENTS, EntryRegimeControl
from src.trading_kernel.domain.exit_policy import (
    CurrentEventExitBinding,
    ExitProfile,
    build_event_exit_binding,
)
from src.trading_kernel.domain.post_fill_exit import (
    PostFillExitPlan,
    PostFillExitRequest,
    build_post_fill_exit_plan,
)
from src.trading_kernel.domain.strategy_registry import registered_strategy_contracts

SUPPORTED_GROUPS = {"CPM-RO-001", "MI-001", "MPG-001", "BRF2-001", "SOR-1H-001"}
SUPPORTED_EVENTS = {
    c.event_spec_id
    for c in registered_strategy_contracts()
    if c.strategy_group_id in SUPPORTED_GROUPS
}


class ExitParameterChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_spec_id: str
    expected_version: int
    expected_binding_id: str
    reward_multiple: Decimal
    quantity_fraction: Decimal
    max_actual_fraction: Decimal | None = None
    ma50_enabled: bool | None = None
    expected_regime_revision: int | None = None

    @field_validator("reward_multiple")
    @classmethod
    def _reward(cls, value: Decimal) -> Decimal:
        if (
            not value.is_finite()
            or not Decimal("0.1") <= value <= Decimal(5)
            or value % Decimal("0.1")
        ):
            raise ValueError("TP1 reward must be 0.1 to 5.0R in 0.1R steps")
        return value

    @model_validator(mode="after")
    def _scope(self) -> ExitParameterChange:
        if (
            self.event_spec_id not in SUPPORTED_EVENTS
            or self.expected_version < 1
            or not self.expected_binding_id.strip()
        ):
            raise ValueError("unsupported exit-parameter event or binding")
        if not self.quantity_fraction.is_finite() or not Decimal(
            0
        ) < self.quantity_fraction <= Decimal("0.50"):
            raise ValueError("TP1 target must be in (0,50%]")
        if self.max_actual_fraction is not None and (
            not self.max_actual_fraction.is_finite()
            or not self.quantity_fraction <= self.max_actual_fraction <= Decimal("0.50")
        ):
            raise ValueError("minimum TP1 cap must cover target and be at most 50%")
        if (self.ma50_enabled is None) != (self.expected_regime_revision is None):
            raise ValueError("MA50 update requires its expected revision")
        if self.ma50_enabled is not None and (
            self.event_spec_id not in REGIME_EVENTS
            or self.expected_regime_revision is None
            or self.expected_regime_revision < 1
        ):
            raise ValueError("MA50 applies only to CPM/MI/MPG LONG")
        return self


class ExitQuantitySample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_spec_id: str
    exchange_instrument_id: str
    quantity: Decimal
    entry_price: Decimal
    stop_price: Decimal

    @model_validator(mode="after")
    def _validate(self) -> ExitQuantitySample:
        from src.trading_kernel.domain.instrument_identity import (
            parse_binance_usdm_instrument_id,
        )

        parse_binance_usdm_instrument_id(self.exchange_instrument_id)
        if any(
            not v.is_finite() or v <= 0
            for v in (self.quantity, self.entry_price, self.stop_price)
        ):
            raise ValueError("quantity preview requires finite positive values")
        return self


class ExitQuantitySampleResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sample: ExitQuantitySample
    status: str
    plan: PostFillExitPlan | None = None


class ExitParameterPublishRequest(ControlMutationRequest):
    venue_id: Literal["binance-usdm"]
    account_id: str
    changes: tuple[ExitParameterChange, ...]
    quantity_samples: tuple[ExitQuantitySample, ...] = ()

    @model_validator(mode="after")
    def _bundle(self) -> ExitParameterPublishRequest:
        if not self.account_id.strip() or not 1 <= len(self.changes) <= 6:
            raise ValueError("exit publication needs an account and one to six events")
        if len({x.event_spec_id for x in self.changes}) != len(self.changes):
            raise ValueError("exit publication events must be unique")
        if self.expected_version != 1:
            raise ValueError("unsupported exit-parameter capability revision")
        if len(self.quantity_samples) > 6 or any(
            s.event_spec_id not in {c.event_spec_id for c in self.changes}
            for s in self.quantity_samples
        ):
            raise ValueError("quantity samples must refer to changed events")
        return self


class ExitParameterPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    profiles: tuple[ExitProfile, ...]
    source_profiles: tuple[ExitProfile, ...]
    quantity_previews: tuple[ExitQuantitySampleResult, ...] = ()
    affects: Literal["new_tickets_only"] = "new_tickets_only"


class ExitParameterReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    bindings: tuple[CurrentEventExitBinding, ...]
    regimes: tuple[EntryRegimeControl, ...]
    authorized_at_ms: int


async def _prepare(
    uow: KernelUnitOfWork, request: ExitParameterPublishRequest, *, check_current: bool
) -> ExitParameterPreview:
    control = await uow.directional_risk.get(request.venue_id, request.account_id)
    if control is None:
        raise OwnerControlBlocked("exit_parameter_account_scope_mismatch")
    profiles = []
    sources = []
    for change in request.changes:
        binding = await uow.exit_profiles.get_binding(change.expected_binding_id)
        if binding is None or binding.event_spec_id != change.event_spec_id:
            raise OwnerControlBlocked("exit_binding_missing")
        current = await uow.exit_profiles.get_current_binding(change.event_spec_id)
        if check_current and (
            current is None
            or current.projection_version != change.expected_version
            or current.exit_binding_id != change.expected_binding_id
        ):
            raise OwnerControlConflict("exit_binding_version_conflict")
        event = await uow.signals.get_event_spec(change.event_spec_id)
        if event is None or event.status != "active":
            raise OwnerControlBlocked("exit_parameter_event_not_active")
        source = await uow.exit_profiles.get_profile(
            exit_profile_id=binding.exit_profile_id,
            semantic_hash=binding.exit_profile_semantic_hash,
        )
        if source is None or (check_current and source.status != "active"):
            raise OwnerControlBlocked("exit_profile_not_active")
        if source.profile.position_side != event.position_side:
            raise OwnerControlBlocked("exit_profile_side_mismatch")
        if change.ma50_enabled is not None:
            regime = await uow.entry_regimes.get_control(change.event_spec_id)
            if check_current and (
                regime is None or regime.revision != change.expected_regime_revision
            ):
                raise OwnerControlConflict("entry_regime_revision_conflict")
        data = source.profile.model_dump(mode="json")
        identity = sha256(
            f"{request.idempotency_key}:{change.event_spec_id}".encode()
        ).hexdigest()[:32]
        data["exit_profile_id"] = "exit-profile:owner:" + identity
        data["exit_profile_version"] = source.profile.exit_profile_version + 1
        data["tp1"]["reward_multiple"] = str(change.reward_multiple)
        data["tp1"]["price_basis"] = "actual_fill"
        data["tp1"]["quantity_fraction"] = str(change.quantity_fraction)
        data["tp1"].pop("quantity_rule", None)
        if change.max_actual_fraction is not None:
            data["tp1"]["quantity_rule"] = {
                "max_actual_fraction": str(change.max_actual_fraction)
            }
        profiles.append(ExitProfile.model_validate(data))
        sources.append(source.profile)
    return ExitParameterPreview(
        profiles=tuple(profiles), source_profiles=tuple(sources)
    )


async def preview_exit_parameters(
    uow: KernelUnitOfWork, request: ExitParameterPublishRequest
) -> ExitParameterPreview:
    preview = await _prepare(uow, request, check_current=True)
    samples = []
    profiles = {
        change.event_spec_id: profile
        for change, profile in zip(request.changes, preview.profiles, strict=True)
    }
    for sample in request.quantity_samples:
        rules = await uow.signals.get_instrument_rules(
            request.venue_id, sample.exchange_instrument_id
        )
        if (
            rules is None
            or not rules.observed_at_ms <= request.now_ms < rules.valid_until_ms
        ):
            samples.append(
                ExitQuantitySampleResult(
                    sample=sample, status="instrument_rules_unavailable_or_stale"
                )
            )
            continue
        decision = build_post_fill_exit_plan(
            PostFillExitRequest(
                ticket_id="preview-only",
                exit_binding_id="preview-only",
                profile=profiles[sample.event_spec_id],
                quantity=sample.quantity,
                average_fill_price=sample.entry_price,
                initial_stop_price=sample.stop_price,
                quantity_step=rules.quantity_step,
                price_tick=rules.price_tick,
                min_quantity=rules.min_quantity,
                min_notional=rules.min_notional,
                rules_digest=canonical_digest(rules.model_dump(mode="json")),
                rules_observed_at_ms=rules.observed_at_ms,
                rules_valid_until_ms=rules.valid_until_ms,
                created_at_ms=request.now_ms,
            )
        )
        samples.append(
            ExitQuantitySampleResult(
                sample=sample,
                status=decision.quantity_rejection or decision.status,
                plan=decision.plan,
            )
        )
    return preview.model_copy(update={"quantity_previews": tuple(samples)})


async def publish_exit_parameters(
    uow: KernelUnitOfWork,
    request: ExitParameterPublishRequest,
    *,
    authentication_strength: Literal["totp_step_up"],
) -> ExitParameterReceipt:
    if authentication_strength != "totp_step_up":
        raise OwnerControlBlocked("exit_parameter_requires_step_up")
    await uow.directional_risk.lock(request.venue_id, request.account_id)
    await uow.exit_profiles.acquire_authority_write_lock()
    await uow.entry_regimes.lock_controls(
        tuple(
            sorted(
                x.event_spec_id for x in request.changes if x.ma50_enabled is not None
            )
        )
    )
    scope = cast(
        dict[str, JsonValue],
        {
            "kind": "exit_parameter_publication",
            "venue_id": request.venue_id,
            "account_id": request.account_id,
            "changes": [x.model_dump(mode="json") for x in request.changes],
        },
    )
    existing = await uow.owner_controls.get_authorization_by_idempotency_key(
        request.idempotency_key
    )
    if (
        existing is None
        and any(c.ma50_enabled is not None for c in request.changes)
        and await uow.directional_risk.has_in_flight(
            request.venue_id, request.account_id
        )
    ):
        raise OwnerControlConflict("entry_regime_send_in_flight")
    if existing is not None:
        _require_matching_authorization(
            existing, purpose="exit_profile_bind", request=request, target_scope=scope
        )
        if existing.authentication_strength != "totp_step_up":
            raise OwnerControlBlocked("exit_parameter_requires_step_up")
    preview = await _prepare(uow, request, check_current=existing is None)
    authorization = existing or _authorization(
        purpose="exit_profile_bind",
        request=request,
        authentication_strength="totp_step_up",
        target_scope=scope,
    )
    if existing is None:
        await uow.owner_controls.add_authorization(authorization)
    receipts = []
    regimes = []
    for change, profile in zip(request.changes, preview.profiles, strict=True):
        previous = await uow.exit_profiles.get_binding(change.expected_binding_id)
        assert previous is not None
        binding = build_event_exit_binding(
            exit_binding_id=f"exit-binding:{change.event_spec_id}:v{previous.binding_version + 1}",
            binding_version=previous.binding_version + 1,
            event_spec_id=change.event_spec_id,
            exit_profile_id=profile.exit_profile_id,
            exit_profile_semantic_hash=profile.semantic_hash(),
            activation_reason=request.reason,
            created_at_ms=authorization.authorized_at_ms,
        )
        if existing is None:
            current = await uow.exit_profiles.get_current_binding(
                change.event_spec_id, for_update=True
            )
            assert current is not None
            await uow.exit_profiles.add_profile(profile, created_at_ms=request.now_ms)
            receipt = await uow.exit_profiles.switch_current_binding(
                expected_current=current,
                new_binding=binding,
                owner_authorization_id=authorization.authorization_id,
                reason=request.reason,
                switched_at_ms=request.now_ms,
            )
        else:
            if await uow.exit_profiles.get_binding(binding.exit_binding_id) != binding:
                raise OwnerControlBlocked("exit_parameter_receipt_missing")
            receipt = CurrentEventExitBinding(
                event_spec_id=change.event_spec_id,
                exit_binding_id=binding.exit_binding_id,
                binding_semantic_hash=binding.binding_semantic_hash,
                projection_version=change.expected_version + 1,
                activated_at_ms=authorization.authorized_at_ms,
            )
        receipts.append(receipt)
        if change.ma50_enabled is not None:
            assert change.expected_regime_revision is not None
            if existing is None:
                regimes.append(
                    await uow.entry_regimes.switch(
                        event_spec_id=change.event_spec_id,
                        expected_revision=change.expected_regime_revision,
                        enabled=change.ma50_enabled,
                        authorization_id=authorization.authorization_id,
                        now_ms=request.now_ms,
                    )
                )
            else:
                regimes.append(
                    EntryRegimeControl(
                        event_spec_id=change.event_spec_id,
                        revision=change.expected_regime_revision + 1,
                        enabled=change.ma50_enabled,
                        authorization_id=authorization.authorization_id,
                        created_at_ms=authorization.authorized_at_ms,
                    )
                )
    return ExitParameterReceipt(
        bindings=tuple(receipts),
        regimes=tuple(regimes),
        authorized_at_ms=authorization.authorized_at_ms,
    )
