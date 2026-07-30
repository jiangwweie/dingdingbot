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
        protected: bool = False,
        external_match: bool = True,
        postflight_external_match: bool | None = None,
    ) -> None:
        self.gate = gate
        self.armed = armed
        self.fail_start = fail_start
        self.protected = protected
        self.external_match = external_match
        self.postflight_external_match = postflight_external_match
        self.external_calls = 0
        self.calls: list[str] = []
        self.fenced = True
        self.entry_active = False

    def certification(self):
        self.calls.append("certification")
        if self.armed:
            return {
                "entry_promotion_pass": False,
                "universe_bootstrap_pass": True,
                "certification_batch_pass": True,
                "flatness_pass": not self.protected,
                "protected_promotion_pass": self.protected,
                "protected_tickets": ([{"ticket_id": "ticket:one"}] if self.protected else []),
                "owner_policy": {
                    "policy_version": 2,
                    "new_entry_submit_enabled": True,
                },
                "capabilities": {"exchange_commands": True},
            }
        return {
            "entry_promotion_pass": self.gate,
            "flatness_pass": not self.protected,
            "protected_promotion_pass": self.protected,
            "protected_tickets": ([{"ticket_id": "ticket:one"}] if self.protected else []),
        }

    def external_state_and_rules_match(self, certification):
        self.calls.append("external")
        self.external_calls += 1
        assert certification["protected_promotion_pass"] is self.protected
        if self.external_calls > 1 and self.postflight_external_match is not None:
            return self.postflight_external_match
        return self.external_match

    def safety_workers_active_stable(self):
        self.calls.append("safety")
        return True

    def entry_is_inactive_disabled_and_fenced(self):
        self.calls.append("preflight")
        return self.fenced and not self.entry_active

    def arm_entry_authority(self):
        self.calls.append("arm")
        self.armed = True
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
        "certification",
        "external",
        "safety",
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


def test_exact_protected_snapshot_can_promote_without_flatness() -> None:
    """Catches the historical protected-release ENTRY dead end."""

    backend = FakePromotionBackend(protected=True)

    assert promote_entry(backend) == "promoted"
    assert backend.calls.index("external") < backend.calls.index("arm")


def test_protected_external_mismatch_keeps_entry_fenced_and_unarmed() -> None:
    backend = FakePromotionBackend(protected=True, external_match=False)

    with pytest.raises(EntryPromotionBlocked, match="exchange_state_or_rule"):
        promote_entry(backend)

    assert "arm" not in backend.calls
    assert backend.fenced is True


def test_final_postflight_mismatch_refences_and_stops_entry() -> None:
    """Catches unfencing after facts drift while Entry starts under the fence."""

    backend = FakePromotionBackend(postflight_external_match=False)

    with pytest.raises(EntryPromotionBlocked, match="final_postflight"):
        promote_entry(backend)

    assert backend.calls[-1] == "restore"
    assert backend.fenced is True
    assert backend.entry_active is False


def test_deployment_state_machine_can_resume_with_entry_already_started_fenced() -> None:
    backend = FakePromotionBackend()
    backend.entry_active = True

    assert promote_entry(backend) == "promoted"
    assert "start" not in backend.calls
    assert backend.calls.count("active_fenced") == 2


def test_active_fenced_entry_reports_expired_promotion_gate_exactly() -> None:
    backend = FakePromotionBackend(gate=False)
    backend.entry_active = True

    with pytest.raises(EntryPromotionBlocked, match="entry_promotion_gate_failed"):
        promote_entry(backend)

    assert backend.calls == [
        "preflight",
        "certification",
        "active_fenced",
    ]
    assert backend.fenced is True
    assert backend.entry_active is True


def test_completed_promotion_is_idempotent_only_for_the_exact_active_state() -> None:
    backend = FakePromotionBackend(armed=True)
    backend.fenced = False
    backend.entry_active = True

    assert promote_entry(backend) == "already_promoted"
    assert backend.calls == ["preflight", "certification", "active"]
