from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.trading_kernel import manual_host_bootstrap as host


def filesystem(tmp_path):
    (tmp_path / "etc/brc").mkdir(parents=True)
    (tmp_path / "etc/brc/trading-kernel.write-fenced").touch()
    (tmp_path / "etc/brc/trading-kernel.env").touch()
    release = tmp_path / "release"
    release.mkdir()
    (release / ".brc-runtime-commit").write_text("a" * 40)
    (release / ".brc-schema-revision").write_text("0021_manual_operational_closure")
    (tmp_path / "opt/brc").mkdir(parents=True)
    (tmp_path / "opt/brc/current").symlink_to(release, target_is_directory=True)
    return tmp_path


def facts():
    return [
        {
            "commit": "a" * 40,
            "schema": "0021_manual_operational_closure",
            "paused": True,
            "tickets": True,
            "commands": False,
            "positions": True,
            "incidents": True,
        },
        {
            "active_ticket_ids": ["ticket:exact"],
            "recovery_eligible": True,
            "commands": False,
        },
        {
            "ticket": {
                "ticket_id": "ticket:exact",
                "expected_version": 7,
                "management_revision": 2,
                "reason": "tp1_terminal_attribution_unknown",
                "management_mode": "REVIEW_REQUIRED",
            },
            "incidents": [
                {
                    "incident_id": "cause",
                    "ticket_id": "ticket:exact",
                    "kind": "lifecycle_facts_contradictory",
                }
            ],
        },
    ]


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "extra_ticket",
        "unrelated_incident",
        "wrong_reason",
        "unknown",
        "unpaused",
        "active_writer",
    ],
)
def test_exact_natural_recovery_gate_keeps_ordinary_rejection(
    tmp_path, monkeypatch, fault
):
    import json

    r = facts()
    if fault == "extra_ticket":
        r[1]["active_ticket_ids"].append("other")
    if fault == "unrelated_incident":
        r[2]["incidents"][0]["kind"] = "unknown_order"
    if fault == "wrong_reason":
        r[2]["ticket"]["reason"] = "other"
    if fault == "unknown":
        r[0]["commands"] = True
    if fault == "unpaused":
        r[0]["paused"] = False
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=0 if fault == "active_writer" else 3
        ),
    )
    root = filesystem(tmp_path)
    monkeypatch.setattr(
        host, "read_database", Mock(side_effect=[json.dumps(x) for x in r])
    )
    if fault:
        with pytest.raises(ValueError):
            host.require_stopped_upgrade(
                filesystem_root=root,
                recovery_ticket_ids=("ticket:exact",),
                natural_exit_recovery=True,
            )
    else:
        result = host.require_stopped_upgrade(
            filesystem_root=root,
            recovery_ticket_ids=("ticket:exact",),
            natural_exit_recovery=True,
        )
        assert result["natural_exit_recovery"]["incident_ids"] == ["cause"]
    monkeypatch.setattr(host, "read_database", Mock(return_value=json.dumps(r[0])))
    with pytest.raises(ValueError):
        host.require_stopped_upgrade(filesystem_root=root)


@pytest.mark.parametrize("fault", [None, "wrong_status", "unaccepted_order", "extra_ticket"])
def test_only_exact_accepted_system_exit_can_use_natural_recovery(tmp_path, monkeypatch, fault):
    import json

    r = facts()
    r[1]["recovery_eligible"] = False
    r[2]["ticket"].update(
        status="exit_accepted" if fault != "wrong_status" else "position_protected",
        management_mode="AUTO",
        post_fill_stress_status="passed",
        reason=None,
        exit_order_id="exit-order",
        accepted_exit=fault != "unaccepted_order",
    )
    r[2]["incidents"] = []
    r[0]["incidents"] = False
    if fault == "extra_ticket":
        r[1]["active_ticket_ids"].append("other")
    monkeypatch.setattr(host.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=3))
    monkeypatch.setattr(host, "read_database", Mock(side_effect=[json.dumps(x) for x in r]))
    root = filesystem(tmp_path)
    if fault:
        with pytest.raises(ValueError):
            host.require_stopped_upgrade(
                filesystem_root=root, recovery_ticket_ids=("ticket:exact",), natural_exit_recovery=True,
            )
    else:
        result = host.require_stopped_upgrade(
            filesystem_root=root, recovery_ticket_ids=("ticket:exact",), natural_exit_recovery=True,
        )
        assert result["natural_exit_recovery"]["exit_order_id"] == "exit-order"
