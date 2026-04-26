from __future__ import annotations

from backend.integrations.derivatives.bitmart_public_client import BitMartPublicClient


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("GET", "https://example.invalid")
            response = httpx.Response(self.status_code, request=request, json=self._payload)
            raise httpx.HTTPStatusError("boom", request=request, response=response)

    def json(self) -> dict:
        return self._payload


def test_get_recent_trades_uses_market_trade_endpoint_and_parses_side(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def _fake_get(path: str, params: dict[str, object]):
        seen["path"] = path
        seen["params"] = params
        return _FakeResponse(
            {
                "code": 1000,
                "message": "Ok",
                "data": {
                    "trades": [
                        {
                            "symbol": "BTCUSDT",
                            "deal_price": "77726.7",
                            "deal_vol": "0.002",
                            "way": 2,
                            "create_time": 1777111587000,
                        },
                        {
                            "symbol": "BTCUSDT",
                            "deal_price": "77726.8",
                            "deal_vol": "0.003",
                            "way": 1,
                            "create_time": 1777111588000,
                        },
                    ]
                },
            }
        )

    client = BitMartPublicClient()
    monkeypatch.setattr(client._client, "get", _fake_get)

    snapshot = client.get_recent_trades("BTCUSDT", limit=2)

    assert seen["path"] == "/contract/public/trades"
    assert snapshot.symbol == "BTCUSDT"
    assert len(snapshot.trades) == 2
    assert snapshot.trades[0].side == "sell"
    assert snapshot.trades[1].side == "buy"
    assert snapshot.sell_count == 1
    assert snapshot.buy_count == 1