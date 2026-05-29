"""Read-only account facts model for trial readiness checks.

This module defines the minimal account facts shape needed by trial readiness
without depending on runtime, exchange gateways, order repositories, or live
account APIs.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field


class TrialReadinessAccountFactsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccountFactsSourceType(str, Enum):
    PG_ACCOUNT_FACTS = "pg_account_facts"
    CACHED_SNAPSHOT = "cached_snapshot"
    INJECTED_FAKE = "injected_fake"
    UNAVAILABLE = "unavailable"


class AccountFactsFreshnessStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    MISSING = "missing"
    UNKNOWN = "unknown"


class AccountFactsReconciliationStatus(str, Enum):
    CLEAN = "clean"
    MISMATCH = "mismatch"
    NOT_AVAILABLE = "not_available"
    UNKNOWN = "unknown"


class TrialReadinessAccountFacts(TrialReadinessAccountFactsModel):
    account_id: Optional[str] = Field(default=None, max_length=128)
    source_id: str = Field(default="unavailable", max_length=256)
    source_type: AccountFactsSourceType = AccountFactsSourceType.UNAVAILABLE
    account_equity: Optional[Decimal] = None
    available_margin: Optional[Decimal] = None
    timestamp_ms: Optional[int] = None
    freshness_status: AccountFactsFreshnessStatus = AccountFactsFreshnessStatus.MISSING
    reconciliation_status: AccountFactsReconciliationStatus = (
        AccountFactsReconciliationStatus.UNKNOWN
    )
    read_only_guarantee: bool = True
    external_call_performed: bool = False
    notes: tuple[str, ...] = Field(default_factory=tuple)

    def readiness_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.external_call_performed:
            blockers.append("external account call performed")
        if not self.read_only_guarantee:
            blockers.append("read-only guarantee missing")
        if self.account_equity is None:
            blockers.append("account equity missing")
        if self.available_margin is None:
            blockers.append("available margin missing")
        if self.timestamp_ms is None:
            blockers.append("timestamp missing")
        if self.freshness_status != AccountFactsFreshnessStatus.FRESH:
            blockers.append(f"freshness {self.freshness_status.value}")
        if self.reconciliation_status == AccountFactsReconciliationStatus.MISMATCH:
            blockers.append("account reconciliation mismatch")
        return tuple(blockers)

    @property
    def is_ready(self) -> bool:
        return len(self.readiness_blockers()) == 0


class TrialReadinessAccountFactsSource(Protocol):
    async def read_trial_readiness_account_facts(
        self,
        *,
        candidate_id: str,
        symbol: str,
        side: str,
        generated_at_ms: int,
    ) -> TrialReadinessAccountFacts: ...


class StaticTrialReadinessAccountFactsSource:
    """Deterministic injected source for tests or pre-collected local facts."""

    def __init__(self, facts: TrialReadinessAccountFacts) -> None:
        self._facts = facts

    async def read_trial_readiness_account_facts(
        self,
        *,
        candidate_id: str,
        symbol: str,
        side: str,
        generated_at_ms: int,
    ) -> TrialReadinessAccountFacts:
        return self._facts.model_copy(deep=True)
