"""Adapter from Directional Opportunity Pack windows to forward outcomes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.directional_opportunity_pack import DirectionalOpportunityPackSpec


class DirectionalForwardOutcomeWindowRequest(BaseModel):
    """Existing forward outcome calculator window shape."""

    model_config = ConfigDict(extra="forbid")

    windows: dict[str, int] = Field(default_factory=dict)
    primary_timeframe: str = Field(default="1h", min_length=1, max_length=32)

    @model_validator(mode="after")
    def _validate_windows(self) -> "DirectionalForwardOutcomeWindowRequest":
        if not self.windows:
            raise ValueError("windows must not be empty")
        for label, bars_ahead in self.windows.items():
            if not label:
                raise ValueError("window label must not be empty")
            if bars_ahead < 1:
                raise ValueError("bars_ahead must be positive")
        return self


def pack_forward_outcome_windows(
    pack: DirectionalOpportunityPackSpec,
    *,
    primary_timeframe: str = "1h",
) -> DirectionalForwardOutcomeWindowRequest:
    """Convert a pack spec into calculate_forward_outcomes windows."""

    if primary_timeframe != "1h":
        raise ValueError("directional pack forward windows currently support primary_timeframe=1h only")
    return DirectionalForwardOutcomeWindowRequest(
        primary_timeframe=primary_timeframe,
        windows={label: _one_hour_bars_for_window(label) for label in pack.forward_windows},
    )


def _one_hour_bars_for_window(label: str) -> int:
    if label.endswith("h"):
        hours = int(label[:-1])
        if hours < 1:
            raise ValueError(f"unsupported forward window: {label}")
        return hours
    if label.endswith("d"):
        days = int(label[:-1])
        if days < 1:
            raise ValueError(f"unsupported forward window: {label}")
        return days * 24
    raise ValueError(f"unsupported forward window: {label}")
