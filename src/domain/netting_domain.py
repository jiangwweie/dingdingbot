"""Canonical, asset-neutral identity for one exchange netting domain."""

from __future__ import annotations


def build_netting_domain_key(
    *,
    account_id: str,
    exchange_instrument_id: str,
    position_mode: str,
    position_bucket: str,
) -> str:
    """Build the only supported key for exposure, command and hold ownership."""

    values = {
        "account_id": account_id,
        "exchange_instrument_id": exchange_instrument_id,
        "position_mode": position_mode,
        "position_bucket": position_bucket,
    }
    normalized = {key: str(value or "").strip() for key, value in values.items()}
    missing = [key for key, value in normalized.items() if not value]
    if missing:
        raise ValueError("netting_domain_identity_missing:" + ",".join(missing))
    if any("|" in value for value in normalized.values()):
        raise ValueError("netting_domain_identity_delimiter_invalid")
    return "|".join(
        (
            normalized["account_id"],
            normalized["exchange_instrument_id"],
            normalized["position_mode"],
            normalized["position_bucket"],
        )
    )
