"""Normalized models shared by trading integrations and internal tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProviderStatus(BaseModel):
    provider: str
    ok: bool
    detail: str | None = None


class ToolEnvelope(BaseModel):
    ok: bool = True
    source: str
    providers: list[ProviderStatus] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PriceQuote(BaseModel):
    symbol: str
    price: float | None = None
    currency: str = "USD"
    change_24h_pct: float | None = None
    market_cap: float | None = None
    volume_24h: float | None = None
    rank: int | None = None
    as_of: str | None = None


class MarketOverview(BaseModel):
    regime: str = "unknown"
    btc_dominance: float | None = None
    total_market_cap: float | None = None
    total_volume_24h: float | None = None
    fear_greed_proxy: str | None = None
    narrative_summary: str | None = None
    as_of: str | None = None


class OHLCVBar(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class IndicatorSnapshot(BaseModel):
    symbol: str
    interval: str
    sma_20: float | None = None
    ema_20: float | None = None
    rsi_14: float | None = None
    atr_14: float | None = None
    volatility_30d: float | None = None


class NewsItem(BaseModel):
    title: str
    url: str | None = None
    published_at: str | None = None
    source: str | None = None
    sentiment: Literal["positive", "neutral", "negative"] | None = None
    summary: str | None = None
    assets: list[str] = Field(default_factory=list)


class SentimentSnapshot(BaseModel):
    symbol: str
    score: float | None = None
    engagement: float | None = None
    contributors: int | None = None
    trend: str | None = None
    as_of: str | None = None


class WalletTransaction(BaseModel):
    tx_hash: str
    timestamp: str | None = None
    direction: Literal["in", "out", "internal", "unknown"] = "unknown"
    asset: str | None = None
    amount: float | None = None
    counterparty: str | None = None


class WalletData(BaseModel):
    wallet: str
    chain: str = "ethereum"
    balance_native: float | None = None
    token_count: int | None = None
    tx_count: int | None = None
    recent_transactions: list[WalletTransaction] = Field(default_factory=list)


class SmartMoneyFlow(BaseModel):
    asset: str
    timeframe: str
    netflow_usd: float | None = None
    smart_wallet_count: int | None = None
    labels: list[str] = Field(default_factory=list)
    summary: str | None = None


class EventRiskSummary(BaseModel):
    headline_risk: str = "unknown"
    severity: Literal["low", "medium", "high"] = "medium"
    summary: str
    catalysts: list[str] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)


class MacroSeries(BaseModel):
    series_id: str
    title: str
    frequency: str | None = None
    units: str | None = None
    seasonal_adjustment: str | None = None
    popularity: int | None = None
    observation_start: str | None = None
    observation_end: str | None = None
    last_updated: str | None = None
    notes: str | None = None


class MacroSeriesLookup(BaseModel):
    query: str | None = None
    requested_series_id: str | None = None
    count: int
    results: list[MacroSeries] = Field(default_factory=list)


class MacroObservation(BaseModel):
    series_id: str
    date: str
    value: float | None = None
    raw_value: str | None = None
    realtime_start: str | None = None
    realtime_end: str | None = None


class MacroObservationWindow(BaseModel):
    series: MacroSeries
    count: int
    observations: list[MacroObservation] = Field(default_factory=list)


class MacroRegimeIndicator(BaseModel):
    series_id: str
    title: str
    units: str | None = None
    latest_value: float | None = None
    previous_value: float | None = None
    change: float | None = None
    trend: Literal["up", "down", "flat", "unknown"] = "unknown"
    interpretation: str
    as_of: str | None = None


class MacroRegimeSummary(BaseModel):
    regime: str
    risk_bias: Literal["risk_on", "risk_off", "mixed"]
    summary: str
    indicators: list[MacroRegimeIndicator] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    as_of: str | None = None


class EventRiskMacroContext(BaseModel):
    event: str
    regime: str
    risk_bias: Literal["risk_on", "risk_off", "mixed"]
    summary: str
    indicators: list[MacroRegimeIndicator] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    as_of: str | None = None


class DefiProtocolSummary(BaseModel):
    protocol_id: str
    name: str
    slug: str
    symbol: str | None = None
    category: str | None = None
    chain: str | None = None
    chains: list[str] = Field(default_factory=list)
    tvl: float | None = None
    tvl_change_1d_pct: float | None = None
    tvl_change_7d_pct: float | None = None
    mcap: float | None = None
    url: str | None = None
    description: str | None = None
    listed_at: int | None = None


class DefiProtocolDetails(BaseModel):
    protocol_id: str
    name: str
    slug: str
    symbol: str | None = None
    category: str | None = None
    chains: list[str] = Field(default_factory=list)
    current_chain_tvls: dict[str, float | None] = Field(default_factory=dict)
    chain_tvls: dict[str, float | None] = Field(default_factory=dict)
    tvl: float | None = None
    mcap: float | None = None
    url: str | None = None
    description: str | None = None
    methodology: str | None = None
    audits: int | None = None
    github: list[str] = Field(default_factory=list)
    twitter: str | None = None
    stablecoins: list[str] = Field(default_factory=list)


class DefiChainOverview(BaseModel):
    name: str
    token_symbol: str | None = None
    gecko_id: str | None = None
    cmc_id: str | None = None
    chain_id: int | None = None
    tvl: float | None = None


class DefiYieldPool(BaseModel):
    pool: str
    project: str
    chain: str
    symbol: str | None = None
    stablecoin: bool | None = None
    tvl_usd: float | None = None
    apy: float | None = None
    apy_base: float | None = None
    apy_reward: float | None = None
    reward_tokens: list[str] = Field(default_factory=list)
    exposure: str | None = None
    il_risk: str | None = None
    underlying_tokens: list[str] = Field(default_factory=list)
    url: str | None = None


class DefiMetricProtocolOverview(BaseModel):
    protocol_id: str
    name: str
    display_name: str | None = None
    slug: str | None = None
    category: str | None = None
    protocol_type: str | None = None
    chains: list[str] = Field(default_factory=list)
    total_24h: float | None = None
    total_7d: float | None = None
    total_30d: float | None = None
    total_all_time: float | None = None
    change_1d_pct: float | None = None
    change_7d_pct: float | None = None
    change_1m_pct: float | None = None
    methodology_notes: list[str] = Field(default_factory=list)


class DefiMetricOverview(BaseModel):
    metric: Literal["dex_volume", "fees"]
    total_24h: float | None = None
    total_7d: float | None = None
    total_30d: float | None = None
    total_all_time: float | None = None
    change_1d_pct: float | None = None
    change_7d_pct: float | None = None
    change_1m_pct: float | None = None
    all_chains: list[str] = Field(default_factory=list)
    top_protocols: list[DefiMetricProtocolOverview] = Field(default_factory=list)
    as_of: str | None = None


class DefiOpenInterestProtocol(BaseModel):
    protocol_id: str
    name: str
    slug: str | None = None
    category: str | None = None
    chains: list[str] = Field(default_factory=list)
    open_interest_24h: float | None = None
    open_interest_7d: float | None = None
    change_1d_pct: float | None = None
    change_7d_pct: float | None = None
    tvl_proxy_usd: float | None = None
    note: str | None = None


class DefiOpenInterestOverview(BaseModel):
    metric: Literal["open_interest"] = "open_interest"
    access_level: Literal["full", "partial", "unavailable"] = "partial"
    endpoint: str
    summary: str
    total_24h: float | None = None
    total_7d: float | None = None
    change_1d_pct: float | None = None
    change_7d_pct: float | None = None
    top_protocols: list[DefiOpenInterestProtocol] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    as_of: str | None = None


class DefiRegimeSignal(BaseModel):
    name: str
    status: Literal["bullish", "bearish", "neutral", "unavailable"]
    detail: str
    value: float | None = None


class DefiRegimeSummary(BaseModel):
    regime: str
    risk_bias: Literal["risk_on", "risk_off", "mixed"]
    summary: str
    signals: list[DefiRegimeSignal] = Field(default_factory=list)
    top_chains: list[DefiChainOverview] = Field(default_factory=list)
    top_yields: list[DefiYieldPool] = Field(default_factory=list)
    dex: DefiMetricOverview | None = None
    fees: DefiMetricOverview | None = None
    open_interest: DefiOpenInterestOverview | None = None
    watch_items: list[str] = Field(default_factory=list)
    as_of: str | None = None


class PortfolioAsset(BaseModel):
    symbol: str
    quantity: float
    avg_entry: float | None = None
    mark_price: float | None = None
    notional_usd: float | None = None
    pnl_unrealized: float | None = None


class PortfolioState(BaseModel):
    account_id: str = "paper"
    total_equity_usd: float | None = None
    cash_usd: float | None = None
    exposure_usd: float | None = None
    positions: list[PortfolioAsset] = Field(default_factory=list)
    updated_at: str | None = None


class RiskApproval(BaseModel):
    approved: bool
    max_size_usd: float | None = None
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)
    stop_guidance: str | None = None


class NotificationResult(BaseModel):
    delivered: bool
    channel: str
    message_id: str | None = None
    detail: str | None = None
    channels: list[str] = Field(default_factory=list)
    notification_type: str = "generic"
    severity: str = "info"
    title: str | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)


class ListTradeCandidate(BaseModel):
    symbol: str
    direction: Literal["long", "short", "watch"]
    confidence: float
    rationale: str


class ExecutionBalance(BaseModel):
    asset: str
    free: float | None = None
    used: float | None = None
    total: float | None = None


class ExchangeBalances(BaseModel):
    exchange: str
    account_type: str = "spot"
    balances: list[ExecutionBalance] = Field(default_factory=list)
    as_of: str | None = None


class ExecutionOrder(BaseModel):
    order_id: str
    exchange: str
    symbol: str
    side: Literal["buy", "sell"] | None = None
    order_type: str | None = None
    status: str | None = None
    client_order_id: str | None = None
    price: float | None = None
    average_price: float | None = None
    amount: float | None = None
    filled: float | None = None
    remaining: float | None = None
    cost: float | None = None
    time_in_force: str | None = None
    post_only: bool | None = None
    reduce_only: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ExecutionTrade(BaseModel):
    trade_id: str
    order_id: str | None = None
    exchange: str
    symbol: str
    side: Literal["buy", "sell"] | None = None
    price: float | None = None
    amount: float | None = None
    cost: float | None = None
    fee_cost: float | None = None
    fee_currency: str | None = None
    liquidity: str | None = None
    timestamp: str | None = None


class ExecutionStatus(BaseModel):
    exchange: str
    configured: bool
    connected: bool
    rate_limit_enabled: bool
    account_type: str = "spot"
    readiness_status: str | None = None
    readiness: dict[str, Any] | None = None
    support_matrix: dict[str, Any] | None = None
    detail: str | None = None
    order: ExecutionOrder | None = None
    checked_at: str | None = None


class NormalizedResponse(BaseModel):
    meta: ToolEnvelope
    data: Any


# ---------------------------------------------------------------------------
# Order Book / Depth Feed
# ---------------------------------------------------------------------------

class OrderBookLevel(BaseModel):
    price: float
    amount: float
    exchange: str | None = None


class OrderBookSnapshot(BaseModel):
    symbol: str
    exchange: str
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)
    best_bid: float | None = None
    best_ask: float | None = None
    spread: float | None = None
    spread_pct: float | None = None
    bid_depth_usd: float | None = None
    ask_depth_usd: float | None = None
    imbalance: float | None = None
    as_of: str | None = None


# ---------------------------------------------------------------------------
# Derivatives & Funding Data
# ---------------------------------------------------------------------------

class FundingRateEntry(BaseModel):
    symbol: str
    exchange: str | None = None
    funding_rate: float | None = None
    funding_time: str | None = None
    mark_price: float | None = None
    index_price: float | None = None
    next_funding_time: str | None = None
    open_interest_usd: float | None = None


class FundingRatesSnapshot(BaseModel):
    symbols: list[FundingRateEntry] = Field(default_factory=list)
    as_of: str | None = None
    source: str = "derivatives_public"


class LiquidationEntry(BaseModel):
    symbol: str
    side: str | None = None
    price: float | None = None
    quantity: float | None = None
    usd_value: float | None = None
    timestamp: str | None = None


class LiquidationZonesSnapshot(BaseModel):
    symbol: str
    recent_liquidations: list[LiquidationEntry] = Field(default_factory=list)
    total_longs_liquidated_usd: float | None = None
    total_shorts_liquidated_usd: float | None = None
    dominant_side: str | None = None
    open_interest_usd: float | None = None
    long_short_ratio: float | None = None
    long_account_pct: float | None = None
    short_account_pct: float | None = None
    as_of: str | None = None


# ---------------------------------------------------------------------------
# Tape / Recent Trades Feed
# ---------------------------------------------------------------------------


class TradeRecord(BaseModel):
    """Single trade from the exchange public trade feed (tape/aggTrades)."""

    price: float
    size: float
    side: Literal["buy", "sell", "unknown"]
    timestamp: str


class RecentTradesSnapshot(BaseModel):
    """Recent public trades for a symbol (tape/time-and-sales)."""

    symbol: str
    exchange: str
    trades: list[TradeRecord] = Field(default_factory=list)
    buy_volume: float | None = None
    sell_volume: float | None = None
    buy_count: int | None = None
    sell_count: int | None = None
    vwap: float | None = None
    as_of: str | None = None


# ---------------------------------------------------------------------------
# Risk Policy State
# ---------------------------------------------------------------------------

class RiskState(BaseModel):
    kill_switch_active: bool = False
    kill_switch_reason: str | None = None
    kill_switch_set_at: str | None = None
    max_position_usd: float | None = None
    max_daily_loss_usd: float | None = None
    drawdown_limit_pct: float = 10.0
    carry_trade_max_equity_pct: float = 30.0
    current_equity_usd: float | None = None
    peak_equity_usd: float | None = None
    current_drawdown_pct: float | None = None
    warnings: list[str] = Field(default_factory=list)


class KillSwitchResult(BaseModel):
    success: bool
    active: bool
    reason: str | None = None
    set_at: str | None = None
