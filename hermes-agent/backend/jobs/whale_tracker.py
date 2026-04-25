"""Whale tracker job powered by BitMart Wallet AI smart-money endpoints."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.event_bus.models import TradingEvent
from backend.event_bus.publisher import TradingEventPublisher
from backend.integrations.onchain.bitmart_wallet_client import BitMartWalletAIClient
from backend.redis_client import get_redis_client
from backend.strategies.whale_follower import TRACKED_BASE_SYMBOLS

logger = logging.getLogger(__name__)

SUPPORTED_CHAINS: dict[int, str] = {
    2001: "Solana",
    2002: "BSC",
    2003: "Ethereum",
    2004: "Arbitrum",
    2007: "Base",
}
TOP_WALLET_LIMIT = 50
LOOKBACK_WINDOW = timedelta(hours=1)
MIN_ACCUMULATION_USD = 50_000.0
_TRADE_DEDUPE_TTL_SECONDS = 2 * 60 * 60


@dataclass(slots=True)
class WhaleFlowEmission:
    symbol: str
    total_accumulation_usd: float
    unique_wallet_count: int
    trade_count: int
    latest_trade_at: str
    chains: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WhaleTrackerSummary:
    ranked_wallets: int = 0
    scanned_wallets: int = 0
    new_trades: int = 0
    duplicate_trades_skipped: int = 0
    emitted_events: int = 0
    emissions: list[WhaleFlowEmission] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Whale tracker",
            "",
            f"- Ranked wallets considered: {self.ranked_wallets}",
            f"- Wallets scanned: {self.scanned_wallets}",
            f"- New qualifying trades: {self.new_trades}",
            f"- Duplicate trades skipped: {self.duplicate_trades_skipped}",
            f"- Events emitted: {self.emitted_events}",
        ]

        if self.emissions:
            lines.extend(["", "## Emitted whale flows", ""])
            for emission in self.emissions:
                chains = ", ".join(emission.chains) or "unknown"
                lines.append(
                    f"- `{emission.symbol}` ${emission.total_accumulation_usd:,.0f} across "
                    f"{emission.unique_wallet_count} wallets / {emission.trade_count} trades "
                    f"({chains}) latest `{emission.latest_trade_at}`"
                )
        else:
            lines.extend(["", "No new whale-flow events crossed the emission threshold."])

        return "\n".join(lines)


@dataclass(slots=True)
class _AggregatedFlow:
    base_symbol: str
    total_accumulation_usd: float = 0.0
    trade_count: int = 0
    latest_trade_at: datetime | None = None
    wallets: dict[str, dict[str, Any]] = field(default_factory=dict)
    tx_hashes: list[str] = field(default_factory=list)
    chains: set[str] = field(default_factory=set)
    profit_rate_samples: list[float] = field(default_factory=list)
    win_rate_samples: list[float] = field(default_factory=list)

    def record_trade(
        self,
        *,
        wallet_address: str,
        chain_name: str,
        amount_usd: float,
        trade_time: datetime,
        tx_hash: str | None,
        profit_rate_7d: float | None,
        win_rate_7d: float | None,
    ) -> None:
        self.total_accumulation_usd += amount_usd
        self.trade_count += 1
        self.latest_trade_at = max(filter(None, [self.latest_trade_at, trade_time]))
        self.chains.add(chain_name)
        if tx_hash:
            self.tx_hashes.append(tx_hash)
        wallet_entry = self.wallets.setdefault(
            wallet_address,
            {
                "wallet_address": wallet_address,
                "chain": chain_name,
                "accumulation_usd": 0.0,
                "trade_count": 0,
                "profit_rate_7d": profit_rate_7d,
                "win_rate_7d": win_rate_7d,
            },
        )
        wallet_entry["accumulation_usd"] = float(wallet_entry["accumulation_usd"]) + amount_usd
        wallet_entry["trade_count"] = int(wallet_entry["trade_count"]) + 1
        if profit_rate_7d is not None:
            wallet_entry["profit_rate_7d"] = profit_rate_7d
            self.profit_rate_samples.append(profit_rate_7d)
        if win_rate_7d is not None:
            wallet_entry["win_rate_7d"] = win_rate_7d
            self.win_rate_samples.append(win_rate_7d)

    def to_payload(self) -> dict[str, Any]:
        latest_trade_at = self.latest_trade_at.astimezone(UTC).isoformat() if self.latest_trade_at else None
        wallet_rows = sorted(
            self.wallets.values(),
            key=lambda row: (float(row.get("accumulation_usd") or 0.0), int(row.get("trade_count") or 0)),
            reverse=True,
        )
        avg_profit_rate = (
            sum(self.profit_rate_samples) / len(self.profit_rate_samples)
            if self.profit_rate_samples
            else None
        )
        avg_win_rate = (
            sum(self.win_rate_samples) / len(self.win_rate_samples)
            if self.win_rate_samples
            else None
        )
        return {
            "base_symbol": self.base_symbol,
            "symbol": f"{self.base_symbol}USDT",
            "direction": "accumulation",
            "total_accumulation_usd": round(self.total_accumulation_usd, 2),
            "trade_count": self.trade_count,
            "unique_wallet_count": len(wallet_rows),
            "wallets": wallet_rows,
            "chains": sorted(self.chains),
            "latest_trade_at": latest_trade_at,
            "window_minutes": int(LOOKBACK_WINDOW.total_seconds() // 60),
            "threshold_usd": MIN_ACCUMULATION_USD,
            "avg_profit_rate_7d": round(avg_profit_rate, 2) if avg_profit_rate is not None else None,
            "avg_win_rate_7d": round(avg_win_rate, 2) if avg_win_rate is not None else None,
            "tx_hashes": self.tx_hashes[:20],
            "source": "bitmart_wallet_ai",
            "strategy": "whale_follower",
        }


def run_whale_tracker(
    *,
    client: BitMartWalletAIClient | None = None,
    publisher: TradingEventPublisher | None = None,
    redis_client: Any | None = None,
    now: datetime | None = None,
    top_wallet_limit: int = TOP_WALLET_LIMIT,
) -> WhaleTrackerSummary:
    client = client or BitMartWalletAIClient()
    publisher = publisher or TradingEventPublisher()
    redis_client = redis_client or get_redis_client()
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    cutoff = observed_at - LOOKBACK_WINDOW

    summary = WhaleTrackerSummary()
    ranking_limit = max(top_wallet_limit, 100)
    wallet_rows = client.list_smart_money_wallets(limit=ranking_limit)
    supported_wallets = [
        row for row in wallet_rows if _coerce_int(row.get("chainId")) in SUPPORTED_CHAINS
    ][:top_wallet_limit]
    summary.ranked_wallets = len(supported_wallets)

    aggregated_flows: dict[str, _AggregatedFlow] = {}

    for wallet_row in supported_wallets:
        wallet_address = str(wallet_row.get("walletAddress") or "").strip()
        if not wallet_address:
            continue

        wallet_info = client.get_smart_money_info(wallet_address)
        summary.scanned_wallets += 1

        profit_info = wallet_info.get("profitInfo") if isinstance(wallet_info, dict) else {}
        profit_rate_7d = _to_float((profit_info or {}).get("profitRate7d") or wallet_row.get("profitRate7d"))
        win_rate_7d = _to_float((profit_info or {}).get("winRate7d") or wallet_row.get("winRate7d"))

        for trade in wallet_info.get("tradeHistory") or []:
            if not isinstance(trade, dict):
                continue
            if str(trade.get("tradeDirection") or "").upper() != "BUY":
                continue

            base_symbol = _normalize_base_symbol(trade.get("tokenSymbol"))
            if base_symbol not in TRACKED_BASE_SYMBOLS:
                continue

            chain_id = _coerce_int(trade.get("chainId") or wallet_row.get("chainId"))
            if chain_id not in SUPPORTED_CHAINS:
                continue

            trade_time = _parse_timestamp(trade.get("tradeTime"))
            if trade_time is None or trade_time < cutoff:
                continue

            total_usd = _to_float(trade.get("totalUSD"))
            if total_usd is None or total_usd <= 0:
                continue

            trade_key = _trade_dedupe_key(
                wallet_address=wallet_address,
                chain_id=chain_id,
                base_symbol=base_symbol,
                trade=trade,
            )
            if not _claim_trade(redis_client, trade_key):
                summary.duplicate_trades_skipped += 1
                continue

            summary.new_trades += 1
            aggregate = aggregated_flows.setdefault(base_symbol, _AggregatedFlow(base_symbol=base_symbol))
            aggregate.record_trade(
                wallet_address=wallet_address,
                chain_name=SUPPORTED_CHAINS[chain_id],
                amount_usd=total_usd,
                trade_time=trade_time,
                tx_hash=str(trade.get("txHash") or "").strip() or None,
                profit_rate_7d=profit_rate_7d,
                win_rate_7d=win_rate_7d,
            )

    for base_symbol, aggregate in sorted(aggregated_flows.items()):
        if aggregate.total_accumulation_usd < MIN_ACCUMULATION_USD:
            continue

        payload = aggregate.to_payload()
        publisher.publish(
            TradingEvent(
                event_type="whale_flow",
                source="bitmart_wallet_ai",
                producer="backend.jobs.whale_tracker",
                symbol=f"{base_symbol}USDT",
                payload=payload,
                metadata={
                    "job": "whale_tracker",
                    "tracked_universe": list(TRACKED_BASE_SYMBOLS),
                    "observed_at": observed_at.isoformat(),
                },
            )
        )
        summary.emitted_events += 1
        summary.emissions.append(
            WhaleFlowEmission(
                symbol=f"{base_symbol}USDT",
                total_accumulation_usd=payload["total_accumulation_usd"],
                unique_wallet_count=payload["unique_wallet_count"],
                trade_count=payload["trade_count"],
                latest_trade_at=payload.get("latest_trade_at") or observed_at.isoformat(),
                chains=list(payload.get("chains") or []),
            )
        )

    return summary


def main() -> int:
    summary = run_whale_tracker()
    print(summary.to_markdown())
    return 0


def _claim_trade(redis_client: Any, trade_key: str) -> bool:
    try:
        claimed = redis_client.set(trade_key, "1", ex=_TRADE_DEDUPE_TTL_SECONDS, nx=True)
        return bool(claimed)
    except Exception as exc:
        logger.warning("whale_tracker: failed to dedupe trade %s: %s", trade_key, exc)
        return True


def _trade_dedupe_key(*, wallet_address: str, chain_id: int, base_symbol: str, trade: dict[str, Any]) -> str:
    raw_key = "|".join(
        [
            wallet_address,
            str(chain_id),
            base_symbol,
            str(trade.get("txHash") or ""),
            str(trade.get("tradeTime") or ""),
            str(trade.get("quantity") or ""),
            str(trade.get("totalUSD") or ""),
        ]
    )
    digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()
    return f"hermes:whale_tracker:trade:{digest}"


def _normalize_base_symbol(value: Any) -> str:
    symbol = str(value or "").upper().strip()
    for suffix in ("USDT", "USDC", "USD", "/USDT", "/USD"):
        if symbol.endswith(suffix):
            symbol = symbol[: -len(suffix)]
    return symbol.strip(" /")


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        numeric = float(raw)
    except ValueError:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
    if numeric > 10_000_000_000:
        numeric /= 1000.0
    return datetime.fromtimestamp(numeric, tz=UTC)


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())