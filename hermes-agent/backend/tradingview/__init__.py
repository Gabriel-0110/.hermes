"""Shared TradingView webhook ingestion primitives."""

from .store import TradingViewStore

try:  # Optional at import time for lighter consumers that only need storage primitives.
    from .service import TradingViewIngestionService
except ModuleNotFoundError:  # pragma: no cover - depends on optional runtime deps like redis
    TradingViewIngestionService = None  # type: ignore[assignment]

__all__ = [
    "TradingViewIngestionService",
    "TradingViewStore",
]
