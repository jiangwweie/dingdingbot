from unittest.mock import AsyncMock

import pytest

from src.trading_kernel.infrastructure.manual_account_setup import (
    ManualAccountCredentials,
    verify_manual_account,
)


def credentials():
    return ManualAccountCredentials(
        expected_uid="12345",
        api_key="key-canary",
        api_secret="secret-canary",
        owner_username="owner",
        owner_password="owner-password-canary-long",
    )


def reader(uid=12345):
    result = AsyncMock()
    values = {
        "spot_account": {"uid": uid},
        "api_restrictions": {
            "ipRestrict": True,
            "enableReading": True,
            "enableFutures": True,
            "enableWithdrawals": False,
            "enableInternalTransfer": False,
            "permitsUniversalTransfer": False,
        },
        "account_config": {"canTrade": True},
        "position_mode": {"dualSidePosition": True},
        "multi_asset_mode": {"multiAssetsMargin": False},
        "positions": [],
        "open_orders": [],
        "open_algo_orders": [],
    }

    async def get(name):
        return values[name]

    result.get.side_effect = get
    return result, values


@pytest.mark.asyncio
async def test_wrong_uid_stops_before_any_account_binding():
    source, _ = reader(uid=999)
    with pytest.raises(ValueError, match="UID"):
        await verify_manual_account(source, credentials())


@pytest.mark.asyncio
async def test_account_probe_is_readonly_and_never_returns_secrets():
    source, _ = reader()
    result = await verify_manual_account(source, credentials())
    assert result["account_ready"] and result["uid_matches"]
    rendered = str(result) + repr(credentials())
    assert "key-canary" not in rendered and "secret-canary" not in rendered
    assert "owner-password-canary" not in rendered
    assert {call.args[0] for call in source.get.await_args_list} == {
        "spot_account",
        "api_restrictions",
        "account_config",
        "position_mode",
        "multi_asset_mode",
        "positions",
        "open_orders",
        "open_algo_orders",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["enableWithdrawals", "enableInternalTransfer", "permitsUniversalTransfer"]
)
async def test_dangerous_key_capability_blocks_setup(field):
    source, values = reader()
    values["api_restrictions"][field] = True
    with pytest.raises(ValueError, match="permission"):
        await verify_manual_account(source, credentials())


@pytest.mark.asyncio
async def test_wrong_account_mode_is_reported_without_mutation():
    source, values = reader()
    values["position_mode"]["dualSidePosition"] = False
    result = await verify_manual_account(source, credentials())
    assert (
        not result["account_ready"]
        and "independent_position_sides_required" in result["blockers"]
    )


@pytest.mark.asyncio
async def test_existing_exposure_blocks_fresh_account_use():
    source, values = reader()
    values["positions"] = [{"positionAmt": "1"}]
    result = await verify_manual_account(source, credentials())
    assert not result["account_ready"] and "account_not_flat" in result["blockers"]


def test_signed_http_error_does_not_echo_secret_signature_or_api_key(monkeypatch):
    import http.client
    from unittest.mock import Mock

    from src.trading_kernel.infrastructure.manual_account_setup import (
        BinanceManualAccountReader,
    )

    connection = Mock()
    connection.request.side_effect = http.client.HTTPException(
        "signature=secret-canary key-canary"
    )
    monkeypatch.setattr(http.client, "HTTPSConnection", lambda *a, **kw: connection)
    with pytest.raises(ValueError) as e:
        BinanceManualAccountReader(credentials())._get("spot_account")
    assert "secret-canary" not in str(e.value) and "key-canary" not in str(e.value)
    args = connection.request.call_args.args
    assert args[0] == "GET" and "recvWindow=5000" in args[1]
    connection.close.assert_called_once()


def test_credential_setup_requires_private_interactive_terminal(monkeypatch):
    import sys

    from scripts.trading_kernel.configure_manual_account import main

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(ValueError, match="interactive"):
        main(
            [
                "--target",
                "kr",
                "--machine-id",
                "f956f502ced4461e9d0fcc0ef637abd6",
                "--public-ip",
                "43.133.243.174",
            ]
        )


def test_enrollment_password_hasher_matches_the_actual_console_validator():
    from scripts.trading_kernel.manual_account_enrollment import owner_password_hasher
    from src.trading_kernel.interfaces.owner_console_http.auth import OwnerAuthSettings

    hasher = owner_password_hasher()
    encoded = hasher.hash("owner-password-canary-long")
    settings = OwnerAuthSettings(
        username="owner",
        password_hash=encoded,
        totp_seed="JBSWY3DPEHPK3PXP",
        session_signing_key="s" * 64,
    )
    assert hasher.verify(settings.password_hash, "owner-password-canary-long")
