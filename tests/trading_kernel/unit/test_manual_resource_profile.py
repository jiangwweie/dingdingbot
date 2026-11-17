"""Manual resource headroom must not alter shared/Tokyo defaults."""

from pathlib import Path

import pytest

from scripts.trading_kernel.manual_runtime_installation import (
    install_manual_resource_profile,
)

ROOT = Path(__file__).resolve().parents[3]


def test_manual_profile_installs_exact_dropin_without_rewriting_base_unit(tmp_path):
    install_manual_resource_profile(ROOT, etc=tmp_path)
    p = tmp_path / "systemd/system/brc-trading-kernel.slice.d/manual-resources.conf"
    assert p.read_text() == "[Slice]\nCPUQuota=150%\nMemoryMax=1536M\nTasksMax=128\n"
    base = (ROOT / "deploy/systemd/brc-trading-kernel.slice").read_text()
    assert "CPUQuota=100%" in base and "MemoryMax=1G" in base
    assert not (tmp_path / "systemd/system/brc-trading-kernel.slice").exists()


def test_modified_resource_contract_is_rejected_before_write(tmp_path):
    release = tmp_path / "release"
    d = release / "deploy/manual/systemd"
    d.mkdir(parents=True)
    (d / "kernel-resources.conf").write_text(
        "[Slice]\nCPUQuota=200%\nMemoryMax=2G\nTasksMax=128\n"
    )
    with pytest.raises(ValueError, match="resource"):
        install_manual_resource_profile(release, etc=tmp_path / "etc")
    assert not (tmp_path / "etc").exists()
