#!/usr/bin/env python3
"""Low-friction read-only BRC operator helper.

This script intentionally calls only read endpoints. It does not place orders,
close positions, transfer funds, withdraw, or mutate campaign state.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8001"


def _get_json(base_url: str, path: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    request = Request(url, method="GET")
    return _open_json(request, url)


def _post_json(base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return _open_json(request, url)


def _open_json(request: Request, url: str) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {url}: {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"failed to reach {url}: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only BRC operator helper")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"local runtime base URL, default {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--confirm",
        default=None,
        help="confirmation phrase required for run mode",
    )
    parser.add_argument(
        "command",
        choices=("review", "eligibility", "evidence", "draft", "plan", "run"),
        help="read-only BRC object to print",
    )
    parser.add_argument(
        "text",
        nargs="*",
        help="operator text for draft mode",
    )
    args = parser.parse_args()

    if args.command == "draft":
        text = " ".join(args.text).strip()
        if not text:
            parser.error("draft mode requires operator text")
        payload = _post_json(
            args.base_url,
            "/api/runtime/test/brc/operator/draft",
            {"text": text},
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "plan":
        text = " ".join(args.text).strip()
        if not text:
            parser.error("plan mode requires operator text")
        payload = _post_json(
            args.base_url,
            "/api/runtime/test/brc/operator/plan",
            {"text": text},
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.command == "run":
        text = " ".join(args.text).strip()
        if not text:
            parser.error("run mode requires operator text")
        if not args.confirm:
            parser.error("run mode requires --confirm CONFIRM_READ_ONLY_BRC")
        payload = _post_json(
            args.base_url,
            "/api/runtime/test/brc/operator/run",
            {"text": text, "confirmation_phrase": args.confirm},
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    paths = {
        "review": "/api/runtime/test/brc/review-packet",
        "eligibility": "/api/runtime/test/brc/next-eligibility",
        "evidence": "/api/runtime/test/brc/evidence",
    }
    payload = _get_json(args.base_url, paths[args.command])
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
