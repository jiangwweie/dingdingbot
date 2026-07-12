from __future__ import annotations

import json

from scripts import record_runtime_release_activation as script


def test_cli_records_exact_verified_release_without_file_or_trade_flags(
    monkeypatch,
    capsys,
) -> None:
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "status": "runtime_release_activation_completed",
            "runtime_head": kwargs["runtime_head"],
            "exchange_write_called": False,
        }

    monkeypatch.setattr(script, "run_pg_release_activation", fake_run)
    exit_code = script.main(
        [
            "--database-url",
            "postgresql://example.invalid/brc",
            "--runtime-head",
            "f" * 40,
            "--release-name",
            "brc-runtime-governance-test",
            "--verification-ref",
            "postdeploy:passed",
            "--now-ms",
            "1800000000000",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "database_url": "postgresql://example.invalid/brc",
        "runtime_head": "f" * 40,
        "release_name": "brc-runtime-governance-test",
        "verification_ref": "postdeploy:passed",
        "now_ms": 1_800_000_000_000,
    }
    assert json.loads(capsys.readouterr().out)["exchange_write_called"] is False
    args = script._parse_args(
        [
            "--database-url",
            "postgresql://example.invalid/brc",
            "--runtime-head",
            "f" * 40,
            "--release-name",
            "brc-runtime-governance-test",
            "--verification-ref",
            "postdeploy:passed",
        ]
    )
    assert not hasattr(args, "output")
    assert not hasattr(args, "live_submit")
