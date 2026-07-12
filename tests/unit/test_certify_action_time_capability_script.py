from __future__ import annotations

import json

from scripts import certify_action_time_capability as script


def test_cli_requires_pg_and_prints_stdout_only(monkeypatch, capsys) -> None:
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "status": "action_time_capability_certified",
            "certified_lane_count": 22,
            "first_blocker": None,
            "exchange_write_called": False,
        }

    monkeypatch.setattr(script, "run_pg_certification", fake_run)

    exit_code = script.main(
        [
            "--database-url",
            "postgresql://example.invalid/brc",
            "--runtime-head",
            "d" * 40,
            "--certification-ref",
            "pytest:22-scope",
            "--expected-lane-count",
            "22",
            "--now-ms",
            "1800000000000",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "database_url": "postgresql://example.invalid/brc",
        "runtime_head": "d" * 40,
        "certification_ref": "pytest:22-scope",
        "expected_lane_count": 22,
        "now_ms": 1_800_000_000_000,
    }
    assert json.loads(capsys.readouterr().out)["certified_lane_count"] == 22


def test_cli_has_no_file_output_or_authority_flags() -> None:
    actions = script._parse_args(
        [
            "--database-url",
            "postgresql://example.invalid/brc",
            "--runtime-head",
            "e" * 40,
            "--certification-ref",
            "pytest:shape",
            "--expected-lane-count",
            "22",
        ]
    )

    assert not hasattr(actions, "output")
    assert not hasattr(actions, "apply")
    assert not hasattr(actions, "live_submit")
