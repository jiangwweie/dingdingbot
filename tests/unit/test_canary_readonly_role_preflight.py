from pathlib import Path

from scripts.verify_canary_readonly_role_preflight import FORBIDDEN_STATEMENTS


def test_role_preflight_probes_all_dml_classes_without_privilege_mutation():
    source = (
        Path(__file__).resolve().parents[2]
        / "scripts/verify_canary_readonly_role_preflight.py"
    ).read_text(encoding="utf-8")

    assert {statement.split(None, 1)[0] for statement in FORBIDDEN_STATEMENTS} == {
        "INSERT", "UPDATE", "DELETE", "TRUNCATE"
    }
    assert "SET LOCAL ROLE" not in source
    assert "SET TRANSACTION READ ONLY" in source
    assert 'APPLICATION_ROLE = "brc_runtime_app"' in source
    for forbidden in ("CREATE ROLE", "ALTER ROLE", "GRANT ", "PASSWORD"):
        assert forbidden not in source
