import pytest
from fastapi import HTTPException

from src.application.runtime_official_submit_handoff_service import (
    RuntimeOfficialSubmitHandoffService,
)
from src.domain.runtime_official_submit_handoff import (
    RuntimeOfficialSubmitHandoffMode,
    RuntimeOfficialSubmitHandoffStatus,
)
from tests.unit.test_runtime_official_submit_handoff import _readiness


@pytest.mark.asyncio
async def test_service_builds_disabled_smoke_handoff_preview():
    service = RuntimeOfficialSubmitHandoffService()

    packet = await service.preview_from_readiness_packet(
        readiness_packet=_readiness(),
        fresh_submit_authorization_id="fresh-auth-1",
    )

    assert packet.status == (
        RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL
    )
    assert packet.official_query[
        "owner_confirmed_for_first_real_submit_action"
    ] is False
    assert packet.exchange_order_submitted is False
    assert packet.order_lifecycle_called is False


@pytest.mark.asyncio
async def test_service_uses_standing_authorization_for_real_gateway_handoff():
    service = RuntimeOfficialSubmitHandoffService()

    packet = await service.preview_from_readiness_packet(
        readiness_packet=_readiness(),
        fresh_submit_authorization_id="fresh-auth-1",
        mode=RuntimeOfficialSubmitHandoffMode.REAL_GATEWAY_ACTION,
        owner_confirmed_for_real_submit_action=False,
    )

    assert packet.status == (
        RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL
    )
    assert packet.official_query[
        "owner_confirmed_for_first_real_submit_action"
    ] is True
    assert "owner_real_submit_action_confirmation_missing" not in packet.blockers


@pytest.mark.asyncio
async def test_trading_console_official_submit_handoff_endpoint():
    from src.interfaces.api_trading_console import (
        RuntimeOfficialSubmitHandoffPreviewRequest,
        runtime_official_submit_handoff_preview,
    )

    readiness = _readiness()
    response = await runtime_official_submit_handoff_preview(
        readiness.runtime_instance_id,
        RuntimeOfficialSubmitHandoffPreviewRequest(
            readiness_packet=readiness,
            fresh_submit_authorization_id="fresh-auth-1",
            additional_warnings=["unit_endpoint"],
        ),
    )

    assert response.status == (
        RuntimeOfficialSubmitHandoffStatus.READY_FOR_OFFICIAL_SUBMIT_CALL
    )
    assert "unit_endpoint" in response.warnings
    assert "trading_console_api_non_executing_handoff_preview" in (
        response.warnings
    )
    assert response.exchange_called is False


@pytest.mark.asyncio
async def test_trading_console_official_submit_handoff_endpoint_blocks_runtime_mismatch():
    from src.interfaces.api_trading_console import (
        RuntimeOfficialSubmitHandoffPreviewRequest,
        runtime_official_submit_handoff_preview,
    )

    readiness = _readiness()
    with pytest.raises(HTTPException) as exc_info:
        await runtime_official_submit_handoff_preview(
            "different-runtime",
            RuntimeOfficialSubmitHandoffPreviewRequest(
                readiness_packet=readiness,
                fresh_submit_authorization_id="fresh-auth-1",
            ),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "readiness_packet_runtime_mismatch"
