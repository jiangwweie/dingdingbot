"""Bounded Feishu transport only. No trading, templates or background threads."""

from urllib.parse import urlsplit

import aiohttp


class FeishuChannel:
    def __init__(self, webhook: str | None):
        self._webhook = (webhook or "").strip()
        if self._webhook:
            target = urlsplit(self._webhook)
            if (
                target.scheme != "https"
                or target.netloc != "open.feishu.cn"
                or not target.path.startswith("/open-apis/bot/v2/hook/")
                or target.query
                or target.fragment
            ):
                raise ValueError("invalid_feishu_route")

    @property
    def configured(self) -> bool:
        return bool(self._webhook)

    async def send(self, message: str) -> None:
        if not self.configured:
            raise ValueError("feishu_route_missing")
        async with (
            aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as session,
            session.post(
                self._webhook,
                json={"msg_type": "text", "content": {"text": message}},
                allow_redirects=False,
            ) as response,
        ):
            if response.status != 200:
                raise ValueError("feishu_http_rejected")
            chunks: list[bytes] = []
            size = 0
            while chunk := await response.content.read(8192):
                size += len(chunk)
                if size > 65536:
                    raise ValueError("feishu_response_oversized")
                chunks.append(chunk)
            raw = b"".join(chunks)
            import json

            result = json.loads(raw)
            if result.get("code", result.get("StatusCode")) != 0:
                raise ValueError("feishu_platform_rejected")


def load_feishu_channel(webhook: str | None) -> FeishuChannel:
    """Only the independent Seoul environment variable is supplied at startup."""
    return FeishuChannel(webhook)
