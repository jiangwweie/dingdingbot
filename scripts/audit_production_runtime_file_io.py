#!/usr/bin/env python3
"""Inventory runtime file I/O surfaces and classify cleanup risk.

This audit is intentionally conservative. It inventories production code,
runtime scripts, systemd units, and optional tests, then classifies every
detected file read/write/mutation surface for elimination.

The target is not "well documented file I/O". The target is:

    runtime and trading decisions read PG/current services, not files;
    recurring production paths do not write JSON/MD report state;
    valuable historical material is archived, not consumed;
    everything else is deleted.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "brc.production_runtime_file_io_inventory.v1"
DEFAULT_TARGETS = ("scripts", "src", "deploy/systemd")
DEFAULT_EXTRA_TARGETS = ("config",)
GOVERNANCE_TARGETS = ("AGENTS.md", "CLAUDE.md", ".agents")
MIGRATION_TARGETS = ("migrations",)
PRODUCTION_CADENCE_SCRIPT_NAMES = {
    "runtime_signal_watcher_tick.py",
    "run_server_product_state_refresh_sequence.py",
    "build_runtime_account_safe_facts.py",
    "materialize_pg_promotion_action_time_lane.py",
    "materialize_action_time_ticket.py",
    "materialize_action_time_finalgate_preflight.py",
    "materialize_action_time_operation_layer_handoff.py",
    "materialize_ticket_bound_runtime_safety_state.py",
    "materialize_ticket_bound_post_submit_closure.py",
    "publish_runtime_control_current_projections.py",
    "runtime_signal_watcher_resume_dispatcher.py",
    "run_tokyo_runtime_server_monitor.py",
}
FAIL_ON_RISK_FLAGS = (
    "blocking_cleanup_required",
    "frequent_report_write",
    "generated_file_write",
    "legacy_artifact_file_io",
    "owner_explanation_file_source",
    "runtime_file_read",
    "runtime_file_write",
    "suspicious_runtime_file_authority",
)
FILE_ARTIFACT_CLI_TOKENS = {
    "--candidate-pool-json",
    "--control-state-json",
    "--daily-table-json",
    "--facts-json",
    "--goal-status-json",
    "--input-json",
    "--live-facts-json",
    "--output-dir",
    "--output-json",
    "--output-md",
    "--output-owner-progress",
    "--owner-progress",
    "--report-dir",
    "--resume-pack-json",
    "--runtime-monitor-dir",
}
LEGACY_ARTIFACT_SCRIPT_NAME_TOKENS = {
    "artifact",
    "evidence",
    "fixture",
    "from_reports",
    "handoff",
    "local_monitor",
    "packet",
    "proof",
    "proposal",
    "readiness",
    "replay",
}
SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "output",
    "reports",
    "htmlcov",
}
PYTHON_SUFFIXES = {".py"}
TEXT_SUFFIXES = {".conf", ".service", ".timer", ".sh", ".json", ".md", ".yaml", ".yml"}
PATH_LITERAL_RE = re.compile(
    r"""(?P<path>(?:/home/ubuntu/|/Users/|\.{0,2}/|[A-Za-z0-9_-]+/)[^"'\s,)]+(?:\.jsonl|\.tar\.gz|\.json|\.md|\.env|\.yaml|\.yml|\.toml|\.log|\.txt|\.csv|\.gz)|[^"'\s,)]+(?:\.jsonl|\.tar\.gz|\.json|\.md|\.env|\.yaml|\.yml|\.toml|\.log|\.txt|\.csv|\.gz))"""
)
CLI_IO_OPTIONS = {
    "--input-json": "read",
    "--output-json": "write",
    "--output": "write",
    "--output-dir": "directory_write",
    "--output-owner-progress": "write",
    "--output-md": "write",
    "--owner-progress": "write",
    "--archive-dir": "directory_write",
    "--backup-dir": "directory_write",
    "--manifest": "read",
    "--env-file": "read",
    "--input": "read",
    "--report-dir": "directory_write",
    "--runtime-monitor-dir": "directory_write",
    "--registry-json": "read",
    "--tier-policy-json": "read",
    "--policy-json": "read",
    "--strategy-json": "read",
    "--facts-json": "read",
    "--resume-pack-json": "read",
    "--candidate-pool-json": "read",
    "--daily-table-json": "read",
    "--goal-status-json": "read",
    "--control-state-json": "read",
}


@dataclass(frozen=True)
class FileIoOccurrence:
    path: str
    line: int
    operation: str
    api: str
    path_hints: tuple[str, ...]
    runtime_surface: str
    role_guess: str
    risk_flags: tuple[str, ...]
    cleanup_decision: str
    recommended_action: str
    source_excerpt: str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--include-docs", action="store_true")
    parser.add_argument("--include-governance", action="store_true")
    parser.add_argument("--include-migrations", action="store_true")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Scan production, config, migrations, tests, current docs, and agent constraints.",
    )
    parser.add_argument(
        "--fail-on-risk",
        action="store_true",
        help="Exit non-zero when production file authority or recurring report-write risk exists.",
    )
    parser.add_argument(
        "--max-blocking-cleanup-required",
        type=int,
        default=None,
        help="Debt ceiling for blocking cleanup risk. Use 0 for strict cleanup.",
    )
    parser.add_argument(
        "--max-frequent-report-write",
        type=int,
        default=None,
        help="Debt ceiling for recurring report-write risk.",
    )
    parser.add_argument(
        "--max-owner-explanation-file-source",
        type=int,
        default=None,
        help="Debt ceiling for Owner-facing file-source risk.",
    )
    parser.add_argument(
        "--max-generated-file-write",
        type=int,
        default=None,
        help="Debt ceiling for JSON/MD or generated-file write risk.",
    )
    parser.add_argument(
        "--max-runtime-file-read",
        type=int,
        default=None,
        help="Debt ceiling for current runtime/config file reads.",
    )
    parser.add_argument(
        "--max-runtime-file-write",
        type=int,
        default=None,
        help="Debt ceiling for current runtime/config file writes.",
    )
    parser.add_argument(
        "--max-file-artifact-cli-interface",
        type=int,
        default=None,
        help="Debt ceiling for CLI file artifact input/output interfaces.",
    )
    parser.add_argument(
        "--max-legacy-artifact-file-io",
        type=int,
        default=None,
        help="Debt ceiling for current scripts that preserve legacy artifact/proof/evidence file I/O.",
    )
    parser.add_argument(
        "--max-test-fixture-file-write",
        type=int,
        default=None,
        help="Debt ceiling for test-local JSON/MD fixture file writes.",
    )
    parser.add_argument(
        "--max-manual-agent-tool-file-write",
        type=int,
        default=None,
        help="Debt ceiling for manual agent tool generated file writes.",
    )
    parser.add_argument(
        "--max-destructive-file-mutation",
        type=int,
        default=None,
        help="Debt ceiling for delete/delete-tree file mutation risk.",
    )
    parser.add_argument(
        "--max-unbounded-destructive-file-mutation",
        type=int,
        default=None,
        help="Debt ceiling for delete/delete-tree mutations that are not classified as bounded cleanup.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    targets = list(DEFAULT_TARGETS) + list(DEFAULT_EXTRA_TARGETS)
    if args.all or args.include_migrations:
        targets.extend(MIGRATION_TARGETS)
    if args.all or args.include_governance:
        targets.extend(GOVERNANCE_TARGETS)
    if args.all or args.include_tests:
        targets.append("tests")
    if args.all or args.include_docs:
        targets.append("docs/current")

    occurrences = audit_targets(repo_root=repo_root, targets=targets)
    report = build_report(occurrences, repo_root=repo_root, targets=targets)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(report["status"])
        print(f"occurrence_count={report['occurrence_count']}")
        print(f"suspicious_runtime_file_authority={report['summary']['risk_flags'].get('suspicious_runtime_file_authority', 0)}")
        print(f"frequent_report_write={report['summary']['risk_flags'].get('frequent_report_write', 0)}")
    ceiling_errors = _ceiling_errors(
        report,
        max_blocking_cleanup_required=args.max_blocking_cleanup_required,
        max_frequent_report_write=args.max_frequent_report_write,
        max_owner_explanation_file_source=args.max_owner_explanation_file_source,
        max_generated_file_write=args.max_generated_file_write,
        max_runtime_file_read=args.max_runtime_file_read,
        max_runtime_file_write=args.max_runtime_file_write,
        max_file_artifact_cli_interface=args.max_file_artifact_cli_interface,
        max_legacy_artifact_file_io=args.max_legacy_artifact_file_io,
        max_test_fixture_file_write=args.max_test_fixture_file_write,
        max_manual_agent_tool_file_write=args.max_manual_agent_tool_file_write,
        max_destructive_file_mutation=args.max_destructive_file_mutation,
        max_unbounded_destructive_file_mutation=(
            args.max_unbounded_destructive_file_mutation
        ),
    )
    for error in ceiling_errors:
        print(f"ERROR: {error}")
    if ceiling_errors:
        return 1
    if args.fail_on_risk and any(
        report["summary"]["risk_flags"].get(flag, 0)
        for flag in FAIL_ON_RISK_FLAGS
    ):
        return 1
    return 0


def audit_targets(*, repo_root: Path, targets: Iterable[str]) -> list[FileIoOccurrence]:
    occurrences: list[FileIoOccurrence] = []
    for target in targets:
        root = repo_root / target
        if not root.exists():
            continue
        if root.is_file():
            occurrences.extend(audit_file(root, repo_root=repo_root))
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or _should_skip(path, repo_root=repo_root):
                continue
            if path.suffix in PYTHON_SUFFIXES or path.suffix in TEXT_SUFFIXES:
                occurrences.extend(audit_file(path, repo_root=repo_root))
    return sorted(occurrences, key=lambda item: (item.path, item.line, item.api))


def audit_file(path: Path, *, repo_root: Path) -> list[FileIoOccurrence]:
    rel_path = _rel(path, repo_root)
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".py":
        return audit_python_file(rel_path=rel_path, text=text)
    return audit_text_file(rel_path=rel_path, text=text)


def audit_python_file(*, rel_path: str, text: str) -> list[FileIoOccurrence]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return audit_text_file(rel_path=rel_path, text=text)
    visitor = FileIoVisitor(rel_path=rel_path, text=text)
    visitor.visit(tree)
    return visitor.occurrences


def audit_text_file(*, rel_path: str, text: str) -> list[FileIoOccurrence]:
    occurrences: list[FileIoOccurrence] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        path_hints = _path_hints(stripped)
        operation = _operation_from_text(stripped)
        if operation == "none" and not path_hints:
            continue
        if operation == "none":
            operation = "path_literal"
        occurrences.append(
            _occurrence(
                rel_path=rel_path,
                lineno=lineno,
                operation=operation,
                api="text_scan",
                path_hints=path_hints,
                source_excerpt=stripped,
            )
        )
    return occurrences


class FileIoVisitor(ast.NodeVisitor):
    def __init__(self, *, rel_path: str, text: str) -> None:
        self.rel_path = rel_path
        self.text = text
        self.lines = text.splitlines()
        self.occurrences: list[FileIoOccurrence] = []
        self.path_var_hints: dict[str, tuple[str, ...]] = {}

    def visit_Call(self, node: ast.Call) -> Any:  # noqa: ANN401
        api = _call_name(node.func)
        operation = _operation_from_call(api, node)
        source = self._line_source(node) or api
        path_hints = _path_hints(source)
        if not path_hints:
            path_hints = self.path_var_hints.get(api.split(".", 1)[0], ())
        if operation in {"parse_json", "serialize_json"} and not path_hints:
            self.generic_visit(node)
            return
        if operation != "none" or path_hints:
            if operation == "none":
                operation = "path_literal"
            self.occurrences.append(
                _occurrence(
                    rel_path=self.rel_path,
                    lineno=getattr(node, "lineno", 0),
                    operation=operation,
                    api=api,
                    path_hints=path_hints,
                    source_excerpt=_compact(source),
                )
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:  # noqa: ANN401
        source = self._line_source(node)
        path_hints = _path_hints(source)
        if path_hints:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.path_var_hints[target.id] = path_hints
            self.occurrences.append(
                _occurrence(
                    rel_path=self.rel_path,
                    lineno=getattr(node, "lineno", 0),
                    operation="path_literal",
                    api="assignment",
                    path_hints=path_hints,
                    source_excerpt=_compact(source),
                )
            )
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:  # noqa: ANN401
        source = self._line_source(node)
        path_hints = _path_hints(source)
        if path_hints:
            if isinstance(node.target, ast.Name):
                self.path_var_hints[node.target.id] = path_hints
            self.occurrences.append(
                _occurrence(
                    rel_path=self.rel_path,
                    lineno=getattr(node, "lineno", 0),
                    operation="path_literal",
                    api="annotated_assignment",
                    path_hints=path_hints,
                    source_excerpt=_compact(source),
                )
            )
        self.generic_visit(node)

    def _line_source(self, node: ast.AST) -> str:
        lineno = int(getattr(node, "lineno", 0) or 0)
        end_lineno = int(getattr(node, "end_lineno", lineno) or lineno)
        if lineno <= 0 or lineno > len(self.lines):
            return ""
        if end_lineno < lineno:
            end_lineno = lineno
        end_lineno = min(end_lineno, lineno + 4, len(self.lines))
        return " ".join(self.lines[lineno - 1 : end_lineno])


def build_report(
    occurrences: list[FileIoOccurrence],
    *,
    repo_root: Path,
    targets: list[str],
) -> dict[str, Any]:
    operation_counts = Counter(item.operation for item in occurrences)
    role_counts = Counter(item.role_guess for item in occurrences)
    cleanup_counts = Counter(item.cleanup_decision for item in occurrences)
    risk_counts: Counter[str] = Counter()
    for item in occurrences:
        risk_counts.update(item.risk_flags)
    suspicious = [
        asdict(item)
        for item in occurrences
        if "suspicious_runtime_file_authority" in item.risk_flags
        or "frequent_report_write" in item.risk_flags
        or "owner_explanation_file_source" in item.risk_flags
    ]
    scope_name = (
        "full_repo"
        if any(
            target in {"tests", "docs/current", ".agents", "migrations", "AGENTS.md", "CLAUDE.md"}
            for target in targets
        )
        else "production_runtime"
    )
    file_summary = _file_summary(occurrences)
    read_ops = {"read", "read_write"}
    write_ops = {"write", "read_write", "directory_write", "copy", "move"}
    mutation_ops = {"delete", "delete_tree", "move", "copy"}
    return {
        "schema": SCHEMA,
        "status": "production_runtime_file_io_inventory_generated",
        "scope_name": scope_name,
        "repo_root": str(repo_root),
        "targets": targets,
        "occurrence_count": len(occurrences),
        "summary": {
            "operations": dict(sorted(operation_counts.items())),
            "role_guess": dict(sorted(role_counts.items())),
            "cleanup_decision": dict(sorted(cleanup_counts.items())),
            "risk_flags": dict(sorted(risk_counts.items())),
            "runtime_surface": dict(
                sorted(Counter(item.runtime_surface for item in occurrences).items())
            ),
            "operation_by_runtime_surface": _operation_by_runtime_surface(occurrences),
        },
        "suspicious_occurrences": suspicious[:500],
        "file_summary": file_summary,
        "read_inventory": [
            asdict(item) for item in occurrences if item.operation in read_ops
        ],
        "write_inventory": [
            asdict(item) for item in occurrences if item.operation in write_ops
        ],
        "mutation_inventory": [
            asdict(item) for item in occurrences if item.operation in mutation_ops
        ],
        "performance_risk": _performance_risk(occurrences),
        "cleanup_plan": _cleanup_plan(occurrences),
        "occurrences": [asdict(item) for item in occurrences],
        "target_policy": {
            "runtime_file_reads": "delete_or_migrate_to_pg",
            "recurring_file_writes": "delete_from_cadence_or_move_to_pg",
            "historical_material": "archive_only_not_runtime_input",
            "json_md_exports": "temporary_diagnostic_only_until_deleted",
            "legacy_file_artifact_scripts": "delete_current_script_or_move_to_archive_only_provenance",
        },
    }


def _file_summary(occurrences: list[FileIoOccurrence]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_file: dict[str, list[FileIoOccurrence]] = {}
    for item in occurrences:
        by_file.setdefault(item.path, []).append(item)
    for path, items in sorted(by_file.items()):
        risk_flags: Counter[str] = Counter()
        cleanup: Counter[str] = Counter()
        operations = Counter(item.operation for item in items)
        roles = Counter(item.role_guess for item in items)
        surfaces = Counter(item.runtime_surface for item in items)
        path_hints: Counter[str] = Counter()
        for item in items:
            risk_flags.update(item.risk_flags)
            cleanup[item.cleanup_decision] += 1
            path_hints.update(item.path_hints)
        primary_cleanup = cleanup.most_common(1)[0][0] if cleanup else "review"
        rows.append(
            {
                "path": path,
                "occurrence_count": len(items),
                "runtime_surface": surfaces.most_common(1)[0][0],
                "operations": dict(sorted(operations.items())),
                "role_guess": dict(sorted(roles.items())),
                "risk_flags": dict(sorted(risk_flags.items())),
                "cleanup_decision": dict(sorted(cleanup.items())),
                "primary_cleanup_decision": primary_cleanup,
                "top_path_hints": [
                    {"path_hint": hint, "count": count}
                    for hint, count in path_hints.most_common(12)
                ],
                "recommended_action": _file_recommended_action(
                    primary_cleanup=primary_cleanup,
                    risk_flags=set(risk_flags),
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            0 if row["risk_flags"] else 1,
            -int(row["occurrence_count"]),
            row["path"],
        ),
    )


def _operation_by_runtime_surface(
    occurrences: list[FileIoOccurrence],
) -> dict[str, dict[str, int]]:
    by_surface: dict[str, Counter[str]] = {}
    for item in occurrences:
        by_surface.setdefault(item.runtime_surface, Counter())[item.operation] += 1
    return {
        surface: dict(sorted(counter.items()))
        for surface, counter in sorted(by_surface.items())
    }


def _performance_risk(occurrences: list[FileIoOccurrence]) -> dict[str, Any]:
    rows = [
        item
        for item in occurrences
        if "frequent_report_write" in item.risk_flags
        or item.runtime_surface
        in {"watcher_tick", "product_state_refresh_orchestrator", "server_monitor"}
        and item.operation in {"write", "directory_write"}
        and _looks_like_report_state_write(
            joined=" ".join(item.path_hints),
            source=item.source_excerpt.lower(),
            role_guess=item.role_guess,
        )
    ]
    by_file = Counter(item.path for item in rows)
    return {
        "status": "risk_present" if rows else "clear",
        "risk_count": len(rows),
        "file_count": len(by_file),
        "no_signal_tick_file_growth_target": "zero_recurring_json_md_report_growth",
        "pg_row_growth_target": (
            "append only when new fact/signal/promotion/ticket/monitor event exists; "
            "current projection updates are bounded by one row per projection owner"
        ),
        "cpu_heavy_trigger_policy": (
            "recurring timers must not rebuild broad JSON/MD report chains; "
            "heavy diagnostics move to manual archive-only ops commands"
        ),
        "disk_retention_policy": (
            "production cadence writes PG current state, not report directories; "
            "archive-only commands must declare retention before writing files"
        ),
        "top_files": [
            {"path": path, "occurrence_count": count}
            for path, count in by_file.most_common(20)
        ],
        "occurrences": [asdict(item) for item in rows[:200]],
    }


def _file_recommended_action(
    *,
    primary_cleanup: str,
    risk_flags: set[str],
) -> str:
    if "frequent_report_write" in risk_flags:
        return "delete recurring JSON/MD writer from timer cadence or replace with PG event/current projection writes"
    if "owner_explanation_file_source" in risk_flags:
        return "delete Owner-facing file read and read PG Owner Explanation projection"
    if "suspicious_runtime_file_authority" in risk_flags:
        return "delete production reader or migrate source to PG; archive old files only"
    if "legacy_artifact_file_io" in risk_flags:
        return "delete current artifact/proof/evidence file-I/O script or move historical value to archive-only provenance"
    if "file_artifact_cli_interface" in risk_flags:
        return "delete JSON/MD/report file CLI interface; use PG/current services or stdout summaries"
    if primary_cleanup == "seed_then_pg":
        return "import once into PG seed/projection tables, then archive or delete source file"
    if primary_cleanup == "delete_reader":
        return "delete generated-output reader; rebuild from PG or archive-only diagnostics"
    if primary_cleanup == "delete_writer_or_archive_only":
        return "delete writer from normal path; retain only explicit archive-only command if useful"
    if primary_cleanup == "bounded_file_cleanup":
        return "keep only when test-local or dry-run guarded one-shot ops cleanup"
    if primary_cleanup == "bound_or_delete_mutation":
        return "delete this mutation path or add explicit retention, dry-run, one-shot, and scope guardrails"
    return "review manually and classify as PG source, archive-only, test fixture, or deletion"


def _cleanup_plan(occurrences: list[FileIoOccurrence]) -> list[dict[str, Any]]:
    phases = [
        (
            "P0-delete-recurring-json-md-writers",
            lambda item: "frequent_report_write" in item.risk_flags,
            "Remove recurring JSON/MD writers from watcher/product refresh cadence or replace with PG rows.",
        ),
        (
            "P0-replace-owner-explanation-file-reads",
            lambda item: "owner_explanation_file_source" in item.risk_flags,
            "Source Owner-facing explanation from PG readmodels only.",
        ),
        (
            "P0-delete-or-migrate-runtime-file-readers",
            lambda item: "suspicious_runtime_file_authority" in item.risk_flags,
            "Delete production file readers or replace them with PG/current service reads.",
        ),
        (
            "P0-delete-current-runtime-file-readers",
            lambda item: "runtime_file_read" in item.risk_flags,
            "Delete current runtime/config file readers; migrate useful semantics to PG/current services.",
        ),
        (
            "P0-delete-current-runtime-file-writers",
            lambda item: "runtime_file_write" in item.risk_flags,
            "Delete current runtime/config file writers; persist useful current semantics in PG/current services.",
        ),
        (
            "P0-delete-current-legacy-artifact-file-io",
            lambda item: "legacy_artifact_file_io" in item.risk_flags,
            "Delete current artifact/proof/evidence file-I/O scripts or move historical value to archive-only provenance.",
        ),
        (
            "P0-delete-file-artifact-cli-interfaces",
            lambda item: "file_artifact_cli_interface" in item.risk_flags,
            "Remove CLI JSON/MD/report file interfaces from current scripts; use PG/current services or stdout summaries.",
        ),
        (
            "P1-import-seed-files-then-delete-runtime-readers",
            lambda item: item.cleanup_decision == "seed_then_pg",
            "Import seed/config semantics into PG and remove runtime readers.",
        ),
        (
            "P1-delete-generated-export-readers",
            lambda item: item.cleanup_decision == "delete_reader",
            "Delete readers of generated outputs; rebuild from PG or move to archive-only tooling.",
        ),
        (
            "P1-archive-or-delete-generated-writers",
            lambda item: item.cleanup_decision == "delete_writer_or_archive_only",
            "Delete generated writers or move them to explicit manual archive commands.",
        ),
        (
            "P1-archive-legacy-dry-run-artifacts",
            lambda item: "legacy_dry_run_artifact" in item.risk_flags,
            "Remove dry-run audit artifacts from production and keep only archive/test-rejection references.",
        ),
        (
            "P2-bound-ops-file-mutations",
            lambda item: item.cleanup_decision
            in {"bounded_file_cleanup", "bound_or_delete_mutation"},
            "Keep file mutations only when test-local or dry-run guarded one-shot ops cleanup.",
        ),
    ]
    plan: list[dict[str, Any]] = []
    for phase_id, predicate, goal in phases:
        rows = [item for item in occurrences if predicate(item)]
        if not rows:
            continue
        by_file = Counter(item.path for item in rows)
        plan.append(
            {
                "phase_id": phase_id,
                "goal": goal,
                "occurrence_count": len(rows),
                "file_count": len(by_file),
                "top_files": [
                    {"path": path, "occurrence_count": count}
                    for path, count in by_file.most_common(20)
                ],
                "example_occurrences": [
                    asdict(item)
                    for item in sorted(rows, key=lambda x: (x.path, x.line))[:20]
                ],
            }
        )
    return plan


def _ceiling_errors(
    report: dict[str, Any],
    *,
    max_blocking_cleanup_required: int | None,
    max_frequent_report_write: int | None,
    max_owner_explanation_file_source: int | None,
    max_generated_file_write: int | None = None,
    max_runtime_file_read: int | None = None,
    max_runtime_file_write: int | None = None,
    max_file_artifact_cli_interface: int | None = None,
    max_legacy_artifact_file_io: int | None = None,
    max_test_fixture_file_write: int | None = None,
    max_manual_agent_tool_file_write: int | None = None,
    max_destructive_file_mutation: int | None = None,
    max_unbounded_destructive_file_mutation: int | None = None,
) -> list[str]:
    risk_flags = report["summary"]["risk_flags"]
    checks = {
        "blocking_cleanup_required": max_blocking_cleanup_required,
        "frequent_report_write": max_frequent_report_write,
        "owner_explanation_file_source": max_owner_explanation_file_source,
        "generated_file_write": max_generated_file_write,
        "file_artifact_cli_interface": max_file_artifact_cli_interface,
        "legacy_artifact_file_io": max_legacy_artifact_file_io,
        "runtime_file_read": max_runtime_file_read,
        "runtime_file_write": max_runtime_file_write,
        "test_fixture_file_write": max_test_fixture_file_write,
        "manual_agent_tool_file_write": max_manual_agent_tool_file_write,
        "destructive_file_mutation": max_destructive_file_mutation,
        "unbounded_destructive_file_mutation": (
            max_unbounded_destructive_file_mutation
        ),
    }
    errors = []
    for key, limit in checks.items():
        if limit is None:
            continue
        actual = int(risk_flags.get(key, 0) or 0)
        if actual > limit:
            errors.append(f"{key}={actual} exceeds ceiling {limit}")
    return errors


def _operation_from_call(api: str, node: ast.Call) -> str:
    if api in {"read_text", "read_bytes"} or api.endswith(".read_text") or api.endswith(".read_bytes"):
        return "read"
    if api in {"write_text", "write_bytes"} or api.endswith(".write_text") or api.endswith(".write_bytes"):
        return "write"
    if api.endswith(".open") or api == "open" or api.endswith(".gzip.open"):
        return _operation_from_open_mode(node)
    if api.endswith(".json.load") or api == "json.load":
        return "read"
    if api.endswith(".json.dump") or api == "json.dump":
        return "write"
    if api.endswith(".json.loads") or api == "json.loads":
        return "parse_json"
    if api.endswith(".json.dumps") or api == "json.dumps":
        return "serialize_json"
    if api.endswith(".unlink") or api == "os.remove":
        return "delete"
    if api.endswith(".rmtree") or api == "shutil.rmtree":
        return "delete_tree"
    if api.endswith(".rename") or api in {"os.rename", "os.replace"}:
        return "move"
    if api.endswith(".mkdir") or api == "os.makedirs":
        return "directory_write"
    if api in {"shutil.copy", "shutil.copy2", "shutil.copyfile"}:
        return "copy"
    if api.endswith(".add_argument"):
        return _operation_from_cli_argument(node)
    return "none"


def _operation_from_text(text: str) -> str:
    if "ExecStart" in text or "ExecStartPost" in text:
        return "process_spawn"
    for token, operation in CLI_IO_OPTIONS.items():
        if token in text:
            return operation
    return "none"


def _operation_from_cli_argument(node: ast.Call) -> str:
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if arg.value in CLI_IO_OPTIONS:
                return CLI_IO_OPTIONS[arg.value]
    return "none"


def _operation_from_open_mode(node: ast.Call) -> str:
    mode = "r"
    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
        mode = str(node.args[1].value)
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            mode = str(keyword.value.value)
    if any(flag in mode for flag in ("w", "a", "x", "+")):
        if "r" in mode and "+" in mode:
            return "read_write"
        return "write"
    return "read"


def _occurrence(
    *,
    rel_path: str,
    lineno: int,
    operation: str,
    api: str,
    path_hints: tuple[str, ...],
    source_excerpt: str,
) -> FileIoOccurrence:
    runtime_surface = _runtime_surface(rel_path)
    role_guess = _role_guess(operation, path_hints, rel_path)
    risk_flags = _risk_flags(
        operation,
        path_hints,
        rel_path,
        runtime_surface,
        role_guess,
        source_excerpt,
    )
    cleanup_decision, recommended_action = _cleanup(operation, role_guess, risk_flags)
    if _is_test_rejection_guard(
        runtime_surface=runtime_surface,
        role_guess=role_guess,
        source_excerpt=source_excerpt,
    ):
        risk_flags = tuple(
            flag
            for flag in risk_flags
            if flag
            not in {
                "generated_file_write",
                "file_export_to_delete_or_archive",
            }
        )
        cleanup_decision = "test_rejection_guard"
        recommended_action = (
            "Keep only as a negative test proving old file paths are rejected; "
            "do not use as current runtime, Owner explanation, or fixture source."
        )
    return FileIoOccurrence(
        path=rel_path,
        line=lineno,
        operation=operation,
        api=api,
        path_hints=path_hints,
        runtime_surface=runtime_surface,
        role_guess=role_guess,
        risk_flags=risk_flags,
        cleanup_decision=cleanup_decision,
        recommended_action=recommended_action,
        source_excerpt=source_excerpt,
    )


def _runtime_surface(rel_path: str) -> str:
    if rel_path.startswith("deploy/systemd/"):
        return "production_systemd"
    if rel_path.endswith("runtime_signal_watcher_tick.py"):
        return "watcher_tick"
    if rel_path.endswith("run_server_product_state_refresh_sequence.py"):
        return "product_state_refresh_orchestrator"
    if rel_path.endswith("run_tokyo_runtime_server_monitor.py"):
        return "server_monitor"
    if rel_path.startswith("scripts/"):
        name = rel_path.rsplit("/", 1)[-1]
        if name in PRODUCTION_CADENCE_SCRIPT_NAMES:
            return "production_cadence_script"
    if "materialize_action_time" in rel_path or "materialize_ticket_bound" in rel_path:
        return "action_time_or_submit_chain"
    if "readmodels/trading_console.py" in rel_path:
        return "owner_console_readmodel"
    if rel_path.startswith("scripts/ops/"):
        return "one_shot_ops"
    if rel_path.startswith("tests/"):
        return "test"
    if rel_path.startswith("docs/") or rel_path.startswith("config/"):
        return "governance_or_config"
    if rel_path.startswith("scripts/"):
        return "script"
    if rel_path.startswith("src/"):
        return "application"
    return "unknown"


def _role_guess(operation: str, path_hints: tuple[str, ...], rel_path: str) -> str:
    joined = " ".join(path_hints)
    if operation in {"serialize_json", "parse_json"} and not path_hints:
        return "in_memory_json_payload"
    if any(token in joined for token in ("output/runtime-monitor", "reports/", "/reports/")):
        if operation in {"write", "directory_write", "copy", "move", "delete", "delete_tree"}:
            return "generated_export_or_report_writer"
        return "generated_export_or_report_reader"
    if "docs/current" in joined and ".json" in joined:
        return "repo_machine_config_or_seed"
    if ".md" in joined:
        return "markdown_artifact_or_doc"
    if ".env" in joined:
        return "environment_config"
    if operation in {"write", "directory_write"}:
        return "file_writer"
    if operation == "read":
        return "file_reader"
    if operation in {"delete", "delete_tree", "move", "copy"}:
        return "file_lifecycle_mutation"
    return "path_or_json_reference"


def _risk_flags(
    operation: str,
    path_hints: tuple[str, ...],
    rel_path: str,
    runtime_surface: str,
    role_guess: str,
    source_excerpt: str,
) -> tuple[str, ...]:
    flags: set[str] = set()
    joined = " ".join(path_hints)
    source = source_excerpt.lower()
    production_surface = runtime_surface in {
        "production_systemd",
        "watcher_tick",
        "product_state_refresh_orchestrator",
        "server_monitor",
        "production_cadence_script",
        "owner_console_readmodel",
        "action_time_or_submit_chain",
    }
    if production_surface and operation == "read" and role_guess in {
        "generated_export_or_report_reader",
        "markdown_artifact_or_doc",
        "repo_machine_config_or_seed",
    }:
        flags.add("suspicious_runtime_file_authority")
        flags.add("blocking_cleanup_required")
    if runtime_surface == "owner_console_readmodel" and operation == "read":
        flags.add("owner_explanation_file_source")
        flags.add("blocking_cleanup_required")
    if runtime_surface in {
        "watcher_tick",
        "product_state_refresh_orchestrator",
        "server_monitor",
        "production_cadence_script",
    } and operation in {
        "write",
        "directory_write",
    } and _looks_like_report_state_write(
        joined=joined,
        source=source,
        role_guess=role_guess,
    ):
        flags.add("frequent_report_write")
        flags.add("blocking_cleanup_required")
    if "latest-" in joined and operation == "read":
        flags.add("latest_file_read")
    if "runtime-dry-run-audit-chain" in joined:
        flags.add("legacy_dry_run_artifact")
    if ".md" in joined and production_surface and operation == "read":
        flags.add("runtime_markdown_read")
    if operation in {"delete", "delete_tree"}:
        flags.add("destructive_file_mutation")
        if _is_bounded_destructive_file_mutation(
            rel_path=rel_path,
            runtime_surface=runtime_surface,
            source=source,
        ):
            flags.add("bounded_destructive_file_mutation")
        else:
            flags.add("unbounded_destructive_file_mutation")
            flags.add("blocking_cleanup_required")
    if operation == "write" and (".json" in joined or ".md" in joined):
        if production_surface or role_guess == "generated_export_or_report_writer":
            flags.add("generated_file_write")
            if production_surface:
                flags.add("file_export_to_delete_or_archive")
        elif runtime_surface == "test":
            flags.add("test_fixture_file_write")
        elif runtime_surface == "governance_or_config":
            flags.add("governance_file_reference")
        elif rel_path.startswith(".agents/"):
            flags.add("manual_agent_tool_file_write")
        else:
            flags.add("manual_or_diagnostic_file_write")
    if operation in {"read", "read_write"} and _looks_like_current_runtime_file_read(
        rel_path=rel_path,
        source=source,
        joined=joined,
    ):
        flags.add("runtime_file_read")
        if runtime_surface not in {"test", "governance_or_config", "one_shot_ops"}:
            flags.add("blocking_cleanup_required")
    if operation in {"write", "read_write", "directory_write"} and _looks_like_current_runtime_file_write(
        rel_path=rel_path,
        source=source,
        joined=joined,
    ):
        flags.add("runtime_file_write")
        if operation in {"write", "read_write"}:
            flags.add("generated_file_write")
        if runtime_surface not in {"test", "governance_or_config", "one_shot_ops"}:
            flags.add("blocking_cleanup_required")
    if _has_file_artifact_cli_interface(source) and runtime_surface not in {
        "test",
        "one_shot_ops",
    }:
        flags.add("file_artifact_cli_interface")
        if production_surface:
            flags.add("blocking_cleanup_required")
    if _is_legacy_artifact_file_io(
        rel_path=rel_path,
        runtime_surface=runtime_surface,
        operation=operation,
        role_guess=role_guess,
        source=source,
        joined=joined,
    ):
        flags.add("legacy_artifact_file_io")
        if production_surface:
            flags.add("blocking_cleanup_required")
    return tuple(sorted(flags))


def _has_file_artifact_cli_interface(source: str) -> bool:
    return any(token in source for token in FILE_ARTIFACT_CLI_TOKENS)


def _looks_like_current_runtime_file_read(
    *,
    rel_path: str,
    source: str,
    joined: str,
) -> bool:
    if rel_path in {
        "src/application/config/config_parser.py",
        "src/application/config/config_repository.py",
        "src/application/config_manager.py",
    } and any(token in source for token in ("yaml_path", "parse_yaml_file", "file_path", "yaml.safe_load")):
        return True
    if any(token in joined for token in ("output/runtime-monitor", "reports/")):
        return True
    return False


def _looks_like_current_runtime_file_write(
    *,
    rel_path: str,
    source: str,
    joined: str,
) -> bool:
    if rel_path in {
        "src/infrastructure/jsonl_trace_sink.py",
        "src/infrastructure/strategy_signal_v2_observe_sink.py",
    }:
        return True
    if rel_path in {
        "src/application/config/config_repository.py",
        "src/application/config_manager.py",
    } and any(token in source for token in ("yaml_path", "yaml_str", "yaml_content", "yaml.safe_dump")):
        return True
    if any(token in source for token in ("evidence_path", "write_seed_evidence", "runtime-profile-seed-evidence")):
        return True
    if "json.dumps" in source and any(token in source for token in ("write_text", ".write(", "open(")):
        return True
    if any(token in joined for token in ("output/runtime-monitor", "reports/", ".jsonl")):
        return True
    return False


def _is_legacy_artifact_file_io(
    *,
    rel_path: str,
    runtime_surface: str,
    operation: str,
    role_guess: str,
    source: str,
    joined: str,
) -> bool:
    if not rel_path.startswith("scripts/"):
        return False
    if rel_path.startswith("scripts/ops/"):
        return False
    if runtime_surface in {
        "watcher_tick",
        "product_state_refresh_orchestrator",
        "server_monitor",
        "production_cadence_script",
        "action_time_or_submit_chain",
    }:
        return False
    name = rel_path.rsplit("/", 1)[-1]
    legacy_name = name.startswith("build_") or any(
        token in name for token in LEGACY_ARTIFACT_SCRIPT_NAME_TOKENS
    )
    if not legacy_name:
        return False
    if operation not in {"read", "write", "directory_write", "read_write"}:
        return False
    if role_guess in {"environment_config", "in_memory_json_payload"}:
        return False
    if _has_file_artifact_cli_interface(source):
        return True
    if any(token in joined for token in (".json", ".md", "output/", "reports/")):
        return True
    return any(
        token in source
        for token in (
            "json.dump",
            "output_path.write_text",
            "path.write_text",
            "read_text(",
        )
    )


def _looks_like_report_state_write(
    *,
    joined: str,
    source: str,
    role_guess: str,
) -> bool:
    if role_guess == "generated_export_or_report_writer":
        return True
    if any(token in joined for token in (".json", ".md", "output/runtime-monitor", "reports/")):
        return True
    return any(
        token in source
        for token in (
            "output_json",
            "output_md",
            "report_dir",
            "runtime_monitor_dir",
            "latest-",
            "write_json",
            "_write_json",
        )
    )


def _cleanup(
    operation: str,
    role_guess: str,
    risk_flags: tuple[str, ...],
) -> tuple[str, str]:
    if "suspicious_runtime_file_authority" in risk_flags:
        return (
            "migrate_to_pg_or_delete_reader",
            "Delete this production read or replace it with PG/current service access. If historical value exists, move it to archive-only tooling outside runtime cadence.",
        )
    if "owner_explanation_file_source" in risk_flags:
        return (
            "replace_owner_explanation_source",
            "Delete Owner-facing file reads and source explanation from the PG Owner Explanation Read Model. Historical files may be archived only.",
        )
    if "frequent_report_write" in risk_flags:
        return (
            "delete_from_recurring_cadence",
            "Remove this JSON/MD writer from recurring production cadence or replace it with PG rows/current projections. Archive-only diagnostics must be manually invoked.",
        )
    if "runtime_file_read" in risk_flags:
        return (
            "delete_runtime_file_reader",
            "Delete this current runtime/config file reader. Current semantics must come from PG/current services; history is archive-only.",
        )
    if "runtime_file_write" in risk_flags:
        return (
            "delete_runtime_file_writer",
            "Delete this current runtime/config file writer. Useful current semantics must be persisted in PG; history is archive-only.",
        )
    if "legacy_artifact_file_io" in risk_flags:
        return (
            "delete_current_legacy_artifact_io",
            "Delete this current artifact/proof/evidence file-I/O path. If historical value remains, move it to archive-only provenance and keep it out of runtime, Owner explanation, and deployment readiness.",
        )
    if "file_artifact_cli_interface" in risk_flags:
        return (
            "delete_file_artifact_cli_interface",
            "Delete JSON/MD/report file input/output CLI interface from current scripts. Current state must come from PG/current services; diagnostics use stdout or explicit archive-only tools.",
        )
    if role_guess == "repo_machine_config_or_seed":
        return (
            "seed_then_pg",
            "Import once into PG, then delete the runtime reader. Keep the file only as archived seed provenance if needed.",
        )
    if role_guess == "generated_export_or_report_writer":
        return (
            "delete_writer_or_archive_only",
            "Delete recurring writer. If the artifact is still useful, make it manual archive-only and excluded from runtime/Owner explanation.",
        )
    if role_guess == "generated_export_or_report_reader":
        return (
            "delete_reader",
            "Delete production reader. Rebuild the view from PG or move the file to archive-only historical tooling.",
        )
    if "unbounded_destructive_file_mutation" in risk_flags:
        return (
            "bound_or_delete_mutation",
            "Delete this file mutation path or add explicit one-shot, retention, dry-run, and scope guardrails.",
        )
    if operation in {"delete", "delete_tree"}:
        return (
            "bounded_file_cleanup",
            "Allowed only as local test fixture cleanup or explicit dry-run guarded one-shot ops tooling.",
        )
    return ("review_and_classify", "Classify as PG source, export, diagnostic, seed, or forbidden before accepting production use.")


def _is_bounded_destructive_file_mutation(
    *,
    rel_path: str,
    runtime_surface: str,
    source: str,
) -> bool:
    if runtime_surface == "test":
        return True
    if rel_path.startswith("scripts/ops/"):
        return True
    return False


def _is_test_rejection_guard(
    *,
    runtime_surface: str,
    role_guess: str,
    source_excerpt: str,
) -> bool:
    if runtime_surface != "test":
        return False
    if role_guess not in {
        "generated_export_or_report_reader",
        "generated_export_or_report_writer",
    }:
        return False
    source = source_excerpt.lower()
    return any(
        token in source
        for token in (
            "validate_changed_output_paths",
            "validate_tracked_output_paths",
            "_changed_output_paths_from_porcelain",
            "_assert_output_paths_absent",
            "assert \"output/runtime-monitor",
            "\"d output/runtime-monitor",
            "\" d output/runtime-monitor",
            "\"m output/runtime-monitor",
            "\" m output/runtime-monitor",
            "\"?? output/runtime-monitor",
            "allowed_files\"].append",
            "not in packet",
            "not in artifact",
            "not in text",
            "not in commands",
        )
    )


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _path_hints(source: str) -> tuple[str, ...]:
    hints = []
    for match in PATH_LITERAL_RE.finditer(source):
        value = match.group("path")
        if not _looks_like_real_path_hint(value):
            continue
        if value and value not in hints:
            hints.append(value)
    return tuple(hints)


def _looks_like_real_path_hint(value: str) -> bool:
    if not value:
        return False
    false_positive_fragments = (
        "os.env",
        "_runtime_config_provider.resolved_config.env",
        "username=os.env",
        "password_hash=os.env",
        "totp_secret=os.env",
        "session_secret=os.env",
        "int(os.env",
    )
    if any(fragment in value for fragment in false_positive_fragments):
        return False
    return True


def _should_skip(path: Path, *, repo_root: Path) -> bool:
    rel_parts = path.relative_to(repo_root).parts
    return any(part in SKIP_PARTS for part in rel_parts)


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _compact(source: str, *, max_chars: int = 260) -> str:
    value = " ".join(source.strip().split())
    return value if len(value) <= max_chars else value[: max_chars - 3] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
