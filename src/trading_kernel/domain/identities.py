"""Canonical immutable identities for one Ticket-bound exposure episode."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


class _FrozenIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def _require_non_blank_strings(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("identity values must be non-blank")
            return normalized
        return value


class NettingDomain(_FrozenIdentity):
    """Exchange position bucket that may own at most one active Ticket."""

    venue_id: str
    account_id: str
    exchange_instrument_id: str
    position_side: Literal["long", "short"]

    def key(self) -> str:
        return ":".join(
            (
                self.venue_id,
                self.account_id,
                self.exchange_instrument_id,
                self.position_side,
            )
        )


class RuntimeIdentity(_FrozenIdentity):
    """Versioned runtime and strategy identity frozen into a Ticket."""

    runtime_profile_id: str
    strategy_group_id: str
    strategy_version_id: str
    event_spec_id: str


class TicketIdentity(_FrozenIdentity):
    """Exact identity shared by every fact, command, event, and projection."""

    ticket_id: str
    exposure_episode_id: str
    signal_event_id: str
    runtime: RuntimeIdentity
    netting_domain: NettingDomain
