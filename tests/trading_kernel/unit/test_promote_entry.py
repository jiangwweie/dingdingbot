from __future__ import annotations

import pytest

from scripts.trading_kernel.promote_entry import (
    EntryPromotionBlocked,
    LocalEntryPromotionBackend,
    promote_entry,
)


class FakePromotionBackend:
    def __init__(
        self,
        *,
        gate: bool = True,
        armed: bool = False,
        fail_start: bool = False,
        policy_version: int = 7,
        external_match: bool = True,
        postflight_external_match: bool | None = None,
    ) -> None:
        self.gate = gate
        self.armed = armed
        self.fail_start = fail_start
        self.policy_version = policy_version
        self.external_match = external_match
        self.postflight_external_match = postflight_external_match
        self.external_calls = 0
        self.calls: list[str] = []
        self.fenced = True
        self.entry_active = False

    def certification(self):
        self.calls.append("certification")
        if self.armed:
            import time
            return {
                "status": "pass",
                "entry_recovery_valid_until_ms": int(time.time() * 1000) + 5000,
                "entry_recovery_ready": True,
                "entry_recovery_basis_digest": "sha256:" + "a" * 64,
                "owner_entry_resume_authorized": True,
                "entry_promotion_pass": False,
                "universe_bootstrap_pass": True,
                "certification_batch_pass": True,
                "flatness_pass": True,
                "owner_policy": {
                    "policy_version": self.policy_version,
                    "new_entry_submit_enabled": True,
                },
                "capabilities": {"exchange_commands": True},
            }
        return {
            "entry_promotion_pass": self.gate,
            "flatness_pass": True,
        }

    def external_state_and_rules_match(self, certification):
        self.calls.append("external")
        self.external_calls += 1
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
        return {
            "policy_version": self.policy_version,
            "new_entry_submit_enabled": True,
        }

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


def test_promotion_requires_owner_resume_then_starts_and_unfences() -> None:
    backend = FakePromotionBackend(armed=True)

    assert promote_entry(backend) == "promoted"
    assert backend.calls == [
        "preflight",
        "certification",
        "external",
        "safety",
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
    backend = FakePromotionBackend(armed=True, fail_start=True)

    with pytest.raises(EntryPromotionBlocked, match="active_while_fenced"):
        promote_entry(backend)

    assert backend.calls[-1] == "restore"
    assert backend.fenced is True
    assert backend.entry_active is False


def test_armed_service_fenced_retry_resumes_without_creating_another_policy() -> None:
    backend = FakePromotionBackend(armed=True)

    assert promote_entry(backend) == "promoted"
    assert "arm" not in backend.calls


def test_positive_monotonic_policy_version_is_not_fixed_to_v2() -> None:
    backend = FakePromotionBackend(armed=True, policy_version=9)

    assert promote_entry(backend) == "promoted"


def test_nonpositive_armed_policy_version_is_rejected() -> None:
    backend = FakePromotionBackend(armed=True, policy_version=0)

    with pytest.raises(EntryPromotionBlocked, match="promotion_gate"):
        promote_entry(backend)


def test_final_postflight_mismatch_refences_and_stops_entry() -> None:
    """Catches unfencing after facts drift while Entry starts under the fence."""

    backend = FakePromotionBackend(armed=True, postflight_external_match=False)

    with pytest.raises(EntryPromotionBlocked, match="final_postflight"):
        promote_entry(backend)

    assert backend.calls[-1] == "restore"
    assert backend.fenced is True
    assert backend.entry_active is False


def test_deployment_state_machine_can_resume_with_entry_already_started_fenced() -> None:
    backend = FakePromotionBackend(armed=True)
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
    assert "external" in backend.calls and "safety" in backend.calls


def test_paused_policy_is_never_armed_by_operational_tool() -> None:
    backend = FakePromotionBackend(gate=True, armed=False)
    with pytest.raises(EntryPromotionBlocked):
        promote_entry(backend)
    assert "arm" not in backend.calls
    assert "unfence" not in backend.calls


@pytest.mark.parametrize("field", ["entry_recovery_ready", "owner_entry_resume_authorized"])
def test_missing_current_recovery_or_owner_proof_keeps_fence(field: str) -> None:
    backend = FakePromotionBackend(armed=True)
    original = backend.certification
    def certificate():
        result = original()
        result[field] = False
        return result
    backend.certification = certificate
    with pytest.raises(EntryPromotionBlocked):
        promote_entry(backend)
    assert "unfence" not in backend.calls


def test_final_current_universe_or_policy_drift_restores_fence() -> None:
    backend = FakePromotionBackend(armed=True)
    original = backend.certification
    counter = 0
    def certificate():
        nonlocal counter
        counter += 1
        result = original()
        result["entry_recovery_basis_digest"] = "sha256:" + ("a" if counter == 1 else "b") * 64
        return result
    backend.certification = certificate
    with pytest.raises(EntryPromotionBlocked, match="final_postflight"):
        promote_entry(backend)
    assert backend.fenced and "unfence" not in backend.calls


@pytest.mark.parametrize("count", [7, 15, 22, 24])
def test_external_gate_uses_exact_current_members_not_fixed_size(monkeypatch, count):
    import time
    members = [f"member:{index:02}" for index in range(count)]
    certificate = {"flatness_pass": True, "entry_recovery_members": members,
                   "entry_recovery_account_id": "account"}
    probe = {"environment": "live", "venue_id": "binance-usdm", "account_id": "account",
             "account_position_mode": "independent_sides", "account_margin_mode": "cross",
             "non_flat_domain_count": 0, "open_order_domain_count": 0,
             "probe_manifest": members, "instrument_rule_count": count,
             "observed_at_ms": int(time.time()*1000),
             "rules": [{"exchange_instrument_id": m, "configured_leverage": 5,
                        "valid_until_ms": int(time.time()*1000)+5000} for m in members]}
    backend = LocalEntryPromotionBackend(python="python", database_url="not-used")
    monkeypatch.setattr(backend, "_json_script", lambda *_: probe)
    assert backend.external_state_and_rules_match(certificate)


@pytest.mark.parametrize("fault", ["duplicate_rule", "wrong_member", "wrong_account", "expired", "future", "leverage", "orders"])
def test_external_gate_rejects_bad_exact_current_proof(monkeypatch, fault):
    import time
    now = int(time.time()*1000)
    members = [f"member:{index:02}" for index in range(15)]
    certificate = {"flatness_pass": True, "entry_recovery_members": members,
                   "entry_recovery_account_id": "account"}
    probe = {"environment": "live", "venue_id": "binance-usdm", "account_id": "account",
             "account_position_mode": "independent_sides", "account_margin_mode": "cross",
             "non_flat_domain_count": 0, "open_order_domain_count": 0,
             "probe_manifest": members, "instrument_rule_count": 15, "observed_at_ms": now,
             "rules": [{"exchange_instrument_id": m, "configured_leverage": 5,
                        "valid_until_ms": now+5000} for m in members]}
    if fault == "duplicate_rule": probe["rules"].append(dict(probe["rules"][0]))
    elif fault == "wrong_member": probe["probe_manifest"] = [*members[:-1], "wrong"]
    elif fault == "wrong_account": probe["account_id"] = "other"
    elif fault == "expired": probe["rules"][0]["valid_until_ms"] = now-1
    elif fault == "future": probe["observed_at_ms"] = now+60000
    elif fault == "leverage": probe["rules"][0]["configured_leverage"] = 10
    elif fault == "orders": probe["open_order_domain_count"] = 1
    backend = LocalEntryPromotionBackend(python="python", database_url="not-used")
    monkeypatch.setattr(backend, "_json_script", lambda *_: probe)
    assert not backend.external_state_and_rules_match(certificate)


@pytest.mark.parametrize("fault", [None,"missing_commit","wrong_commit","wrong_schema","wrong_account","future_time"])
def test_local_promotion_binds_readonly_evidence_to_deployed_environment(monkeypatch, fault):
    import time
    now=int(time.time()*1000)
    monkeypatch.setenv("TRADING_KERNEL_RUNTIME_COMMIT","a"*40)
    monkeypatch.setenv("TRADING_KERNEL_SCHEMA_REVISION","0009_capacity_policy_v0")
    monkeypatch.setenv("TRADING_KERNEL_ACCOUNT_ID","account")
    certificate={"certified_at_ms":now,"entry_recovery_account_id":"account",
                 "runtime_identity":{"runtime_commit":"a"*40,"schema_revision":"0009_capacity_policy_v0"}}
    if fault=="missing_commit": monkeypatch.delenv("TRADING_KERNEL_RUNTIME_COMMIT")
    elif fault=="wrong_commit": certificate["runtime_identity"]["runtime_commit"]="b"*40
    elif fault=="wrong_schema": certificate["runtime_identity"]["schema_revision"]="0007_exit_profile_authority_v1"
    elif fault=="wrong_account": certificate["entry_recovery_account_id"]="other"
    elif fault=="future_time": certificate["certified_at_ms"]=now+60000
    backend=LocalEntryPromotionBackend(python="python",database_url="not-used")
    monkeypatch.setattr(backend,"_json_script",lambda *_:certificate)
    if fault:
        with pytest.raises(EntryPromotionBlocked,match="deployed_runtime_identity_mismatch"):
            backend.certification()
    else:
        assert backend.certification()==certificate


@pytest.mark.parametrize("fault", ["expired","bad_digest","failed_readonly"])
def test_invalid_final_readonly_evidence_never_unfences(fault):
    import time
    backend=FakePromotionBackend(armed=True)
    original=backend.certification
    def certificate():
        result=original()
        if fault=="expired": result["entry_recovery_valid_until_ms"]=int(time.time()*1000)-1
        elif fault=="bad_digest": result["entry_recovery_basis_digest"]="sha256:not-a-digest"
        else: result["status"]="fail"
        return result
    backend.certification=certificate
    with pytest.raises(EntryPromotionBlocked): promote_entry(backend)
    assert "unfence" not in backend.calls


def test_certification_expiring_during_external_probe_keeps_fence(monkeypatch):
    from scripts.trading_kernel import promote_entry as module
    clock=[1000.0]
    monkeypatch.setattr(module.time,"time",lambda:clock[0])
    backend=FakePromotionBackend(armed=True)
    external=backend.external_state_and_rules_match
    def delayed_probe(certificate):
        valid=external(certificate)
        if backend.external_calls==2:
            clock[0]+=6
        return valid
    backend.external_state_and_rules_match=delayed_probe
    with pytest.raises(EntryPromotionBlocked,match="final_postflight"):
        promote_entry(backend)
    assert backend.fenced and "unfence" not in backend.calls


def test_prepare_owner_resume_starts_worker_without_modifying_paused_policy() -> None:
    backend=FakePromotionBackend(armed=True)
    original=backend.certification
    def paused_evidence():
        facts=original()
        facts["owner_policy"]["new_entry_submit_enabled"]=False
        facts["owner_entry_resume_authorized"]=False
        return facts
    backend.certification=paused_evidence
    assert promote_entry(backend,prepare_owner_resume=True)=="prepared_owner_paused"
    assert "arm" not in backend.calls and "unfence" in backend.calls
    assert backend.entry_active and not backend.fenced
    assert not backend.certification()["owner_policy"]["new_entry_submit_enabled"]


def test_prepare_owner_resume_rejects_a_live_policy() -> None:
    backend=FakePromotionBackend(armed=True)
    with pytest.raises(EntryPromotionBlocked):
        promote_entry(backend,prepare_owner_resume=True)
    assert "unfence" not in backend.calls


def test_prepare_owner_resume_policy_change_during_start_restores_fence():
    backend=FakePromotionBackend(armed=True)
    original=backend.certification
    counter=0
    def changed():
        nonlocal counter
        counter+=1
        facts=original()
        facts["owner_policy"]["new_entry_submit_enabled"]=(counter>1)
        return facts
    backend.certification=changed
    with pytest.raises(EntryPromotionBlocked,match="final_postflight"):
        promote_entry(backend,prepare_owner_resume=True)
    assert backend.fenced and not backend.entry_active
