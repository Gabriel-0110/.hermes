"""Safe internal trading tools backed by backend-only integrations."""

from __future__ import annotations

import json

from backend.tools.get_asset_rankings import get_asset_rankings
from backend.tools.get_correlation_inputs import get_correlation_inputs
from backend.tools.get_crypto_news import get_crypto_news
from backend.tools.get_crypto_prices import get_crypto_prices
from backend.tools.get_defi_chain_overview import get_defi_chain_overview
from backend.tools.get_defi_dex_overview import get_defi_dex_overview
from backend.tools.get_defi_fees_overview import get_defi_fees_overview
from backend.tools.get_defi_open_interest import get_defi_open_interest
from backend.tools.get_defi_protocol_details import get_defi_protocol_details
from backend.tools.get_defi_protocols import get_defi_protocols
from backend.tools.get_defi_regime_summary import get_defi_regime_summary
from backend.tools.get_defi_yields import get_defi_yields
from backend.tools.get_exchange_balances import get_exchange_balances
from backend.tools.get_event_risk_summary import get_event_risk_summary
from backend.tools.get_event_risk_macro_context import get_event_risk_macro_context
from backend.tools.get_execution_status import get_execution_status
from backend.tools.get_general_news import get_general_news
from backend.tools.get_indicator_snapshot import get_indicator_snapshot
from backend.tools.get_labeled_wallet_activity import get_labeled_wallet_activity
from backend.tools.get_market_overview import get_market_overview
from backend.tools.get_macro_observations import get_macro_observations
from backend.tools.get_macro_regime_summary import get_macro_regime_summary
from backend.tools.get_macro_series import get_macro_series
from backend.tools.get_ohlcv import get_ohlcv
from backend.tools.get_onchain_signal_summary import get_onchain_signal_summary
from backend.tools.get_onchain_wallet_data import get_onchain_wallet_data
from backend.tools.get_portfolio_state import get_portfolio_state
from backend.tools.get_portfolio_valuation import get_portfolio_valuation
from backend.tools.get_recent_tradingview_alerts import get_recent_tradingview_alerts
from backend.tools.get_risk_approval import get_risk_approval
from backend.tools.get_smart_money_flows import get_smart_money_flows
from backend.tools.get_social_sentiment import get_social_sentiment
from backend.tools.get_social_spike_alerts import get_social_spike_alerts
from backend.tools.get_pending_signal_events import get_pending_signal_events
from backend.tools.get_tradingview_alert_by_symbol import get_tradingview_alert_by_symbol
from backend.tools.get_tradingview_alert_context import get_tradingview_alert_context
from backend.tools.get_open_orders import get_open_orders
from backend.tools.get_order_history import get_order_history
from backend.tools.get_trade_history import get_trade_history
from backend.tools.get_token_activity import get_token_activity
from backend.tools.get_volatility_metrics import get_volatility_metrics
from backend.tools.get_wallet_transactions import get_wallet_transactions
from backend.tools.list_trade_candidates import list_trade_candidates
from backend.tools.place_order import place_order
from backend.tools.cancel_order import cancel_order
from backend.tools.send_notification import send_notification
from backend.tools.send_trade_alert import send_trade_alert
from backend.tools.send_risk_alert import send_risk_alert
from backend.tools.send_daily_summary import send_daily_summary
from backend.tools.send_execution_update import send_execution_update
from backend.tools.get_order_book import get_order_book
from backend.tools.get_funding_rates import get_funding_rates
from backend.tools.get_liquidation_zones import get_liquidation_zones
from backend.tools.get_recent_trades import get_recent_trades
from backend.tools.get_execution_quality import get_execution_quality
from backend.tools.list_strategies import list_strategies
from backend.tools.evaluate_strategy import evaluate_strategy
from backend.tools.save_research_memo import save_research_memo
from backend.tools.get_research_memos import get_research_memos
from tools.registry import registry


def _wrap(fn):
    return lambda args, **_: json.dumps(fn(args), ensure_ascii=False)


_COMMON_ARRAY_SYMBOLS = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Asset symbols or tickers.",
}


_TRADING_TOOLS = {
    "get_crypto_prices": {
        "description": "Get normalized crypto spot price snapshots without exposing provider details or secrets.",
        "parameters": {"type": "object", "properties": {"symbols": _COMMON_ARRAY_SYMBOLS, "currency": {"type": "string"}}, "required": ["symbols"]},
        "handler": get_crypto_prices,
    },
    "get_market_overview": {
        "description": "Get a normalized market overview built from wrapped crypto market data providers.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "handler": get_market_overview,
    },
    "get_defi_protocols": {
        "description": "Get normalized DefiLlama protocol summaries for DeFi market intelligence.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "category": {"type": "string"},
                "chain": {"type": "string"},
                "search": {"type": "string"},
            },
            "required": [],
        },
        "handler": get_defi_protocols,
    },
    "get_defi_protocol_details": {
        "description": "Get normalized DefiLlama protocol details for a known protocol slug.",
        "parameters": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
        "handler": get_defi_protocol_details,
    },
    "get_defi_chain_overview": {
        "description": "Get normalized DefiLlama chain TVL rankings and chain metadata.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "search": {"type": "string"},
            },
            "required": [],
        },
        "handler": get_defi_chain_overview,
    },
    "get_defi_yields": {
        "description": "Get normalized DefiLlama yield-pool snapshots when the free api.llama.fi surface exposes them.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "chain": {"type": "string"},
                "project": {"type": "string"},
                "stablecoin": {"type": "boolean"},
                "min_tvl": {"type": "number", "minimum": 0},
                "min_apy": {"type": "number"},
            },
            "required": [],
        },
        "handler": get_defi_yields,
    },
    "get_defi_dex_overview": {
        "description": "Get normalized DEX activity overview from DefiLlama dimensions.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "chain": {"type": "string"},
            },
            "required": [],
        },
        "handler": get_defi_dex_overview,
    },
    "get_defi_fees_overview": {
        "description": "Get normalized fee and revenue overview from DefiLlama dimensions.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "chain": {"type": "string"},
            },
            "required": [],
        },
        "handler": get_defi_fees_overview,
    },
    "get_defi_open_interest": {
        "description": "Get open-interest overview from DefiLlama when available, or a documented derivatives proxy fallback on the free tier.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "chain": {"type": "string"},
            },
            "required": [],
        },
        "handler": get_defi_open_interest,
    },
    "get_defi_regime_summary": {
        "description": "Synthesize chain, DEX, fee, yield, and derivatives context into a normalized DeFi regime summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "chain_limit": {"type": "integer", "minimum": 1, "maximum": 20},
                "protocol_limit": {"type": "integer", "minimum": 1, "maximum": 20},
                "yield_limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": [],
        },
        "handler": get_defi_regime_summary,
    },
    "get_portfolio_valuation": {
        "description": "Estimate portfolio valuation using internal portfolio state plus wrapped market data.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "handler": get_portfolio_valuation,
    },
    "get_asset_rankings": {
        "description": "Rank supplied assets by wrapped market-cap context.",
        "parameters": {"type": "object", "properties": {"symbols": _COMMON_ARRAY_SYMBOLS}, "required": ["symbols"]},
        "handler": get_asset_rankings,
    },
    "get_ohlcv": {
        "description": "Get normalized OHLCV bars for a symbol and interval.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "interval": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["symbol"]},
        "handler": get_ohlcv,
    },
    "get_indicator_snapshot": {
        "description": "Get a compact indicator snapshot derived from normalized time-series data.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "interval": {"type": "string"}}, "required": ["symbol"]},
        "handler": get_indicator_snapshot,
    },
    "get_volatility_metrics": {
        "description": "Compute normalized realized-volatility metrics from internal OHLCV data.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "interval": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["symbol"]},
        "handler": get_volatility_metrics,
    },
    "get_correlation_inputs": {
        "description": "Return close-price series for downstream correlation and concentration analysis.",
        "parameters": {"type": "object", "properties": {"symbols": _COMMON_ARRAY_SYMBOLS, "interval": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["symbols"]},
        "handler": get_correlation_inputs,
    },
    "get_crypto_news": {
        "description": "Get normalized crypto-native news items.",
        "parameters": {"type": "object", "properties": {"assets": _COMMON_ARRAY_SYMBOLS, "limit": {"type": "integer"}}, "required": []},
        "handler": get_crypto_news,
    },
    "get_general_news": {
        "description": "Get normalized general or macro news items.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": []},
        "handler": get_general_news,
    },
    "get_macro_series": {
        "description": "Search FRED macro series or fetch exact metadata for a known series id.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "series_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": [],
        },
        "handler": get_macro_series,
    },
    "get_macro_observations": {
        "description": "Get normalized FRED observations for a macro series id.",
        "parameters": {
            "type": "object",
            "properties": {
                "series_id": {"type": "string"},
                "limit": {"type": "integer"},
                "sort_order": {"type": "string", "enum": ["asc", "desc"]},
                "observation_start": {"type": "string"},
                "observation_end": {"type": "string"},
            },
            "required": ["series_id"],
        },
        "handler": get_macro_observations,
    },
    "get_macro_regime_summary": {
        "description": "Synthesize a macro regime summary from normalized FRED series observations.",
        "parameters": {
            "type": "object",
            "properties": {
                "series_ids": _COMMON_ARRAY_SYMBOLS,
                "observation_limit": {"type": "integer"},
            },
            "required": [],
        },
        "handler": get_macro_regime_summary,
    },
    "get_event_risk_macro_context": {
        "description": "Provide macro regime context for event-risk reviews without exposing raw FRED access.",
        "parameters": {"type": "object", "properties": {"event": {"type": "string"}}, "required": []},
        "handler": get_event_risk_macro_context,
    },
    "get_event_risk_summary": {
        "description": "Synthesize a normalized event-risk summary from wrapped news tools.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": []},
        "handler": get_event_risk_summary,
    },
    "get_social_sentiment": {
        "description": "Get normalized social sentiment for a single asset.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        "handler": get_social_sentiment,
    },
    "get_social_spike_alerts": {
        "description": "Detect simple social-engagement spikes from wrapped sentiment data.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        "handler": get_social_spike_alerts,
    },
    "get_onchain_wallet_data": {
        "description": "Get normalized wallet activity and balances without exposing provider-specific APIs.",
        "parameters": {"type": "object", "properties": {"wallet": {"type": "string"}, "chain": {"type": "string"}}, "required": ["wallet"]},
        "handler": get_onchain_wallet_data,
    },
    "get_wallet_transactions": {
        "description": "Get normalized wallet transactions.",
        "parameters": {"type": "object", "properties": {"wallet": {"type": "string"}}, "required": ["wallet"]},
        "handler": get_wallet_transactions,
    },
    "get_token_activity": {
        "description": "Summarize token activity for a wallet from normalized onchain transaction data.",
        "parameters": {"type": "object", "properties": {"wallet": {"type": "string"}}, "required": ["wallet"]},
        "handler": get_token_activity,
    },
    "get_smart_money_flows": {
        "description": "Get normalized smart-money flow data for an asset.",
        "parameters": {"type": "object", "properties": {"asset": {"type": "string"}, "timeframe": {"type": "string"}}, "required": ["asset"]},
        "handler": get_smart_money_flows,
    },
    "get_labeled_wallet_activity": {
        "description": "Get smart-wallet labels and summarized activity.",
        "parameters": {"type": "object", "properties": {"asset": {"type": "string"}, "timeframe": {"type": "string"}}, "required": ["asset"]},
        "handler": get_labeled_wallet_activity,
    },
    "get_onchain_signal_summary": {
        "description": "Get a compact bullish/bearish bias summary from normalized onchain intelligence.",
        "parameters": {"type": "object", "properties": {"asset": {"type": "string"}, "timeframe": {"type": "string"}}, "required": ["asset"]},
        "handler": get_onchain_signal_summary,
    },
    "get_portfolio_state": {
        "description": "Get normalized portfolio state from the internal portfolio adapter.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_exchange_balances": {"type": "boolean"},
                "venue": {"type": "string"},
                "venues": {"type": "array", "items": {"type": "string"}},
            },
            "required": [],
        },
        "handler": get_portfolio_state,
    },
    "get_exchange_balances": {
        "description": "Get normalized exchange balances from one venue or reconcile balances across multiple configured execution venues.",
        "parameters": {
            "type": "object",
            "properties": {
                "venue": {"type": "string"},
                "venues": {"type": "array", "items": {"type": "string"}},
                "aggregate": {"type": "boolean"},
            },
            "required": [],
        },
        "handler": get_exchange_balances,
    },
    "get_open_orders": {
        "description": "Get normalized open exchange orders for a selected execution venue without exposing raw exchange credentials.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "venue": {"type": "string"},
            },
            "required": [],
        },
        "handler": get_open_orders,
    },
    "place_order": {
        "description": "Place a validated order through the backend-only execution adapter, with optional smart venue routing across configured exchanges.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "order_type": {"type": "string", "enum": ["market", "limit", "stop", "stop_limit"]},
                "amount": {"type": "number", "exclusiveMinimum": 0},
                "price": {"type": "number", "exclusiveMinimum": 0},
                "client_order_id": {"type": "string"},
                "time_in_force": {"type": "string", "enum": ["GTC", "IOC", "FOK"]},
                "post_only": {"type": "boolean"},
                "venue": {"type": "string"},
                "venues": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["symbol", "side", "amount"],
        },
        "handler": place_order,
    },
    "cancel_order": {
        "description": "Cancel a known exchange order id on a selected execution venue.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "symbol": {"type": "string"},
                "venue": {"type": "string"},
            },
            "required": ["order_id"],
        },
        "handler": cancel_order,
    },
    "get_order_history": {
        "description": "Get normalized historical orders from a selected backend execution venue.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "since": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "venue": {"type": "string"},
            },
            "required": [],
        },
        "handler": get_order_history,
    },
    "get_trade_history": {
        "description": "Get normalized historical trades from a selected backend execution venue.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "since": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "venue": {"type": "string"},
            },
            "required": [],
        },
        "handler": get_trade_history,
    },
    "list_trade_candidates": {
        "description": "List structured trade/watch candidates through internal strategy wrappers only.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "handler": list_trade_candidates,
    },
    "get_risk_approval": {
        "description": "Return a normalized pre-trade approval envelope from internal risk logic.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "proposed_size_usd": {"type": "number"}}, "required": ["symbol", "proposed_size_usd"]},
        "handler": get_risk_approval,
    },
    "send_notification": {
        "description": "Send a structured internal notification without exposing provider credentials.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
                "channels": {"type": "array", "items": {"type": "string"}},
                "title": {"type": "string"},
                "message": {"type": "string"},
                "severity": {"type": "string"},
                "notification_type": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["message"],
        },
        "handler": send_notification,
    },
    "send_trade_alert": {
        "description": "Send a normalized trade alert through backend-only Telegram and Slack integrations.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "message": {"type": "string"},
                "title": {"type": "string"},
                "side": {"type": "string", "enum": ["buy", "sell", "long", "short", "watch"]},
                "status": {"type": "string"},
                "channel": {"type": "string"},
                "channels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["symbol", "message"],
        },
        "handler": send_trade_alert,
    },
    "send_risk_alert": {
        "description": "Send a normalized risk alert through backend-only Telegram and Slack integrations.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "title": {"type": "string"},
                "severity": {"type": "string"},
                "symbol": {"type": "string"},
                "channel": {"type": "string"},
                "channels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["message"],
        },
        "handler": send_risk_alert,
    },
    "send_daily_summary": {
        "description": "Send a normalized market or portfolio summary through backend-only Telegram and Slack integrations.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "title": {"type": "string"},
                "summary_date": {"type": "string"},
                "channel": {"type": "string"},
                "channels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["message"],
        },
        "handler": send_daily_summary,
    },
    "send_execution_update": {
        "description": "Send a normalized order or execution status update through backend-only Telegram and Slack integrations.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "title": {"type": "string"},
                "order_id": {"type": "string"},
                "symbol": {"type": "string"},
                "status": {"type": "string"},
                "channel": {"type": "string"},
                "channels": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["message"],
        },
        "handler": send_execution_update,
    },
    "get_execution_status": {
        "description": "Get execution-provider workflow status or a normalized order status if an execution adapter is configured.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "symbol": {"type": "string"},
                "venue": {"type": "string"},
            },
            "required": [],
        },
        "handler": get_execution_status,
    },
    "get_recent_tradingview_alerts": {
        "description": "Read recent normalized TradingView webhook alerts from the shared backend ingestion store.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}, "processing_status": {"type": "string"}}, "required": []},
        "handler": get_recent_tradingview_alerts,
    },
    "get_tradingview_alert_by_symbol": {
        "description": "Read recent TradingView alerts for a symbol without exposing raw HTTP request data.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["symbol"]},
        "handler": get_tradingview_alert_by_symbol,
    },
    "get_pending_signal_events": {
        "description": "Read pending normalized TradingView signal-ready internal events for workflow routing.",
        "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}, "symbol": {"type": "string"}}, "required": []},
        "handler": get_pending_signal_events,
    },
    "get_tradingview_alert_context": {
        "description": "Read TradingView alert context, related alerts, and related internal events for a symbol or alert id.",
        "parameters": {"type": "object", "properties": {"alert_id": {"type": "string"}, "symbol": {"type": "string"}, "limit": {"type": "integer"}}, "required": []},
        "handler": get_tradingview_alert_context,
    },
    "get_order_book": {
        "description": "Fetch the current order book (bids/asks) for a futures symbol from BitMart. Returns best bid/ask, spread, and depth snapshot.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Futures symbol, e.g. 'BTCUSDT'."},
                "limit": {"type": "integer", "minimum": 5, "maximum": 50},
            },
            "required": ["symbol"],
        },
        "handler": get_order_book,
    },
    "get_funding_rates": {
        "description": "Fetch current funding rates for one or more perpetual futures symbols from BitMart.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "Futures symbols, e.g. ['BTCUSDT', 'ETHUSDT']."},
            },
            "required": [],
        },
        "handler": get_funding_rates,
    },
    "get_liquidation_zones": {
        "description": "Fetch estimated liquidation heat-map zones for a futures symbol from Coinglass.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol without USDT suffix, e.g. 'BTC'."},
                "exchange": {"type": "string"},
            },
            "required": ["symbol"],
        },
        "handler": get_liquidation_zones,
    },
    "get_recent_trades": {
        "description": "Fetch recent public trades (tape / time-and-sales) for a futures symbol. Useful for measuring buying vs selling pressure.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Futures symbol, e.g. 'BTCUSDT'."},
                "limit": {"type": "integer", "minimum": 5, "maximum": 100},
            },
            "required": ["symbol"],
        },
        "handler": get_recent_trades,
    },
    "get_execution_quality": {
        "description": "Analyse fill quality for recent personal trades vs the current mid-price. Reports avg fill price, VWAP, slippage in basis points.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol, e.g. 'BTC/USDT' or 'BTCUSDT'."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["symbol"],
        },
        "handler": get_execution_quality,
    },
    "list_strategies": {
        "description": "List all named trading strategies in the strategy registry with their descriptions, target timeframes, and current versions.",
        "parameters": {"type": "object", "properties": {}, "required": []},
        "handler": list_strategies,
    },
    "evaluate_strategy": {
        "description": "Run a named strategy scorer against a symbol using live market data and return a scored trade candidate with confidence and rationale.",
        "parameters": {
            "type": "object",
            "properties": {
                "strategy_name": {"type": "string", "description": "One of: 'momentum', 'mean_reversion', 'breakout'."},
                "symbol": {"type": "string", "description": "Symbol, e.g. 'BTCUSDT'."},
                "timeframe": {"type": "string", "description": "Chart timeframe, e.g. '1h', '4h', '1d'."},
            },
            "required": ["strategy_name", "symbol"],
        },
        "handler": evaluate_strategy,
    },
    "save_research_memo": {
        "description": "Persist a structured research note to the durable research memory store. Supports symbol-scoping, strategy references, and tag-based retrieval.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The memo body text."},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Searchable tags, e.g. ['bearish', 'btc', 'funding-rate']."},
                "symbol": {"type": "string"},
                "source_agent": {"type": "string"},
                "strategy_ref": {"type": "string"},
                "supersedes": {"type": "string", "description": "ID of an older memo this supersedes."},
            },
            "required": ["content", "tags"],
        },
        "handler": save_research_memo,
    },
    "get_research_memos": {
        "description": "Retrieve durable research memos from the memory store. Filter by symbol, tags (OR-matched), strategy reference, or lookback window.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Return memos matching ANY of these tags."},
                "strategy_ref": {"type": "string"},
                "include_superseded": {"type": "boolean"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "since_hours": {"type": "number"},
            },
            "required": [],
        },
        "handler": get_research_memos,
    },
}


def _check_trading_requirements() -> bool:
    return True


for tool_name, spec in _TRADING_TOOLS.items():
    registry.register(
        name=tool_name,
        toolset="trading",
        schema={"name": tool_name, "description": spec["description"], "parameters": spec["parameters"]},
        handler=_wrap(spec["handler"]),
        check_fn=_check_trading_requirements,
        emoji="📈",
    )
