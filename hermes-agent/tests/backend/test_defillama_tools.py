from __future__ import annotations

from backend.integrations import DefiLlamaClient, DefiLlamaEndpointUnavailableError
from backend.models import (
    DefiChainOverview,
    DefiMetricOverview,
    DefiOpenInterestOverview,
    DefiRegimeSummary,
)
from backend.tools.get_defi_chain_overview import get_defi_chain_overview
from backend.tools.get_defi_dex_overview import get_defi_dex_overview
from backend.tools.get_defi_fees_overview import get_defi_fees_overview
from backend.tools.get_defi_open_interest import get_defi_open_interest
from backend.tools.get_defi_protocol_details import get_defi_protocol_details
from backend.tools.get_defi_protocols import get_defi_protocols
from backend.tools.get_defi_regime_summary import get_defi_regime_summary
from backend.tools.get_defi_yields import get_defi_yields


def test_defi_protocol_and_chain_tools_are_normalized(monkeypatch):
    def fake_request_json(self, path, *, params=None):
        if path == "/protocols":
            return [
                {
                    "id": "1599",
                    "name": "Aave V3",
                    "slug": "aave-v3",
                    "symbol": "AAVE",
                    "category": "Lending",
                    "chain": "Multi-Chain",
                    "chains": ["Ethereum", "Base"],
                    "tvl": 25000000000,
                    "change_1d": 1.5,
                    "change_7d": 9.25,
                    "mcap": 3200000000,
                    "url": "https://aave.com",
                    "description": "Earn interest, borrow assets, and build applications",
                    "listedAt": 1648776877,
                }
            ]
        if path == "/protocol/aave-v3":
            return {
                "id": "1599",
                "name": "Aave V3",
                "slug": "aave-v3",
                "symbol": "AAVE",
                "category": "Lending",
                "chains": ["Ethereum", "Base"],
                "currentChainTvls": {"Ethereum": 21000000000, "Base": 700000000},
                "chainTvls": {
                    "Ethereum": {"tvl": [{"date": 1, "totalLiquidityUSD": 21000000000}]},
                    "Base": {"tvl": [{"date": 1, "totalLiquidityUSD": 700000000}]},
                },
                "tvl": 21700000000,
                "mcap": 3200000000,
                "url": "https://aave.com",
                "description": "Earn interest, borrow assets, and build applications",
                "methodology": "Collateral locked in protocol contracts.",
                "audits": "2",
                "github": ["aave"],
                "twitter": "aave",
                "stablecoins": ["gho"],
            }
        if path == "/v2/chains":
            return [
                {"name": "Ethereum", "tokenSymbol": "ETH", "gecko_id": "ethereum", "cmcId": "1027", "chainId": 1, "tvl": 52000000000},
                {"name": "Base", "tokenSymbol": None, "gecko_id": "base", "cmcId": None, "chainId": 8453, "tvl": 4500000000},
            ]
        raise AssertionError(path)

    monkeypatch.setattr(DefiLlamaClient, "request_json", fake_request_json)

    protocols_payload = get_defi_protocols({"category": "Lending", "limit": 5})
    details_payload = get_defi_protocol_details({"slug": "aave-v3"})
    chains_payload = get_defi_chain_overview({"limit": 2})

    assert protocols_payload["meta"]["ok"] is True
    assert protocols_payload["data"][0]["slug"] == "aave-v3"
    assert details_payload["data"]["current_chain_tvls"]["Ethereum"] == 21000000000
    assert chains_payload["data"][0]["name"] == "Ethereum"


def test_defi_dimension_tools_are_normalized(monkeypatch):
    def fake_request_json(self, path, *, params=None):
        if path == "/overview/dexs":
            return {
                "total24h": 1000,
                "total7d": 9000,
                "total30d": 40000,
                "totalAllTime": 999999,
                "change_1d": 12.5,
                "change_7d": 8.0,
                "change_1m": 4.0,
                "allChains": ["Ethereum", "Base"],
                "protocols": [
                    {
                        "defillamaId": "1",
                        "name": "Uniswap",
                        "displayName": "Uniswap",
                        "slug": "uniswap",
                        "category": "Dexes",
                        "protocolType": "protocol",
                        "chains": ["Ethereum", "Base"],
                        "total24h": 500,
                        "total7d": 4000,
                        "total30d": 15000,
                        "totalAllTime": 500000,
                        "change_1d": 10.0,
                        "change_7d": 5.0,
                        "change_1m": 2.0,
                        "methodology": {"Volume": "Swap volume"},
                    }
                ],
            }
        if path == "/overview/fees":
            return {
                "total24h": 250,
                "total7d": 1800,
                "total30d": 7000,
                "totalAllTime": 55555,
                "change_1d": -3.0,
                "change_7d": 6.5,
                "change_1m": 1.0,
                "allChains": ["Ethereum", "Base"],
                "protocols": [
                    {
                        "defillamaId": "2",
                        "name": "Aave",
                        "displayName": "Aave",
                        "slug": "aave",
                        "category": "Lending",
                        "protocolType": "protocol",
                        "chains": ["Ethereum", "Base"],
                        "total24h": 100,
                        "total7d": 700,
                        "total30d": 2900,
                        "totalAllTime": 18000,
                        "change_1d": -1.0,
                        "change_7d": 4.0,
                        "change_1m": 2.0,
                        "methodology": {"Fees": "Borrow fees"},
                    }
                ],
            }
        raise AssertionError(path)

    monkeypatch.setattr(DefiLlamaClient, "request_json", fake_request_json)

    dex_payload = get_defi_dex_overview({"limit": 5})
    fees_payload = get_defi_fees_overview({"limit": 5})

    assert dex_payload["meta"]["ok"] is True
    assert dex_payload["data"]["metric"] == "dex_volume"
    assert dex_payload["data"]["top_protocols"][0]["name"] == "Uniswap"
    assert fees_payload["data"]["metric"] == "fees"
    assert fees_payload["data"]["top_protocols"][0]["methodology_notes"] == ["Fees: Borrow fees"]


def test_defi_open_interest_uses_partial_fallback(monkeypatch):
    def fake_request_json(self, path, *, params=None):
        if path == "/overview/derivatives":
            raise DefiLlamaEndpointUnavailableError("DefiLlama endpoint /overview/derivatives requires a paid API plan.")
        if path == "/protocols":
            return [
                {
                    "id": "d1",
                    "name": "Hyperliquid",
                    "slug": "hyperliquid",
                    "symbol": "HYPE",
                    "category": "Derivatives",
                    "chain": "Hyperliquid L1",
                    "chains": ["Hyperliquid L1"],
                    "tvl": 123456789,
                    "change_1d": 3.0,
                    "change_7d": 14.0,
                }
            ]
        raise AssertionError(path)

    monkeypatch.setattr(DefiLlamaClient, "request_json", fake_request_json)

    payload = get_defi_open_interest({"limit": 5})

    assert payload["meta"]["ok"] is True
    assert payload["meta"]["warnings"] == ["open_interest_endpoint_unavailable_on_free_api"]
    assert payload["data"]["access_level"] == "partial"
    assert payload["data"]["top_protocols"][0]["tvl_proxy_usd"] == 123456789


def test_defi_yields_fail_safely_when_endpoint_missing(monkeypatch):
    def fake_request_json(self, path, *, params=None):
        raise DefiLlamaEndpointUnavailableError("DefiLlama endpoint /pools is not available on the configured free API base URL.")

    monkeypatch.setattr(DefiLlamaClient, "request_json", fake_request_json)

    payload = get_defi_yields({"limit": 5})

    assert payload["meta"]["ok"] is False
    assert payload["data"]["error"] == "endpoint_not_available"


def test_defi_regime_summary_handles_partial_surface(monkeypatch):
    summary = DefiRegimeSummary(
        regime="expansionary_defi_risk",
        risk_bias="risk_on",
        summary="Test summary",
        signals=[],
        top_chains=[
            DefiChainOverview(name="Ethereum", token_symbol="ETH", gecko_id="ethereum", cmc_id="1027", chain_id=1, tvl=52000000000),
            DefiChainOverview(name="Base", token_symbol=None, gecko_id="base", cmc_id=None, chain_id=8453, tvl=4500000000),
        ],
        top_yields=[],
        dex=DefiMetricOverview(metric="dex_volume", total_24h=1000, total_7d=9000, total_30d=40000, total_all_time=999999, change_1d_pct=8.0, change_7d_pct=11.0, change_1m_pct=4.0, all_chains=["Ethereum", "Base"], top_protocols=[]),
        fees=DefiMetricOverview(metric="fees", total_24h=250, total_7d=1800, total_30d=7000, total_all_time=55555, change_1d_pct=2.0, change_7d_pct=7.0, change_1m_pct=1.0, all_chains=["Ethereum", "Base"], top_protocols=[]),
        open_interest=DefiOpenInterestOverview(
            access_level="partial",
            endpoint="/overview/derivatives",
            summary="Partial fallback",
            warnings=["open_interest_endpoint_unavailable_on_free_api"],
        ),
        watch_items=["Open-interest read is partial."],
    )

    monkeypatch.setattr(DefiLlamaClient, "get_regime_summary", lambda self, **kwargs: summary)

    payload = get_defi_regime_summary({})

    assert payload["meta"]["ok"] is True
    assert payload["data"]["risk_bias"] == "risk_on"
    assert payload["meta"]["warnings"] == ["open_interest_endpoint_unavailable_on_free_api"]
