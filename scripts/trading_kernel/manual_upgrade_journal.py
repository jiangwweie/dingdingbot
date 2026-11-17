"""Root-owned installation progress; never read by trading runtime cadence."""

from __future__ import annotations

import json
import os
from pathlib import Path

from scripts.trading_kernel.manual_host_bootstrap import write_private


class UpgradeJournal:
    def __init__(self, root: Path, receipt: dict, source: dict):
        self.path = root / "upgrade-progress.json"
        self.receipt = receipt
        self.source = source
        binding = {
            "source": source,
            "target": {
                k: receipt[k]
                for k in (
                    "commit",
                    "schema_revision",
                    "kernel_release",
                    "api_release",
                    "static_release",
                    "artifacts_sha256",
                    "product_id",
                )
                if k in receipt
            },
        }
        if self.path.is_symlink():
            raise ValueError("upgrade journal symlink")
        if self.path.exists():
            if self.path.stat().st_mode & 0o077:
                raise ValueError("unsafe upgrade journal permissions")
            self.state = json.loads(self.path.read_text())
            if self.state.get("binding") != binding:
                if "complete" not in self.state.get("steps", []):
                    raise ValueError("upgrade candidate journal differs")
                archive = (
                    root / "upgrade-history" / self.state["binding"]["target"]["commit"]
                )
                write_private(archive, self.path.read_text())
                self.state = {
                    "binding": binding,
                    "steps": [],
                    "baseline": None,
                    "surfaces": None,
                    "environment": None,
                }
                self.save()
        else:
            self.state = {
                "binding": binding,
                "steps": [],
                "baseline": None,
                "surfaces": None,
                "environment": None,
            }
            self.save()

    def save(self):
        write_private(
            self.path,
            json.dumps(self.state, default=str, sort_keys=True) + "\n",
            overwrite=True,
        )

    @property
    def baseline(self):
        return self.state["baseline"]

    def freeze_baseline(self, value):
        normalized = json.loads(json.dumps(value, default=str))
        if self.baseline is not None and self.baseline != normalized:
            raise ValueError("upgrade baseline cannot change")
        if self.baseline is None:
            self.state["baseline"] = normalized
            self.save()

    def resume_binding(self):
        return {
            **self.state["binding"],
            "baseline": self.baseline is not None,
            "surfaces": self.state["surfaces"],
            "starting_services": self.done("starting_services"),
            "steps":list(self.state['steps']),
        }

    def freeze_database(self, value):
        if self.state.get("database") is not None and self.state["database"] != value:
            raise ValueError("upgrade database binding changed")
        if self.state.get("database") is None:
            self.state["database"] = value
            self.save()

    def done(self, step):
        return step in self.state["steps"]

    def complete_step(self, step):
        if not self.done(step):
            self.state["steps"].append(step)
            self.save()

    def freeze_surfaces(self, links):
        observed = {
            kind: str(path.resolve(strict=True)) for kind, path in links.items()
        }
        for kind, path in links.items():
            if kind == "static":
                continue
            commit = (path / ".brc-runtime-commit").read_text().strip()
            schema = (path / ".brc-schema-revision").read_text().strip()
            expected = (
                (self.receipt["commit"], self.receipt["schema_revision"])
                if observed[kind] == self.receipt[kind + "_release"]
                else (self.source["commit"], self.source["schema"])
            )
            if (commit, schema) != expected:
                raise ValueError("upgrade surface marker differs")
        if self.state["surfaces"] is None:
            self.state["surfaces"] = observed
            self.save()
        for kind, path in links.items():
            if self.done(kind) and path.resolve()!=Path(self.receipt[kind+'_release']).resolve():
                raise ValueError('completed upgrade surface regressed')
            if not path.is_symlink() or str(path.resolve()) not in {
                self.state["surfaces"][kind],
                self.receipt[kind + "_release"],
            }:
                raise ValueError("upgrade surface outside candidate")

    def switch_surface(self, kind, path):
        expected = Path(self.receipt[kind + "_release"])
        if self.state["surfaces"] is None or not path.is_symlink():
            raise ValueError("upgrade surfaces not frozen")
        if path.resolve() == expected.resolve():
            return
        if str(path.resolve()) != self.state["surfaces"][kind]:
            raise ValueError("source surface differs during resume")
        pending = path.with_name(path.name + ".pending-manual-upgrade")
        if os.path.lexists(pending):
            if not pending.is_symlink() or pending.resolve() != expected.resolve():
                raise ValueError("foreign pending surface")
        else:
            pending.symlink_to(expected, target_is_directory=True)
        os.replace(pending, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def update_environment(self, path):
        if path.is_symlink():
            raise ValueError("environment symlink forbidden")
        values = {
            k: json.loads(v)
            for k, v in (line.split("=", 1) for line in path.read_text().splitlines())
        }
        if self.state["environment"] is None:
            if (
                values["TRADING_KERNEL_RUNTIME_COMMIT"],
                values["TRADING_KERNEL_SCHEMA_REVISION"],
            ) != (self.source["commit"], self.source["schema"]):
                raise ValueError("source environment not bound")
            self.state["environment"] = values
            self.save()
        expected = {
            **self.state["environment"],
            "TRADING_KERNEL_RUNTIME_COMMIT": self.receipt["commit"],
            "TRADING_KERNEL_SCHEMA_REVISION": self.receipt["schema_revision"],
        }
        if values not in [self.state["environment"], expected]:
            raise ValueError("environment outside source/candidate")
        write_private(
            path,
            "".join(k + "=" + json.dumps(v) + "\n" for k, v in expected.items()),
            overwrite=True,
        )
        self.complete_step("environment")
