from unittest.mock import AsyncMock, Mock

import pytest

from src.trading_kernel.infrastructure.feishu_notice import (
    FeishuChannel,
    load_feishu_channel,
)


@pytest.mark.parametrize(
    "route",
    [
        "http://open.feishu.cn/open-apis/bot/v2/hook/test",
        "https://evil.example/open-apis/bot/v2/hook/test",
        "https://open.feishu.cn.evil.example/open-apis/bot/v2/hook/test",
        "https://open.feishu.cn/other",
        "https://open.feishu.cn/open-apis/bot/v2/hook/test?token=secret",
    ],
)
def test_transport_rejects_noncanonical_routes_without_echoing_secret(route):
    with pytest.raises(ValueError, match="^invalid_feishu_route$"):
        FeishuChannel(route)


def test_absent_independent_credential_never_uses_inherited_webhook(
    tmp_path, monkeypatch
):
    monkeypatch.setenv(
        "TRADING_KERNEL_FEISHU_WEBHOOK_URL",
        "https://open.feishu.cn/open-apis/bot/v2/hook/tokyo",
    )
    assert not load_feishu_channel(None).configured


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,status,accepted",
    [
        (b'{"code":0}', 200, True),
        (b'{"code":19024}', 200, False),
        (b"bad", 503, False),
        (b"x" * 65537, 200, False),
    ],
)
async def test_platform_acceptance_is_required_and_no_redirect_allowed(
    monkeypatch, response, status, accepted
):
    from src.trading_kernel.infrastructure import feishu_notice as module

    reply = Mock(status=status)
    reply.content.read = AsyncMock(side_effect=[response,b""])
    request = AsyncMock()
    request.__aenter__.return_value = reply
    session = Mock()
    session.post.return_value = request
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(module.aiohttp, "ClientSession", Mock(return_value=context))
    channel = FeishuChannel("https://open.feishu.cn/open-apis/bot/v2/hook/test")
    if accepted:
        await channel.send("frozen facts")
    else:
        with pytest.raises(ValueError):
            await channel.send("frozen facts")
    assert session.post.call_args.kwargs["allow_redirects"] is False
    assert session.post.call_args.kwargs["json"]["content"]["text"] == "frozen facts"
