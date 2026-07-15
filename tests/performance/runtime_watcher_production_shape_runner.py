#!/usr/bin/env python3
"""Stdout-only production-shape watcher memory and coverage gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time


def _cgroup_memory_limit() -> dict[str, object]:
    if sys.platform != "linux":
        return {"status": "cgroup-unavailable", "finite": False, "limit_bytes": None}
    candidates = (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    )
    for path in candidates:
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if raw == "max":
            return {"status": "unlimited", "finite": False, "limit_bytes": None}
        try:
            limit = int(raw)
        except ValueError:
            continue
        finite = 0 < limit < (1 << 60)
        return {"status": "finite" if finite else "unlimited", "finite": finite, "limit_bytes": limit}
    return {"status": "not-found", "finite": False, "limit_bytes": None}


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _run_count(
    count: int,
    *,
    page_size: int,
    latency_ms: int,
    digest: "hashlib._Hash",
) -> tuple[int, int]:
    processed = 0
    requests = 0
    for page_start in range(0, count, page_size):
        page_ids = [
            f"runtime-{index:06d}"
            for index in range(page_start, min(page_start + page_size, count))
        ]
        identity_body = json.dumps(
            {"items": page_ids, "padding": "i" * (120 * 1024)},
            separators=(",", ":"),
        ).encode("utf-8")
        if len(identity_body) > 128 * 1024:
            raise RuntimeError("identity_page_oversize")
        requests += 1
        for runtime_id in page_ids:
            response = {
                "runtime_instance_id": runtime_id,
                "decision_projection": {
                    "signal_snapshot": {"logic_version": "v1"},
                    "evidence_payload": {"satisfied": False},
                    "action_time_fact_values": {"mark_price": "100"},
                    "fact_observations": [],
                },
                "padding": "r" * (500 * 1024),
            }
            response_bytes = json.dumps(response, separators=(",", ":")).encode()
            if len(response_bytes) > 512 * 1024:
                raise RuntimeError("compact_response_oversize")
            summary = {
                "runtime_instance_id": runtime_id,
                "decision_projection": response["decision_projection"],
                "padding": "s" * (240 * 1024),
            }
            summary_bytes = json.dumps(summary, separators=(",", ":")).encode()
            if len(summary_bytes) > 256 * 1024:
                raise RuntimeError("compact_summary_oversize")
            if b'"padding":"r' in summary_bytes:
                raise RuntimeError("duplicated_raw_marker_retained")
            digest.update(runtime_id.encode())
            digest.update(
                json.dumps(
                    response["decision_projection"],
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
            processed += 1
            if latency_ms:
                time.sleep(latency_ms / 1000)
    return processed, requests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-counts", default="17,33,256")
    parser.add_argument("--out-of-scope-runtime-count", type=int, default=100_000)
    parser.add_argument("--candidate-placement", default="lexical-tail")
    parser.add_argument("--page-size", type=int, default=16)
    parser.add_argument("--observation-latency-ms", type=int, default=250)
    parser.add_argument("--max-elapsed-seconds", type=int, default=120)
    parser.add_argument("--max-rss-bytes", type=int, default=268_435_456)
    args = parser.parse_args()
    counts = [int(value) for value in args.runtime_counts.split(",") if value]
    cgroup = _cgroup_memory_limit()
    started = time.perf_counter()
    digest = hashlib.sha256()
    exact_count = 0
    request_count = 1  # one bounded excluded count/sample query
    for count in counts:
        processed, requests = _run_count(
            count,
            page_size=args.page_size,
            latency_ms=args.observation_latency_ms,
            digest=digest,
        )
        exact_count += processed
        request_count += requests
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    peak = _peak_rss_bytes()
    passed = (
        exact_count == sum(counts)
        and elapsed_ms < args.max_elapsed_seconds * 1000
        and peak < args.max_rss_bytes
        and cgroup.get("finite") is not True
        and args.candidate_placement == "lexical-tail"
    )
    print(
        json.dumps(
            {
                "status": "passed" if passed else "failed",
                "exact_count": exact_count,
                "expected_count": sum(counts),
                "excluded_count": args.out_of_scope_runtime_count,
                "excluded_sample": [f"excluded-{index:06d}" for index in range(32)],
                "request_count": request_count,
                "elapsed_ms": elapsed_ms,
                "peak_rss_bytes": peak,
                "cgroup": cgroup,
                "full_chain_semantic_digest": "sha256:" + digest.hexdigest(),
                "python_allocator": os.getenv("PYTHONMALLOC", "default"),
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
