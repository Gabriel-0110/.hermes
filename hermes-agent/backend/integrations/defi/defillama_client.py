"""Shared DefiLlama client for normalized DeFi intelligence."""

from __future__ import annotations

import logging
from statistics import mean
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from backend.integrations.base import IntegrationError
from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.models import (
    DefiChainOverview,
    DefiMetricOverview,
    DefiMetricProtocolOverview,
    DefiOpenInterestOverview,
    DefiOpenInterestProtocol,
    DefiProtocolDetails,
    DefiProtocolSummary,
    DefiRegimeSignal,
    DefiRegimeSummary,
    DefiYieldPool,
)

logger = logging.getLogger(__name__)


class DefiLlamaEndpointUnavailableError(IntegrationError):
    """Raised when a requested DefiLlama capability is not available on the free API."""


class DefiLlamaClient:
    """Retrying DefiLlama client for Hermes' backend-only trading tools."""

    provider = PROVIDER_PROFILES["defillama"]
    base_url = "https://api.llama.fi"
    timeout_seconds = 20.0

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=True,
            headers={"User-Agent": "hermes-agent/trading-integrations"},
        )

    @property
    def configured(self) -> bool:
        return True

    @retry(
        retry=retry_if_exception(
            lambda exc: isinstance(exc, (httpx.HTTPError, IntegrationError))
            and not isinstance(exc, DefiLlamaEndpointUnavailableError)
        ),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def request_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self._client.get(path, params=params or {})
        if response.status_code == 402:
            raise DefiLlamaEndpointUnavailableError(
                f"DefiLlama endpoint {path} requires a paid API plan."
            )
        if response.status_code == 404:
            raise DefiLlamaEndpointUnavailableError(
                f"DefiLlama endpoint {path} is not available on the configured free API base URL."
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "DefiLlama request failed path=%s status=%s",
                path,
                exc.response.status_code,
            )
            raise IntegrationError(
                f"DefiLlama request failed with status {exc.response.status_code} for {path}"
            ) from exc
        return response.json()

    def get_protocols(
        self,
        *,
        limit: int = 25,
        category: str | None = None,
        chain: str | None = None,
        search: str | None = None,
    ) -> list[DefiProtocolSummary]:
        payload = self.request_json("/protocols")
        rows = list(payload if isinstance(payload, list) else [])

        if category:
            wanted = category.casefold()
            rows = [row for row in rows if str(row.get("category") or "").casefold() == wanted]
        if chain:
            wanted = chain.casefold()
            rows = [
                row
                for row in rows
                if wanted == str(row.get("chain") or "").casefold()
                or any(wanted == str(item).casefold() for item in (row.get("chains") or []))
            ]
        if search:
            needle = search.casefold()
            rows = [
                row
                for row in rows
                if needle in str(row.get("name") or "").casefold()
                or needle in str(row.get("slug") or "").casefold()
                or needle in str(row.get("symbol") or "").casefold()
            ]

        rows.sort(key=lambda row: self._to_float(row.get("tvl")) or 0.0, reverse=True)
        return [self._normalize_protocol_summary(row) for row in rows[:limit]]

    def get_protocol_details(self, slug: str) -> DefiProtocolDetails:
        payload = self.request_json(f"/protocol/{slug}")
        if not isinstance(payload, dict):
            raise IntegrationError(f"Unexpected DefiLlama protocol payload for slug={slug}")
        return self._normalize_protocol_details(payload)

    def get_chains_overview(self, *, limit: int = 25, search: str | None = None) -> list[DefiChainOverview]:
        payload = self.request_json("/v2/chains")
        rows = list(payload if isinstance(payload, list) else [])
        if search:
            needle = search.casefold()
            rows = [row for row in rows if needle in str(row.get("name") or "").casefold()]
        rows.sort(key=lambda row: self._to_float(row.get("tvl")) or 0.0, reverse=True)
        return [self._normalize_chain(row) for row in rows[:limit]]

    def get_yields(
        self,
        *,
        limit: int = 25,
        chain: str | None = None,
        project: str | None = None,
        stablecoin: bool | None = None,
        min_tvl: float | None = None,
        min_apy: float | None = None,
    ) -> list[DefiYieldPool]:
        payload = self.request_json("/pools")
        rows = list(payload.get("data", payload) if isinstance(payload, dict) else payload)
        rows = list(rows if isinstance(rows, list) else [])

        if chain:
            wanted = chain.casefold()
            rows = [row for row in rows if wanted == str(row.get("chain") or "").casefold()]
        if project:
            needle = project.casefold()
            rows = [row for row in rows if needle in str(row.get("project") or "").casefold()]
        if stablecoin is not None:
            rows = [row for row in rows if bool(row.get("stablecoin")) is stablecoin]
        if min_tvl is not None:
            rows = [row for row in rows if (self._to_float(row.get("tvlUsd")) or 0.0) >= min_tvl]
        if min_apy is not None:
            rows = [row for row in rows if (self._to_float(row.get("apy")) or 0.0) >= min_apy]

        rows.sort(key=lambda row: (self._to_float(row.get("apy")) or 0.0, self._to_float(row.get("tvlUsd")) or 0.0), reverse=True)
        return [self._normalize_yield_pool(row) for row in rows[:limit]]

    def get_dex_overview(self, *, limit: int = 20, chain: str | None = None) -> DefiMetricOverview:
        payload = self.request_json(
            "/overview/dexs",
            params={
                "excludeTotalDataChart": "true",
                "excludeTotalDataChartBreakdown": "true",
                **({"chain": chain} if chain else {}),
            },
        )
        return self._normalize_metric_overview("dex_volume", payload, limit=limit)

    def get_fees_overview(self, *, limit: int = 20, chain: str | None = None) -> DefiMetricOverview:
        payload = self.request_json(
            "/overview/fees",
            params={
                "excludeTotalDataChart": "true",
                "excludeTotalDataChartBreakdown": "true",
                **({"chain": chain} if chain else {}),
            },
        )
        return self._normalize_metric_overview("fees", payload, limit=limit)

    def get_open_interest_overview(self, *, limit: int = 20, chain: str | None = None) -> DefiOpenInterestOverview:
        try:
            payload = self.request_json(
                "/overview/derivatives",
                params={
                    "excludeTotalDataChart": "true",
                    "excludeTotalDataChartBreakdown": "true",
                    **({"chain": chain} if chain else {}),
                },
            )
            protocols = list(payload.get("protocols", []))[:limit] if isinstance(payload, dict) else []
            normalized = [
                DefiOpenInterestProtocol(
                    protocol_id=str(row.get("defillamaId") or row.get("id") or row.get("name") or ""),
                    name=str(row.get("displayName") or row.get("name") or "unknown"),
                    slug=row.get("slug"),
                    category=row.get("category"),
                    chains=list(row.get("chains") or []),
                    open_interest_24h=self._to_float(row.get("total24h")),
                    open_interest_7d=self._to_float(row.get("total7d")),
                    change_1d_pct=self._to_float(row.get("change_1d")),
                    change_7d_pct=self._to_float(row.get("change_7d")),
                )
                for row in protocols
            ]
            return DefiOpenInterestOverview(
                access_level="full",
                endpoint="/overview/derivatives",
                summary="Open-interest overview normalized directly from DefiLlama derivatives dimensions.",
                total_24h=self._to_float(payload.get("total24h")) if isinstance(payload, dict) else None,
                total_7d=self._to_float(payload.get("total7d")) if isinstance(payload, dict) else None,
                change_1d_pct=self._to_float(payload.get("change_1d")) if isinstance(payload, dict) else None,
                change_7d_pct=self._to_float(payload.get("change_7d")) if isinstance(payload, dict) else None,
                top_protocols=normalized,
            )
        except DefiLlamaEndpointUnavailableError:
            logger.info("DefiLlama free API does not expose /overview/derivatives; using derivatives TVL proxy fallback")

        derivatives = self.get_protocols(limit=max(limit * 3, 50), category="Derivatives", chain=chain)
        top_protocols = [
            DefiOpenInterestProtocol(
                protocol_id=item.protocol_id,
                name=item.name,
                slug=item.slug,
                category=item.category,
                chains=item.chains,
                tvl_proxy_usd=item.tvl,
                change_1d_pct=item.tvl_change_1d_pct,
                change_7d_pct=item.tvl_change_7d_pct,
                note="Free api.llama.fi access does not currently expose the derivatives open-interest overview endpoint; TVL trend is used as a derivatives activity proxy.",
            )
            for item in derivatives[:limit]
        ]
        return DefiOpenInterestOverview(
            access_level="partial",
            endpoint="/overview/derivatives",
            summary=(
                "Full open-interest data is not available from the current free api.llama.fi surface. "
                "Hermes is returning a derivatives-TVL proxy ranked from public protocol data instead."
            ),
            top_protocols=top_protocols,
            warnings=["open_interest_endpoint_unavailable_on_free_api"],
        )

    def get_regime_summary(
        self,
        *,
        chain_limit: int = 5,
        protocol_limit: int = 5,
        yield_limit: int = 5,
    ) -> DefiRegimeSummary:
        chains = self.get_chains_overview(limit=chain_limit)
        dex = self.get_dex_overview(limit=protocol_limit)
        fees = self.get_fees_overview(limit=protocol_limit)
        open_interest = self.get_open_interest_overview(limit=protocol_limit)

        try:
            yields = self.get_yields(limit=yield_limit, min_tvl=1_000_000)
        except DefiLlamaEndpointUnavailableError:
            yields = []

        signals: list[DefiRegimeSignal] = []
        score = 0

        score += self._append_change_signal(signals, "DEX activity", dex.change_7d_pct)
        score += self._append_change_signal(signals, "Fee momentum", fees.change_7d_pct)

        if open_interest.access_level == "full":
            score += self._append_change_signal(signals, "Open interest", open_interest.change_7d_pct)
        elif open_interest.access_level == "partial":
            signals.append(
                DefiRegimeSignal(
                    name="Open interest",
                    status="unavailable",
                    detail="Full open-interest endpoint requires paid access; using derivatives TVL proxy in the detail payload.",
                )
            )

        if yields:
            avg_apy = mean(pool.apy for pool in yields if pool.apy is not None) if any(pool.apy is not None for pool in yields) else None
            if avg_apy is not None and avg_apy >= 12:
                score += 1
                status = "bullish"
            elif avg_apy is not None and avg_apy <= 5:
                score -= 1
                status = "bearish"
            else:
                status = "neutral"
            signals.append(
                DefiRegimeSignal(
                    name="Yield backdrop",
                    status=status,
                    detail=f"Average APY across the sampled top yield pools is {avg_apy:.2f}%." if avg_apy is not None else "Yield pools returned without APY values.",
                    value=avg_apy,
                )
            )
        else:
            signals.append(
                DefiRegimeSignal(
                    name="Yield backdrop",
                    status="unavailable",
                    detail="Pools/yields are not currently exposed by the configured free api.llama.fi base URL.",
                )
            )

        if score >= 2:
            regime = "expansionary_defi_risk"
            risk_bias = "risk_on"
        elif score <= -2:
            regime = "defensive_defi_conditions"
            risk_bias = "risk_off"
        else:
            regime = "mixed_defi_transition"
            risk_bias = "mixed"

        watch_items = [
            f"Top DEX change_7d={dex.change_7d_pct}%",
            f"Top fees change_7d={fees.change_7d_pct}%",
        ]
        if open_interest.access_level != "full":
            watch_items.append("Open-interest read is partial because the free derivatives overview endpoint is currently unavailable.")
        if yields:
            watch_items.extend(
                f"{pool.project} on {pool.chain}: APY {pool.apy}% TVL ${int(pool.tvl_usd or 0):,}"
                for pool in yields[:3]
            )

        summary = (
            f"DefiLlama regime summary indicates {regime} with a {risk_bias} bias. "
            f"DEX volume change_7d={dex.change_7d_pct}%, fees change_7d={fees.change_7d_pct}%."
        )
        if open_interest.access_level == "partial":
            summary += " Open-interest is represented with a derivatives-TVL proxy because the free endpoint is unavailable."

        return DefiRegimeSummary(
            regime=regime,
            risk_bias=risk_bias,
            summary=summary,
            signals=signals,
            top_chains=chains,
            top_yields=yields,
            dex=dex,
            fees=fees,
            open_interest=open_interest,
            watch_items=watch_items,
        )

    def _normalize_protocol_summary(self, row: dict[str, Any]) -> DefiProtocolSummary:
        return DefiProtocolSummary(
            protocol_id=str(row.get("id") or row.get("slug") or row.get("name") or ""),
            name=str(row.get("name") or "unknown"),
            slug=str(row.get("slug") or row.get("name") or "").strip(),
            symbol=row.get("symbol"),
            category=row.get("category"),
            chain=row.get("chain"),
            chains=list(row.get("chains") or []),
            tvl=self._to_float(row.get("tvl")),
            tvl_change_1d_pct=self._to_float(row.get("change_1d")),
            tvl_change_7d_pct=self._to_float(row.get("change_7d")),
            mcap=self._to_float(row.get("mcap")),
            url=row.get("url"),
            description=row.get("description"),
            listed_at=self._to_int(row.get("listedAt")),
        )

    def _normalize_protocol_details(self, row: dict[str, Any]) -> DefiProtocolDetails:
        current_chain_tvls = {
            key: self._extract_current_tvl(value)
            for key, value in dict(row.get("currentChainTvls") or {}).items()
        }
        chain_tvls = {
            key: self._extract_chart_tvl(value)
            for key, value in dict(row.get("chainTvls") or {}).items()
        }
        return DefiProtocolDetails(
            protocol_id=str(row.get("id") or row.get("slug") or row.get("name") or ""),
            name=str(row.get("name") or "unknown"),
            slug=str(row.get("slug") or row.get("name") or "").strip(),
            symbol=row.get("symbol"),
            category=row.get("category"),
            chains=list(row.get("chains") or []),
            current_chain_tvls=current_chain_tvls,
            chain_tvls=chain_tvls,
            tvl=self._to_float(row.get("tvl")),
            mcap=self._to_float(row.get("mcap")),
            url=row.get("url"),
            description=row.get("description"),
            methodology=row.get("methodology"),
            audits=self._to_int(row.get("audits")),
            github=list(row.get("github") or []),
            twitter=row.get("twitter"),
            stablecoins=list(row.get("stablecoins") or []),
        )

    def _normalize_chain(self, row: dict[str, Any]) -> DefiChainOverview:
        return DefiChainOverview(
            name=str(row.get("name") or "unknown"),
            token_symbol=row.get("tokenSymbol"),
            gecko_id=row.get("gecko_id"),
            cmc_id=str(row.get("cmcId")) if row.get("cmcId") is not None else None,
            chain_id=self._to_int(row.get("chainId")),
            tvl=self._to_float(row.get("tvl")),
        )

    def _normalize_yield_pool(self, row: dict[str, Any]) -> DefiYieldPool:
        return DefiYieldPool(
            pool=str(row.get("pool") or row.get("id") or ""),
            project=str(row.get("project") or "unknown"),
            chain=str(row.get("chain") or "unknown"),
            symbol=row.get("symbol"),
            stablecoin=row.get("stablecoin"),
            tvl_usd=self._to_float(row.get("tvlUsd")),
            apy=self._to_float(row.get("apy")),
            apy_base=self._to_float(row.get("apyBase")),
            apy_reward=self._to_float(row.get("apyReward")),
            reward_tokens=list(row.get("rewardTokens") or []),
            exposure=row.get("exposure"),
            il_risk=row.get("ilRisk"),
            underlying_tokens=list(row.get("underlyingTokens") or []),
            url=row.get("url"),
        )

    def _normalize_metric_overview(self, metric: str, payload: Any, *, limit: int) -> DefiMetricOverview:
        if not isinstance(payload, dict):
            raise IntegrationError(f"Unexpected DefiLlama overview payload for {metric}")
        top_protocols = [
            DefiMetricProtocolOverview(
                protocol_id=str(row.get("defillamaId") or row.get("id") or row.get("name") or ""),
                name=str(row.get("name") or "unknown"),
                display_name=row.get("displayName"),
                slug=row.get("slug"),
                category=row.get("category"),
                protocol_type=row.get("protocolType"),
                chains=list(row.get("chains") or []),
                total_24h=self._to_float(row.get("total24h")),
                total_7d=self._to_float(row.get("total7d")),
                total_30d=self._to_float(row.get("total30d")),
                total_all_time=self._to_float(row.get("totalAllTime")),
                change_1d_pct=self._to_float(row.get("change_1d")),
                change_7d_pct=self._to_float(row.get("change_7d")),
                change_1m_pct=self._to_float(row.get("change_1m")),
                methodology_notes=self._flatten_methodology(row.get("methodology")),
            )
            for row in list(payload.get("protocols") or [])[:limit]
        ]
        return DefiMetricOverview(
            metric="dex_volume" if metric == "dex_volume" else "fees",
            total_24h=self._to_float(payload.get("total24h")),
            total_7d=self._to_float(payload.get("total7d")),
            total_30d=self._to_float(payload.get("total30d")),
            total_all_time=self._to_float(payload.get("totalAllTime")),
            change_1d_pct=self._to_float(payload.get("change_1d")),
            change_7d_pct=self._to_float(payload.get("change_7d")),
            change_1m_pct=self._to_float(payload.get("change_1m")),
            all_chains=list(payload.get("allChains") or []),
            top_protocols=top_protocols,
        )

    def _append_change_signal(self, signals: list[DefiRegimeSignal], name: str, change: float | None) -> int:
        if change is None:
            signals.append(DefiRegimeSignal(name=name, status="unavailable", detail=f"{name} change data is unavailable."))
            return 0
        if change >= 5:
            status = "bullish"
            score = 1
        elif change <= -5:
            status = "bearish"
            score = -1
        else:
            status = "neutral"
            score = 0
        signals.append(DefiRegimeSignal(name=name, status=status, detail=f"{name} changed {change:.2f}% over the sampled period.", value=change))
        return score

    @staticmethod
    def _flatten_methodology(methodology: Any) -> list[str]:
        if isinstance(methodology, dict):
            return [f"{key}: {value}" for key, value in methodology.items()]
        if isinstance(methodology, str) and methodology:
            return [methodology]
        return []

    @staticmethod
    def _extract_current_tvl(value: Any) -> float | None:
        if isinstance(value, dict):
            return DefiLlamaClient._to_float(value.get("totalLiquidityUSD") or value.get("tvl"))
        return DefiLlamaClient._to_float(value)

    @staticmethod
    def _extract_chart_tvl(value: Any) -> float | None:
        if isinstance(value, dict):
            tvl_rows = value.get("tvl")
            if isinstance(tvl_rows, list) and tvl_rows:
                latest = tvl_rows[-1]
                if isinstance(latest, dict):
                    return DefiLlamaClient._to_float(latest.get("totalLiquidityUSD"))
            return DefiLlamaClient._to_float(value.get("totalLiquidityUSD") or value.get("tvl"))
        return DefiLlamaClient._to_float(value)

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, "", "-", "."):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        if value in (None, "", "-", "."):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
