"""Typed portfolio Exposure Family identity shared across kernel boundaries."""

from typing import Literal

ExposureFamily = Literal[
    "long_continuation",
    "opening_range",
    "rally_failure_short",
]
