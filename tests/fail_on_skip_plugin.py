"""Make required certification fail if pytest reports skip or xfail."""

from __future__ import annotations

from typing import Any

import pytest


def pytest_configure(config: Any) -> None:
    config._brc_required_gate_nonpass_reports = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any):
    outcome = yield
    report = outcome.get_result()
    if report.skipped or getattr(report, "wasxfail", None):
        item.config._brc_required_gate_nonpass_reports.append(
            f"{report.nodeid}:{'xfail' if getattr(report, 'wasxfail', None) else 'skip'}"
        )


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    reports = getattr(session.config, "_brc_required_gate_nonpass_reports", [])
    if reports and exitstatus == 0:
        session.exitstatus = 1
