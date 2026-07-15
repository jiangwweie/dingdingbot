from __future__ import annotations

import pytest

from scripts.runtime_first_real_submit_api_flow import (
    _read_response_body_bounded,
)


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.read_sizes: list[int] = []

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        return self.payload[:size]


@pytest.mark.parametrize("limit", [128 * 1024, 512 * 1024, 16 * 1024 * 1024])
def test_bounded_response_reader_accepts_exact_limit(limit):
    response = _Response(b"x" * limit)

    assert len(_read_response_body_bounded(response, max_bytes=limit)) == limit
    assert response.read_sizes == [limit + 1]


@pytest.mark.parametrize("limit", [128 * 1024, 512 * 1024, 16 * 1024 * 1024])
def test_bounded_response_reader_rejects_limit_plus_one(limit):
    response = _Response(b"x" * (limit + 1))

    with pytest.raises(RuntimeError, match=f"api_response_oversize:{limit}"):
        _read_response_body_bounded(response, max_bytes=limit)
    assert response.read_sizes == [limit + 1]

