"""Owner preview and atomic activation of six immutable exit revisions."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from src.trading_kernel.application.owner_control import (
    ControlMutationRequest,
    OwnerControlBlocked,
    OwnerControlConflict,
    _authorization,
    _require_matching_authorization,
)
from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.exit_configuration import (
    DIRECTIONAL_EXIT_EVENTS,
    EXIT_EVENTS,
    MA50_EVENTS,
    ExitConfigurationIntent,
    ExitConfigurationRecord,
    ProfileRevisionLineage,
    derive_exit_profile,
)
from src.trading_kernel.domain.orb_session_selection import (
    ORB_DIRECTIONAL_EVENTS,
    ORB_DIRECTIONAL_LONG_EVENT,
    ORB_EVENT_SPEC_IDS,
)


class ExitConfigurationPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intent: ExitConfigurationIntent
    profiles: tuple[ProfileRevisionLineage, ...]
    preview_digest: str
    source_configuration_revision: int
    valid_until_ms: int


class ActivateExitConfigurationRequest(ControlMutationRequest):
    intent: ExitConfigurationIntent
    preview_digest: str
    preview_valid_until_ms: int


async def preview_exit_configuration(
    uow: KernelUnitOfWork,
    *,
    intent: ExitConfigurationIntent,
    now_ms: int,
    valid_until_ms: int | None = None,
) -> ExitConfigurationPreview:
    # Shared lock ordering with admission/final-send: exit authority first.
    await uow.exit_profiles.acquire_authority_write_lock()
    runtime_profile=await uow.signals.get_runtime_profile("tiny-live-v1")
    if runtime_profile is None or runtime_profile.venue_id!=intent.venue_id or runtime_profile.account_id!=intent.account_id:
        raise OwnerControlBlocked("exit_configuration_account_scope_mismatch")
    current = await uow.exit_profiles.get_current_configuration(
        venue_id=intent.venue_id, account_id=intent.account_id
    )
    revision = 0 if current is None else current.revision
    if revision != intent.expected_revision:
        raise OwnerControlConflict("exit_configuration_revision_conflict")
    target_events = {e.event_spec_id for e in intent.events}
    current_events = set() if current is None else {e.event_spec_id for e in current.intent.events}
    if target_events == set(EXIT_EVENTS):
        installed = await uow.exit_profiles.get_current_binding(ORB_DIRECTIONAL_LONG_EVENT)
        if installed is not None:
            raise OwnerControlBlocked("retired_sor_exit_configuration")
    split_transfer = current is not None and current_events == set(EXIT_EVENTS) and (
        target_events == set(DIRECTIONAL_EXIT_EVENTS)
    )
    if current is not None and current_events == set(DIRECTIONAL_EXIT_EVENTS) and (
        target_events != current_events
    ):
        raise OwnerControlBlocked("retired_sor_exit_configuration")
    carried = {} if not split_transfer or current is None else {
        item.event_spec_id: item for item in current.intent.events
    }
    if valid_until_ms is None:
        valid_until_ms = now_ms + 60_000
    if not now_ms < valid_until_ms <= now_ms + 60_000:
        raise OwnerControlBlocked("exit_configuration_preview_expired")
    if current is None:
        for item in intent.events:
            sor = item.event_spec_id in (*ORB_EVENT_SPEC_IDS, *ORB_DIRECTIONAL_EVENTS)
            if (
                item.reward_multiple != (Decimal("1.2") if sor else Decimal(1))
                or (
                    item.event_spec_id != ORB_DIRECTIONAL_LONG_EVENT
                    and item.ma50_enabled != (item.event_spec_id in MA50_EVENTS)
                )
                or (
                    not sor
                    and (
                        item.target_fraction != Decimal(".05")
                        or not item.minimum_lift
                        or item.max_actual_fraction != Decimal(".50")
                    )
                )
            ):
                raise OwnerControlBlocked(
                    "initial_exit_configuration_requires_approved_parameters"
                )
    profiles = []
    for parameters in sorted(intent.events, key=lambda e: e.event_spec_id):
        binding_current = await uow.exit_profiles.get_current_binding(
            parameters.event_spec_id, for_update=True
        )
        if (
            binding_current is None
            or binding_current.exit_binding_id != parameters.expected_binding_id
            or binding_current.projection_version
            != parameters.expected_binding_revision
        ):
            raise OwnerControlConflict("exit_binding_version_conflict")
        binding = await uow.exit_profiles.get_binding(parameters.expected_binding_id)
        if binding is None:
            raise OwnerControlBlocked("exit_binding_missing")
        source = await uow.exit_profiles.get_profile(
            exit_profile_id=binding.exit_profile_id,
            semantic_hash=binding.exit_profile_semantic_hash,
        )
        if source is None or source.status != "active":
            raise OwnerControlBlocked("exit_profile_not_active")
        event = await uow.signals.get_event_spec(parameters.event_spec_id)
        if (
            event is None
            or event.status != "active"
            or event.position_side != source.profile.position_side
        ):
            raise OwnerControlBlocked("exit_event_scope_invalid")
        if carried:
            old_event_id = parameters.event_spec_id
            if old_event_id in ORB_DIRECTIONAL_EVENTS:
                old_event_id = ORB_EVENT_SPEC_IDS[ORB_DIRECTIONAL_EVENTS.index(old_event_id)]
                old_current = await uow.exit_profiles.get_current_binding(old_event_id, for_update=True)
                old_binding = (
                    None if old_current is None
                    else await uow.exit_profiles.get_binding(old_current.exit_binding_id)
                )
                old_lineage = next(p for p in current.profiles if p.event_spec_id == old_event_id) if current else None
                if (
                    old_binding is None or old_lineage is None
                    or old_binding.exit_profile_id != old_lineage.profile.exit_profile_id
                    or old_binding.exit_profile_semantic_hash != old_lineage.profile.semantic_hash()
                ):
                    raise OwnerControlBlocked("split_exit_configuration_source_drift")
                source = await uow.exit_profiles.get_profile(
                    exit_profile_id=old_binding.exit_profile_id,
                    semantic_hash=old_binding.exit_profile_semantic_hash,
                )
                if source is None or source.status != "active":
                    raise OwnerControlBlocked("split_exit_configuration_source_drift")
            old = carried[old_event_id]
            if (
                parameters.reward_multiple != old.reward_multiple
                or parameters.target_fraction != old.target_fraction
                or parameters.minimum_lift != old.minimum_lift
                or parameters.max_actual_fraction != old.max_actual_fraction
                or (
                    parameters.event_spec_id != ORB_DIRECTIONAL_LONG_EVENT
                    and parameters.ma50_enabled != old.ma50_enabled
                )
            ):
                raise OwnerControlBlocked("split_exit_configuration_must_preserve_effective_terms")
        configuration_id = (
            "exit-config:"
            + canonical_digest({"intent": intent.digest(), "revision": revision + 1})[
                7:39
            ]
        )
        profile = derive_exit_profile(
            source=source.profile,
            parameters=parameters,
            revision_id="exit-owner:"
            + canonical_digest(
                {
                    "configuration_id": configuration_id,
                    "event": parameters.event_spec_id,
                }
            )[7:39],
        )
        profiles.append(
            ProfileRevisionLineage(
                event_spec_id=parameters.event_spec_id,
                source_profile_id=source.profile.exit_profile_id,
                source_profile_hash=source.profile.semantic_hash(),
                profile=profile,
            )
        )
    digest = canonical_digest(
        {
            "intent": intent.model_dump(mode="json"),
            "profiles": [p.model_dump(mode="json") for p in profiles],
            "valid_until_ms": valid_until_ms,
        }
    )
    return ExitConfigurationPreview(
        intent=intent,
        profiles=tuple(profiles),
        preview_digest=digest,
        source_configuration_revision=revision,
        valid_until_ms=valid_until_ms,
    )


async def activate_exit_configuration(
    uow: KernelUnitOfWork,
    *,
    request: ActivateExitConfigurationRequest,
    authentication_strength: Literal["totp_step_up"],
) -> ExitConfigurationRecord:
    if authentication_strength != "totp_step_up":
        raise OwnerControlBlocked("exit_configuration_requires_totp")
    intent = request.intent
    if request.expected_version != intent.expected_revision:
        raise OwnerControlConflict("exit_configuration_revision_conflict")
    scope: dict[str, JsonValue] = {
        "product_id": intent.product_id,
        "venue_id": intent.venue_id,
        "account_id": intent.account_id,
        "intent_digest": intent.digest(),
        "preview_digest": request.preview_digest,
        "preview_valid_until_ms": request.preview_valid_until_ms,
    }
    await uow.exit_profiles.acquire_authority_write_lock()
    existing = await uow.owner_controls.get_authorization_by_idempotency_key(
        request.idempotency_key
    )
    configuration_id = (
        "exit-config:"
        + canonical_digest(
            {"intent": intent.digest(), "revision": intent.expected_revision + 1}
        )[7:39]
    )
    scope["configuration_id"] = configuration_id
    if existing is not None:
        _require_matching_authorization(
            existing, purpose="exit_profile_bind", request=request, target_scope=scope
        )
        record = await uow.exit_profiles.get_configuration(configuration_id)
        if record is None or record.owner_authorization_id != existing.authorization_id:
            raise OwnerControlBlocked("exit_configuration_idempotency_missing")
        return record
    preview = await preview_exit_configuration(
        uow,
        intent=intent,
        now_ms=request.now_ms,
        valid_until_ms=request.preview_valid_until_ms,
    )
    if preview.preview_digest != request.preview_digest:
        raise OwnerControlConflict("exit_configuration_preview_changed")
    authorization = _authorization(
        purpose="exit_profile_bind",
        request=request,
        authentication_strength="totp_step_up",
        target_scope=scope,
    )
    await uow.owner_controls.add_authorization(authorization)
    record = ExitConfigurationRecord(
        configuration_id=configuration_id,
        revision=intent.expected_revision + 1,
        intent=intent,
        profiles=preview.profiles,
        owner_authorization_id=authorization.authorization_id,
        activation_reason=request.reason,
        preview_digest=request.preview_digest,
        preview_valid_until_ms=request.preview_valid_until_ms,
        created_at_ms=request.now_ms,
    )
    await uow.exit_profiles.activate_configuration(record)
    return record
