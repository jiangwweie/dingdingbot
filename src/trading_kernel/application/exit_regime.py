"""Shared MA50 authority checks for admission and final ENTRY sending."""

from __future__ import annotations

from src.trading_kernel.application.ports import KernelUnitOfWork
from src.trading_kernel.domain.exit_configuration import EXIT_EVENTS
from src.trading_kernel.domain.exit_regime import RegimeAdmissionProof
from src.trading_kernel.domain.orb_session_selection import (
    ORB_DIRECTIONAL_EVENTS,
    ORB_DIRECTIONAL_LONG_EVENT,
    ORB_EVENT_SPEC_IDS,
)


async def check_exit_regime(
    uow: KernelUnitOfWork,
    *,
    venue_id: str,
    account_id: str,
    event_spec_id: str,
    now_ms: int,
) -> tuple[str | None, RegimeAdmissionProof | None]:
    current = await uow.exit_profiles.get_current_configuration(
        venue_id=venue_id, account_id=account_id
    )
    requires_configuration = event_spec_id in ORB_DIRECTIONAL_EVENTS
    requires_ma50 = event_spec_id == ORB_DIRECTIONAL_LONG_EVENT
    if current is None:
        if requires_configuration:
            return "exit_configuration_not_activated", None
        capability = await uow.signals.get_runtime_capability("exchange_commands")
        if (
            event_spec_id in EXIT_EVENTS
            and capability is not None
            and capability.certification.get("exit_configuration_required")
        ):
            return "exit_configuration_not_activated", None
        return None, None
    parameters = next(
        (e for e in current.intent.events if e.event_spec_id == event_spec_id), None
    )
    if parameters is None or (requires_ma50 and not parameters.ma50_enabled):
        retired_hourly_event = event_spec_id in ORB_EVENT_SPEC_IDS and any(
            item.event_spec_id in ORB_DIRECTIONAL_EVENTS for item in current.intent.events
        )
        if requires_configuration or retired_hourly_event:
            return "exit_configuration_not_activated", None
        return None, None
    lineage = next((p for p in current.profiles if p.event_spec_id == event_spec_id), None)
    if lineage is None:
        return "exit_configuration_binding_drift", None
    binding_current = await uow.exit_profiles.get_current_binding(event_spec_id)
    binding = (
        None
        if binding_current is None
        else await uow.exit_profiles.get_binding(binding_current.exit_binding_id)
    )
    if (
        binding is None
        or binding.exit_profile_id != lineage.profile.exit_profile_id
        or binding.exit_profile_semantic_hash != lineage.profile.semantic_hash()
    ):
        return "exit_configuration_binding_drift", None
    snapshot = (
        await uow.exit_profiles.get_ma50_snapshot() if parameters.ma50_enabled else None
    )
    proof = RegimeAdmissionProof(
        configuration_id=current.configuration_id,
        configuration_revision=current.revision,
        event_spec_id=event_spec_id,
        enabled=parameters.ma50_enabled,
        snapshot=snapshot,
    )
    if not parameters.ma50_enabled:
        return None, proof
    if snapshot is None:
        return "ma50_unavailable", proof
    if not snapshot.observed_at_ms <= now_ms < snapshot.valid_until_ms:
        return "ma50_stale", proof
    if not snapshot.allowed_at(now_ms):
        return "ma50_not_bullish", proof
    return None, proof
