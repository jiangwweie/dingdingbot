#!/usr/bin/env python3
"""Orchestrator: Run all doc-manager steps in sequence."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]  # .claude/skills/doc-manager/scripts/ → project root
SCRIPTS_DIR = Path(__file__).parent


def run_step(name: str, script: str):
    print(f"\n{'='*60}")
    print(f"Step: {name}")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script)],
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        print(f"FATAL: {name} failed with exit code {result.returncode}")
        sys.exit(1)


def main():
    print("Doc Manager - Starting cleanup ...")

    run_step("1. Scan", "scan.py")
    run_step("2. Validate", "validate.py")
    run_step("3. Classify & Move", "classify.py")
    run_step("4. Generate Index", "index.py")

    print(f"\n{'='*60}")
    print("Done. Clean up .scan-result.json and .validate-result.json")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
