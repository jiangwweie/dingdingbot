"""Compiled product identity; branch names and local paths are not authority."""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PRODUCT_ID: Final = "brc-app-manual-v1"


class ManualReleaseBinding(BaseModel):
    """Explicit, non-secret deployment identity awaiting a real target binding."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    product_id: Literal["brc-app-manual-v1"]
    ssh_target: str
    machine_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    venue_id: Literal["binance-usdm"]
    account_id: str
    exchange_account_uid: str
    database_name: str
    database_system_identifier: str = Field(pattern=r"^[0-9]+$")
    release_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    schema_revision: str

    @field_validator("ssh_target", "account_id", "exchange_account_uid", "database_name", "schema_revision")
    @classmethod
    def exact_token(cls, value: str) -> str:
        if not value or value.strip() != value or any(c.isspace() for c in value):
            raise ValueError("release identity requires one exact token")
        return value


def require_manual_release_identity(
    expected: ManualReleaseBinding, observed: ManualReleaseBinding
) -> None:
    if expected != observed:
        # Do not log the full account/host binding when reporting mismatch.
        raise ValueError("manual product target identity mismatch")


def refuse_inherited_tokyo_deployment() -> None:
    """No manual artifact may use a Tokyo deployment backend, even via an alias."""
    raise ValueError(
        "manual product cannot use inherited Tokyo deployment; "
        "new-server binding and provisioning acceptance are required"
    )
