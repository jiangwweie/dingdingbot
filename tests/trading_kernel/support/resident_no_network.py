"""Fail-on-network public source for Static resident process verification."""


class NoNetworkMarket:
    async def fetch_closed_candles(self, request):
        raise AssertionError("Static resident must not request market candles")

    async def fetch_generic_selection_qualifications(self, **kwargs):
        raise AssertionError("Static resident must not request qualifications")

    async def fetch_generic_selection_klines(self, request):
        raise AssertionError("Static resident must not request Selection candles")
