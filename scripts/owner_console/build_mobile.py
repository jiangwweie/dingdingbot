"""Build the phone shell into the same immutable Owner Console artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

MOBILE_FILES = frozenset(
    {"index.html", "app.js", "styles.css", "sw.js", "manifest.webmanifest", "icon.svg"}
)


def build_mobile(source: Path, destination: Path) -> None:
    if (
        source.is_symlink()
        or destination.is_symlink()
        or source.resolve() == destination.resolve()
    ):
        raise ValueError("mobile build source/destination unsafe")
    paths = {p.name: p for p in source.iterdir()}
    if set(paths) != MOBILE_FILES or any(
        p.is_symlink() or not p.is_file() for p in paths.values()
    ):
        raise ValueError("mobile shell files differ from allowlist")
    digest = hashlib.sha256()
    for name in sorted(MOBILE_FILES):
        digest.update(name.encode())
        digest.update(paths[name].read_bytes())
    if destination.exists():
        if not destination.is_dir() or any(
            p.name not in MOBILE_FILES or p.is_symlink() or not p.is_file()
            for p in destination.iterdir()
        ):
            raise ValueError("mobile destination contains unrelated files")
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for name, p in paths.items():
        content = p.read_bytes()
        if name == "sw.js":
            content = content.replace(
                b"brc-owner-mobile-v1",
                ("brc-owner-mobile-" + digest.hexdigest()[:16]).encode(),
            )
        (destination / name).write_bytes(content)
    manifest = json.loads((destination / "manifest.webmanifest").read_text())
    if manifest["scope"] != "/mobile/" or manifest["start_url"] != "/mobile/":
        raise ValueError("phone application scope differs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("frontend/owner-mobile"))
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("frontend/owner-console-v2/dist/mobile"),
    )
    arguments = parser.parse_args()
    build_mobile(arguments.source, arguments.destination)
