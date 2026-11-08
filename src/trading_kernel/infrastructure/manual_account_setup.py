"""Bounded signed GET-only identity and permissions for a fresh manual account."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import http.client
import json
import ssl
import time
import urllib.parse
from decimal import Decimal
from typing import ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ManualAccountCredentials(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    expected_uid: str = Field(pattern=r"^[0-9]{1,20}$")
    api_key: SecretStr
    api_secret: SecretStr
    owner_username: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$"
    )
    owner_password: SecretStr


class ManualAccountReader(Protocol):
    async def get(self, name: str) -> object: ...


class BinanceManualAccountReader:
    """No POST/PUT/DELETE, leverage setters, listen-key creation or orders exist here."""

    ENDPOINTS: ClassVar[dict[str, tuple[str, str]]] = {
        "spot_account": ("https://api.binance.com", "/api/v3/account"),
        "api_restrictions": (
            "https://api.binance.com",
            "/sapi/v1/account/apiRestrictions",
        ),
        "account_config": ("https://fapi.binance.com", "/fapi/v1/accountConfig"),
        "position_mode": ("https://fapi.binance.com", "/fapi/v1/positionSide/dual"),
        "multi_asset_mode": ("https://fapi.binance.com", "/fapi/v1/multiAssetsMargin"),
        "positions": ("https://fapi.binance.com", "/fapi/v3/positionRisk"),
        "open_orders": ("https://fapi.binance.com", "/fapi/v1/openOrders"),
        "open_algo_orders": ("https://fapi.binance.com", "/fapi/v1/openAlgoOrders"),
    }

    def __init__(self, credentials: ManualAccountCredentials):
        self.credentials = credentials

    async def get(self, name: str) -> object:
        return await asyncio.to_thread(self._get, name)

    def _get(self, name: str) -> object:
        base, path = self.ENDPOINTS[name]
        query = urllib.parse.urlencode(
            {"timestamp": int(time.time() * 1000), "recvWindow": 5000}
        )
        signature = hmac.new(
            self.credentials.api_secret.get_secret_value().encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        connection = http.client.HTTPSConnection(
            base.removeprefix("https://"),
            timeout=10,
            context=ssl.create_default_context(),
        )
        try:
            connection.request(
                "GET",
                path + "?" + query + "&signature=" + signature,
                headers={"X-MBX-APIKEY": self.credentials.api_key.get_secret_value()},
            )
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("signed account response rejected")
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError("account response exceeds bound")
            return json.loads(raw)
        except (OSError, http.client.HTTPException, ValueError):
            raise ValueError(
                "signed readonly account request failed: " + name
            ) from None
        finally:
            connection.close()


async def verify_manual_account(
    source: ManualAccountReader, credentials: ManualAccountCredentials
) -> dict:
    identity = await source.get("spot_account")
    if (
        not isinstance(identity, dict)
        or str(identity.get("uid", "")) != credentials.expected_uid
    ):
        raise ValueError("independent account UID mismatch or unavailable")
    names = (
        "api_restrictions",
        "account_config",
        "position_mode",
        "multi_asset_mode",
        "positions",
        "open_orders",
        "open_algo_orders",
    )
    values = dict(
        zip(
            names,
            await asyncio.gather(*(source.get(name) for name in names)),
            strict=True,
        )
    )
    permission = values["api_restrictions"]
    if not isinstance(permission, dict) or any(
        permission.get(k) is not True
        for k in ("ipRestrict", "enableReading", "enableFutures")
    ):
        raise ValueError("required readonly/futures/IP permission missing")
    if any(
        permission.get(k) is not False
        for k in (
            "enableWithdrawals",
            "enableInternalTransfer",
            "permitsUniversalTransfer",
        )
    ):
        raise ValueError("withdrawal/transfer permission is enabled or unproven")
    blockers = []
    if values["position_mode"] != {"dualSidePosition": True}:
        blockers.append("independent_position_sides_required")
    if values["multi_asset_mode"] != {"multiAssetsMargin": False}:
        blockers.append("single_asset_margin_required")
    config = values["account_config"]
    if not isinstance(config, dict) or config.get("canTrade") is not True:
        blockers.append("account_trading_not_enabled")
    positions = values["positions"]
    if not isinstance(positions, list) or len(positions) > 2000:
        raise ValueError("position facts incomplete")
    for p in positions:
        if not isinstance(p, dict):
            raise TypeError("position fact invalid")
        quantity = Decimal(str(p.get("positionAmt", "NaN")))
        if not quantity.is_finite():
            raise ValueError("position quantity invalid")
        if quantity != 0:
            blockers.append("account_not_flat")
            break
    for name in ("open_orders", "open_algo_orders"):
        rows = values[name]
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ValueError("order facts incomplete")
        if rows:
            blockers.append("existing_" + name)
    return {
        "uid_matches": True,
        "account_ready": not blockers,
        "blockers": sorted(set(blockers)),
        "venue_id": "binance-usdm",
        "position_mode_verified": not (
            "independent_position_sides_required" in blockers
        ),
        "credential_fingerprint": hashlib.sha256(
            credentials.api_key.get_secret_value().encode()
        ).hexdigest(),
        "observed_at_ms": int(time.time() * 1000),
        "exchange_mutations": 0,
    }
