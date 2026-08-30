from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_owner_control_role_covers_dynamic_selection_and_exit_profile_writes() -> None:
    source = (
        REPO_ROOT
        / "deploy/owner-console/postgresql/owner-console-control-role.sql"
    ).read_text(encoding="utf-8")

    for table in (
        "brc_strategy_selection_control_current",
        "brc_event_exit_profile_binding_current",
        "brc_exit_policies",
    ):
        assert table in source.split("GRANT UPDATE ON TABLE", 1)[1]

    for table in (
        "brc_event_exit_profile_bindings",
        "brc_event_exit_profile_binding_events",
    ):
        assert table in source.split("GRANT INSERT ON TABLE", 1)[1]
