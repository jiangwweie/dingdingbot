import json
from pathlib import Path

from scripts import audit_production_runtime_file_io as audit
from scripts import validate_no_runtime_file_authority as no_file_authority


def _audit_source(rel_path: str, source: str) -> list[audit.FileIoOccurrence]:
    return audit.audit_python_file(rel_path=rel_path, text=source)


def test_file_io_audit_flags_recurring_watcher_report_write(tmp_path: Path):
    repo = tmp_path
    script = repo / "scripts" / "runtime_signal_watcher_tick.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
from pathlib import Path

def run(output_dir):
    path = Path(output_dir) / "watcher-tick.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["scripts"])
    flagged = [
        item
        for item in occurrences
        if "frequent_report_write" in item.risk_flags
    ]

    assert flagged
    assert all(item.cleanup_decision == "delete_from_recurring_cadence" for item in flagged)


def test_file_io_audit_flags_action_time_cadence_script_write(
    tmp_path: Path,
):
    repo = tmp_path
    script = repo / "scripts" / "materialize_action_time_ticket.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
from pathlib import Path

def main(output_json):
    Path(output_json).write_text("{}")
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["scripts"])
    flagged = [
        item
        for item in occurrences
        if "frequent_report_write" in item.risk_flags
    ]

    assert flagged
    assert {item.runtime_surface for item in flagged} == {
        "production_cadence_script"
    }
    assert all(item.cleanup_decision == "delete_from_recurring_cadence" for item in flagged)


def test_file_io_audit_flags_owner_readmodel_file_read(tmp_path: Path):
    repo = tmp_path
    readmodel = repo / "src" / "application" / "readmodels" / "trading_console.py"
    readmodel.parent.mkdir(parents=True)
    readmodel.write_text(
        """
import json

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["src"])
    flagged = [
        item
        for item in occurrences
        if "owner_explanation_file_source" in item.risk_flags
    ]

    assert flagged
    assert flagged[0].cleanup_decision == "replace_owner_explanation_source"


def test_file_io_audit_report_exposes_target_policy(tmp_path: Path):
    occurrences = _audit_source(
        "scripts/noop.py",
        "VALUE = 'manual-archive.json'\n",
    )
    report = audit.build_report(occurrences, repo_root=tmp_path, targets=["scripts"])

    assert report["target_policy"]["runtime_file_reads"] == "delete_or_migrate_to_pg"
    assert report["target_policy"]["recurring_file_writes"] == "delete_from_cadence_or_move_to_pg"
    assert report["target_policy"]["historical_material"] == "archive_only_not_runtime_input"


def test_file_io_audit_report_contains_cleanup_plan(tmp_path: Path):
    repo = tmp_path
    script = repo / "scripts" / "runtime_signal_watcher_tick.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
from pathlib import Path

def run(output_dir):
    (Path(output_dir) / "watcher-tick.json").write_text("{}")
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["scripts"])
    report = audit.build_report(occurrences, repo_root=repo, targets=["scripts"])
    phase_ids = {item["phase_id"] for item in report["cleanup_plan"]}

    assert "P0-delete-recurring-json-md-writers" in phase_ids
    assert report["scope_name"] == "production_runtime"


def test_file_io_audit_classifies_output_path_rejection_tests(tmp_path: Path):
    occurrences = _audit_source(
        "tests/unit/test_output_scope.py",
        """
def test_rejects_output_path(module):
    errors = module.validate_changed_output_paths([
        "output/runtime-monitor/latest-old.json",
    ])
    assert errors
""",
    )

    assert {
        item.cleanup_decision
        for item in occurrences
        if "output/runtime-monitor/latest-old.json" in item.path_hints
    } == {"test_rejection_guard"}


def test_file_io_audit_classifies_test_json_write_as_fixture_not_generated_risk(
    tmp_path: Path,
):
    occurrences = _audit_source(
        "tests/unit/test_fixture.py",
        """
def test_writes_tmp_fixture(tmp_path):
    (tmp_path / "fixture.json").write_text("{}")
""",
    )
    fixture_rows = [
        item
        for item in occurrences
        if "fixture.json" in item.path_hints and item.operation == "write"
    ]

    assert fixture_rows
    assert {
        item.risk_flags for item in fixture_rows
    } == {("test_fixture_file_write",)}
    assert all(
        "generated_file_write" not in item.risk_flags for item in fixture_rows
    )


def test_file_io_audit_flags_legacy_artifact_file_io_script(tmp_path: Path):
    repo = tmp_path
    script = repo / "scripts" / "build_runtime_old_evidence_artifact.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
from pathlib import Path

def main():
    output_path = Path("old-evidence.json")
    output_path.write_text("{}")
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["scripts"])
    flagged = [
        item for item in occurrences if "legacy_artifact_file_io" in item.risk_flags
    ]

    assert flagged
    assert {
        item.cleanup_decision for item in flagged
    } == {"delete_current_legacy_artifact_io"}


def test_file_io_audit_does_not_flag_pg_materializer_stdout_json_as_legacy_file_io(
    tmp_path: Path,
):
    repo = tmp_path
    script = repo / "scripts" / "materialize_action_time_ticket.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
import json

def main(report):
    print(json.dumps(report, sort_keys=True))
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["scripts"])

    assert not [
        item for item in occurrences if "legacy_artifact_file_io" in item.risk_flags
    ]
    assert not [
        item for item in occurrences if "file_artifact_cli_interface" in item.risk_flags
    ]


def test_file_io_audit_prints_machine_inventory_to_stdout(tmp_path: Path, capsys):
    assert audit.main(["--repo-root", str(tmp_path)]) == 0
    summary_out = capsys.readouterr().out
    assert "production_runtime_file_io_inventory_generated" in summary_out

    assert audit.main(["--repo-root", str(tmp_path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "production_runtime_file_io_inventory_generated"
    assert report["scope_name"] == "production_runtime"


def test_file_io_audit_ceiling_errors():
    report = {
        "summary": {
            "risk_flags": {
                "blocking_cleanup_required": 2,
                "frequent_report_write": 1,
                "generated_file_write": 3,
                "destructive_file_mutation": 4,
                "unbounded_destructive_file_mutation": 1,
                "owner_explanation_file_source": 1,
            }
        }
    }

    assert audit._ceiling_errors(
        report,
        max_blocking_cleanup_required=2,
        max_frequent_report_write=1,
        max_generated_file_write=3,
        max_destructive_file_mutation=4,
        max_unbounded_destructive_file_mutation=1,
        max_owner_explanation_file_source=1,
    ) == []
    assert audit._ceiling_errors(
        report,
        max_blocking_cleanup_required=1,
        max_frequent_report_write=1,
        max_generated_file_write=3,
        max_destructive_file_mutation=4,
        max_unbounded_destructive_file_mutation=1,
        max_owner_explanation_file_source=1,
    ) == ["blocking_cleanup_required=2 exceeds ceiling 1"]
    assert audit._ceiling_errors(
        report,
        max_blocking_cleanup_required=2,
        max_frequent_report_write=1,
        max_generated_file_write=2,
        max_destructive_file_mutation=4,
        max_unbounded_destructive_file_mutation=1,
        max_owner_explanation_file_source=1,
    ) == ["generated_file_write=3 exceeds ceiling 2"]
    assert audit._ceiling_errors(
        report,
        max_blocking_cleanup_required=2,
        max_frequent_report_write=1,
        max_generated_file_write=3,
        max_destructive_file_mutation=3,
        max_unbounded_destructive_file_mutation=1,
        max_owner_explanation_file_source=1,
    ) == ["destructive_file_mutation=4 exceeds ceiling 3"]
    assert audit._ceiling_errors(
        report,
        max_blocking_cleanup_required=2,
        max_frequent_report_write=1,
        max_generated_file_write=3,
        max_destructive_file_mutation=4,
        max_unbounded_destructive_file_mutation=0,
        max_owner_explanation_file_source=1,
    ) == ["unbounded_destructive_file_mutation=1 exceeds ceiling 0"]


def test_file_io_audit_fail_on_risk_blocks_generated_file_write(tmp_path: Path):
    repo = tmp_path
    script = repo / "scripts" / "runtime_signal_watcher_tick.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
from pathlib import Path

def run():
    Path("output/runtime-monitor/latest-old.json").write_text("{}")
""",
        encoding="utf-8",
    )

    assert audit.main(["--repo-root", str(repo), "--fail-on-risk"]) == 1


def test_file_io_audit_does_not_treat_collection_remove_as_file_delete(
    tmp_path: Path,
):
    repo = tmp_path
    script = repo / "scripts" / "audit_name_stack.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
def visit(stack, name):
    stack.remove(name)
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["scripts"])

    assert not [
        item
        for item in occurrences
        if item.operation == "delete"
        or "destructive_file_mutation" in item.risk_flags
    ]


def test_file_io_audit_does_not_treat_string_replace_as_file_move(tmp_path: Path):
    repo = tmp_path
    script = repo / "scripts" / "normalize_symbol.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
def normalize(text):
    return text.replace("/", "").replace(":USDT", "")
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["scripts"])

    assert not [item for item in occurrences if item.operation == "move"]


def test_file_io_audit_flags_dynamic_json_evidence_write(tmp_path: Path):
    repo = tmp_path
    script = repo / "scripts" / "owner_authorized_close.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
import json
from pathlib import Path

def main(path, result):
    evidence_path = Path(path)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(result, sort_keys=True))
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["scripts"])
    flagged = [
        item for item in occurrences if "runtime_file_write" in item.risk_flags
    ]

    assert flagged
    assert {
        item.cleanup_decision for item in flagged
    } == {"delete_runtime_file_writer"}


def test_file_io_audit_flags_yaml_config_file_interface(tmp_path: Path):
    occurrences = _audit_source(
        "src/application/config_manager.py",
        """
def load(yaml_path):
    with open(yaml_path, "r", encoding="utf-8") as handle:
        data = handle.read()
    with open(yaml_path, "w", encoding="utf-8") as handle:
        handle.write(data)
""",
    )

    assert [
        item for item in occurrences if "runtime_file_read" in item.risk_flags
    ]
    assert [
        item for item in occurrences if "runtime_file_write" in item.risk_flags
    ]


def test_file_io_audit_flags_unbounded_destructive_file_mutation(
    tmp_path: Path,
):
    repo = tmp_path
    script = repo / "scripts" / "unsafe_cleanup.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
def cleanup(path):
    path.unlink()
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["scripts"])
    flagged = [
        item
        for item in occurrences
        if "unbounded_destructive_file_mutation" in item.risk_flags
    ]

    assert flagged
    assert flagged[0].cleanup_decision == "bound_or_delete_mutation"


def test_file_io_audit_classifies_ops_cleanup_as_bounded_mutation(
    tmp_path: Path,
):
    repo = tmp_path
    script = repo / "scripts" / "ops" / "cleanup_once.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
def cleanup(path):
    path.unlink()
""",
        encoding="utf-8",
    )

    occurrences = audit.audit_targets(repo_root=repo, targets=["scripts"])
    cleanup_rows = [
        item for item in occurrences if "destructive_file_mutation" in item.risk_flags
    ]

    assert cleanup_rows
    assert {
        item.cleanup_decision for item in cleanup_rows
    } == {"bounded_file_cleanup"}
    assert not [
        item
        for item in cleanup_rows
        if "unbounded_destructive_file_mutation" in item.risk_flags
    ]


def test_no_runtime_file_authority_validator_blocks_generated_file_write(
    tmp_path: Path,
):
    repo = tmp_path
    dropin_dir = (
        repo
        / "deploy"
        / "systemd"
        / "brc-runtime-signal-watcher.service.d"
    )
    dropin_dir.mkdir(parents=True)
    (dropin_dir / "90-resume-dispatcher-after-refresh.conf").write_text(
        "ExecStartPost=python scripts/runtime_signal_watcher_resume_dispatcher.py --identity-source pg_ticket\n",
        encoding="utf-8",
    )
    (dropin_dir / "80-product-state-refresh.conf").write_text(
        "ExecStartPost=python scripts/run_server_product_state_refresh_sequence.py --mode watcher_tick_summary\n",
        encoding="utf-8",
    )
    (dropin_dir / "85-action-time-refresh-if-needed.conf").write_text(
        "ExecStartPost=python scripts/run_server_product_state_refresh_sequence.py --mode action_time_if_needed\n",
        encoding="utf-8",
    )
    script = repo / "scripts" / "build_daily_live_enablement_table.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
from pathlib import Path

def export(output_json):
    Path("output/runtime-monitor/latest-old.json").write_text("{}")
""",
        encoding="utf-8",
    )

    errors = no_file_authority.validate_no_runtime_file_authority(repo_root=repo)

    assert any("generated_file_write" in error for error in errors)


def test_no_runtime_file_authority_validator_blocks_action_time_file_artifact_cli(
    tmp_path: Path,
):
    repo = tmp_path
    dropin_dir = (
        repo
        / "deploy"
        / "systemd"
        / "brc-runtime-signal-watcher.service.d"
    )
    dropin_dir.mkdir(parents=True)
    (dropin_dir / "90-resume-dispatcher-after-refresh.conf").write_text(
        "ExecStartPost=python scripts/runtime_signal_watcher_resume_dispatcher.py --identity-source pg_ticket\n",
        encoding="utf-8",
    )
    (dropin_dir / "80-product-state-refresh.conf").write_text(
        "ExecStartPost=python scripts/run_server_product_state_refresh_sequence.py --mode watcher_tick_summary\n",
        encoding="utf-8",
    )
    (dropin_dir / "85-action-time-refresh-if-needed.conf").write_text(
        "ExecStartPost=python scripts/run_server_product_state_refresh_sequence.py --mode action_time_if_needed\n",
        encoding="utf-8",
    )
    script = repo / "scripts" / "materialize_ticket_bound_submit.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
def configure(parser):
    parser.add_argument("--output-json")
""",
        encoding="utf-8",
    )

    errors = no_file_authority.validate_no_runtime_file_authority(repo_root=repo)

    assert any("file_artifact_cli_interface" in error for error in errors)


def test_no_runtime_file_authority_validator_blocks_legacy_artifact_file_io(
    tmp_path: Path,
):
    repo = tmp_path
    dropin_dir = (
        repo
        / "deploy"
        / "systemd"
        / "brc-runtime-signal-watcher.service.d"
    )
    dropin_dir.mkdir(parents=True)
    (dropin_dir / "90-resume-dispatcher-after-refresh.conf").write_text(
        "ExecStartPost=python scripts/runtime_signal_watcher_resume_dispatcher.py --identity-source pg_ticket\n",
        encoding="utf-8",
    )
    (dropin_dir / "80-product-state-refresh.conf").write_text(
        "ExecStartPost=python scripts/run_server_product_state_refresh_sequence.py --mode watcher_tick_summary\n",
        encoding="utf-8",
    )
    (dropin_dir / "85-action-time-refresh-if-needed.conf").write_text(
        "ExecStartPost=python scripts/run_server_product_state_refresh_sequence.py --mode action_time_if_needed\n",
        encoding="utf-8",
    )
    script = repo / "scripts" / "build_runtime_old_evidence_artifact.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
from pathlib import Path

def main():
    Path("old-evidence.json").write_text("{}")
""",
        encoding="utf-8",
    )

    errors = no_file_authority.validate_no_runtime_file_authority(repo_root=repo)

    assert any("legacy_artifact_file_io" in error for error in errors)


def test_no_runtime_file_authority_validator_audits_transitive_scripts(
    tmp_path: Path,
):
    repo = tmp_path
    dropin_dir = (
        repo
        / "deploy"
        / "systemd"
        / "brc-runtime-signal-watcher.service.d"
    )
    dropin_dir.mkdir(parents=True)
    (dropin_dir / "90-resume-dispatcher-after-refresh.conf").write_text(
        "ExecStartPost=python scripts/runtime_signal_watcher_resume_dispatcher.py --identity-source pg_ticket\n",
        encoding="utf-8",
    )
    (dropin_dir / "80-product-state-refresh.conf").write_text(
        "ExecStartPost=python scripts/run_server_product_state_refresh_sequence.py --mode watcher_tick_summary\n",
        encoding="utf-8",
    )
    (dropin_dir / "85-action-time-refresh-if-needed.conf").write_text(
        "ExecStartPost=python scripts/run_server_product_state_refresh_sequence.py --mode action_time_if_needed\n",
        encoding="utf-8",
    )
    script = repo / "scripts" / "runtime_signal_watcher_tick.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
from pathlib import Path

def run(output_dir):
    report = Path(output_dir) / "watcher-tick.json"
    report.write_text("{}")
""",
        encoding="utf-8",
    )

    errors = no_file_authority.validate_no_runtime_file_authority(repo_root=repo)

    assert any("frequent_report_write" in error for error in errors)
    assert no_file_authority.validate_no_runtime_file_authority(
        repo_root=repo,
        include_transitive_audit=False,
    ) == []
