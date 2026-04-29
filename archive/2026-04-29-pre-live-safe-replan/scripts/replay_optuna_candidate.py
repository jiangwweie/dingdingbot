#!/usr/bin/env python3
"""
Replay (dry-run) an Optuna candidate report.

This script is intentionally safe-by-default:
- It does NOT promote runtime profiles.
- It does NOT auto-run a heavy backtest unless explicitly asked later.

Current behavior:
- Load candidate JSON.
- Print key metadata, constraints, and the resolved backtest request envelope.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, help="Path to candidate JSON report")
    args = parser.parse_args()

    candidate_path = Path(args.candidate)
    if not candidate_path.exists():
        print(f"❌ candidate not found: {candidate_path}")
        return 2

    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    print("✅ Candidate loaded")
    print(f"  candidate_name: {payload.get('candidate_name')}")
    print(f"  generated_at:   {payload.get('generated_at')}")
    print(f"  status:         {payload.get('status')}")
    print(f"  source_profile: {payload.get('source_profile')}")
    print(f"  git:            {payload.get('git')}")
    print()
    print("constraints:")
    print(json.dumps(payload.get("constraints", {}), ensure_ascii=False, indent=2, default=str))
    print()
    print("resolved_request:")
    print(json.dumps(payload.get("resolved_request", {}), ensure_ascii=False, indent=2, default=str))
    print()
    print("runtime_overrides:")
    print(json.dumps(payload.get("runtime_overrides", {}), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

