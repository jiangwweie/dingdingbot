from __future__ import annotations

import pytest

from scripts.trading_kernel.promote_entry import (
    EntryPromotionBlocked,
    promote_entry,
)


class FakePromotionBackend:
    def __init__(
        self,
        *,
        gate: bool = True,
        armed: bool = False,
        fail_start: bool = False,
    ) -> None:
        self.gate = gate
        self.armed = armed
        self.fail_start = fail_start
        self.calls: list[str] = []
        self.fenced = True
        self.entry_active = False

    def certification(self):
        self.calls.append("certification")
        if self.armed:
            return {
                "entry_promotion_pass": False,
                "universe_bootstrap_pass": True,
                "flatness_pass": True,
                "owner_policy": {
                    "policy_version": 2,
                    "new_entry_submit_enabled": True,
                },
                "capabilities": {"exchange_commands": True},
            }
        return {"entry_promotion_pass": self.gate}

    def external_flat_and_rules_match(self):
        self.calls.append("external")
        return True

    def safety_workers_active_stable(self):
        self.calls.append("safety")
        return True

    def entry_is_inactive_disabled_and_fenced(self):
        self.calls.append("preflight")
        return self.fenced and not self.entry_active

    def arm_entry_authority(self):
        self.calls.append("arm")
        return {"policy_version": 2, "new_entry_submit_enabled": True}

    def start_entry_while_fenced(self):
        self.calls.append("start")
        self.entry_active = not self.fail_start

    def entry_is_active_while_fenced(self):
        self.calls.append("active_fenced")
        return self.fenced and self.entry_active

    def remove_entry_fence(self):
        self.calls.append("unfence")
        self.fenced = False

    def entry_is_active(self):
        self.calls.append("active")
        return not self.fenced and self.entry_active

    def restore_entry_fence(self):
        self.calls.append("restore")
        self.fenced = True
        self.entry_active = False


def test_promotion_arms_then_starts_while_fenced_then_unfences() -> None:
    backend = FakePromotionBackend()

    assert promote_entry(backend) == "promoted"
    assert backend.calls == [
        "preflight",
        "certification",
        "external",
        "safety",
        "arm",
        "start",
        "active_fenced",
        "unfence",
        "active",
    ]


def test_gate_failure_never_arms_or_changes_service_state() -> None:
    backend = FakePromotionBackend(gate=False)

    with pytest.raises(EntryPromotionBlocked, match="promotion_gate"):
        promote_entry(backend)

    assert backend.calls == ["preflight", "certification"]


def test_start_failure_restores_fence_and_stops_entry() -> None:
    backend = FakePromotionBackend(fail_start=True)

    with pytest.raises(EntryPromotionBlocked, match="active_while_fenced"):
        promote_entry(backend)

    assert backend.calls[-1] == "restore"
    assert backend.fenced is True
    assert backend.entry_active is False


def test_armed_service_fenced_retry_resumes_without_creating_another_policy() -> None:
    backend = FakePromotionBackend(armed=True)

    assert promote_entry(backend) == "promoted"
    assert "arm" not in backend.calls


def test_completed_promotion_is_idempotent_only_for_the_exact_active_state() -> None:
    backend = FakePromotionBackend(armed=True)
    backend.fenced = False
    backend.entry_active = True

    assert promote_entry(backend) == "already_promoted"
    assert backend.calls == ["preflight", "certification", "active"]
