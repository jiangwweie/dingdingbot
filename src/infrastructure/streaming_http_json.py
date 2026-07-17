"""Incremental JSON transport helpers with bounded individual reads."""

from __future__ import annotations

from collections.abc import Iterator
from typing import BinaryIO
import re

import ijson


DEFAULT_CHUNK_BYTES = 65_536


class PositiveBoundedReader:
    """Never forwards an unbounded or oversized read to the transport."""

    def __init__(self, response: BinaryIO, *, chunk_bytes: int) -> None:
        if chunk_bytes <= 0:
            raise ValueError("chunk_bytes must be positive")
        self._response = response
        self._chunk_bytes = chunk_bytes

    def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        bounded_size = self._chunk_bytes if size < 0 else min(size, self._chunk_bytes)
        if bounded_size <= 0:
            bounded_size = self._chunk_bytes
        return self._response.read(bounded_size)


def iter_json_events(
    response: BinaryIO,
    *,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
) -> Iterator[tuple[str, str, object]]:
    """Yield nested JSON events without materializing the root document."""

    yield from ijson.parse(
        PositiveBoundedReader(response, chunk_bytes=chunk_bytes)
    )


def iter_json_array_items(
    response: BinaryIO,
    *,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
) -> Iterator[object]:
    """Yield every top-level array item under transport backpressure."""

    yield from ijson.items(
        PositiveBoundedReader(response, chunk_bytes=chunk_bytes),
        "item",
    )


def read_masked_error_excerpt(
    response: BinaryIO,
    *,
    max_bytes: int = DEFAULT_CHUNK_BYTES,
) -> str:
    """Retain one bounded, masked diagnostic excerpt; never account truth."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    chunks: list[bytes] = []
    remaining = max_bytes
    while remaining > 0:
        chunk = response.read(min(DEFAULT_CHUNK_BYTES, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    text = b"".join(chunks).decode("utf-8", errors="replace")
    return _mask_sensitive_text(text)


def _mask_sensitive_text(value: str) -> str:
    value = re.sub(
        r"(?i)(api[_-]?key|secret|signature|token|authorization)"
        r"([\"']?\s*[:=]\s*[\"']?)([^\s,;&\"']+)",
        r"\1\2***",
        value,
    )
    return re.sub(r"\b[A-Fa-f0-9]{48,}\b", "***", value)
