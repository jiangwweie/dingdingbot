from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.interfaces.operator_auth import require_operator_session


router = APIRouter(
    prefix="/api/runtime",
    tags=["Runtime Safety"],
    dependencies=[Depends(require_operator_session)],
)


class RuntimeSafetyResponse(BaseModel):
    runtime_bound: bool
    profile: Optional[str] = None
    testnet: Optional[bool] = None
    gks_active: Optional[bool] = None
    startup_guard_armed: Optional[bool] = None
    flatness_known: bool = False
    current_stage: str = "BRC-R4 local operator console"
    next_recommended_step: str = "Confirm runtime profile/testnet/guards before any controlled rehearsal."
    global_planning_stage: str = "Bounded Risk Campaign System mainline; real live remains unauthorized."
    human_summary: str
    live_ready: bool = False


def _api_module() -> Any:
    from src.interfaces import api as api_module

    return api_module


def _safe_profile(provider: Any) -> tuple[Optional[str], Optional[bool]]:
    if provider is None:
        return None, None
    resolved = getattr(provider, "resolved_config", None)
    if resolved is None:
        return None, None
    profile = getattr(resolved, "profile_name", None)
    environment = getattr(resolved, "environment", None)
    testnet = getattr(environment, "exchange_testnet", None)
    if testnet is None:
        testnet = getattr(environment, "testnet", None)
    if testnet is None:
        market = getattr(resolved, "market", None)
        testnet = getattr(market, "testnet", None)
    return profile, testnet


@router.get("/safety", response_model=RuntimeSafetyResponse)
async def get_runtime_safety() -> RuntimeSafetyResponse:
    api_module = _api_module()
    runtime_context = api_module.get_runtime_context()
    profile, testnet = _safe_profile(getattr(api_module, "_runtime_config_provider", None))

    gks_active = None
    gks = getattr(api_module, "_global_kill_switch_service", None)
    if gks is not None and hasattr(gks, "get_state"):
        state = gks.get_state()
        gks_active = bool(getattr(state, "active", state.get("active") if isinstance(state, dict) else None))
    elif gks is not None and hasattr(gks, "is_active"):
        gks_active = bool(gks.is_active())

    startup_guard_armed = None
    guard = getattr(api_module, "_startup_trading_guard_service", None)
    if guard is not None and hasattr(guard, "get_state"):
        state = guard.get_state()
        startup_guard_armed = bool(getattr(state, "armed", state.get("armed") if isinstance(state, dict) else None))
    elif guard is not None and hasattr(guard, "is_armed"):
        startup_guard_armed = bool(guard.is_armed())

    if runtime_context is None:
        summary = "Runtime is not bound, so the console can only show auth/session state."
    elif profile != "brc_btc_eth_testnet_runtime":
        summary = "Runtime is bound, but the active profile is not the fixed BRC BTC/ETH testnet profile."
    elif testnet is not True:
        summary = "Runtime is bound, but testnet mode is not confirmed."
    else:
        summary = "Runtime is bound to the fixed BRC testnet profile. Guard state still controls whether actions are allowed."

    return RuntimeSafetyResponse(
        runtime_bound=runtime_context is not None,
        profile=profile,
        testnet=testnet,
        gks_active=gks_active,
        startup_guard_armed=startup_guard_armed,
        human_summary=summary,
    )
