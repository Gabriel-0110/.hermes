"""Redis Streams event bus primitives for Hermes trading workflows."""

from .bootstrap import DEFAULT_CONSUMER_GROUPS, bootstrap_consumer_groups, ensure_consumer_group
from .consumer import RedisStreamWorker
from .models import TradingEvent, TradingEventEnvelope, TradingEventType
from .publisher import TradingEventPublisher
from .runtime import bootstrap_event_bus_on_startup, inspect_pending, inspect_stream, list_consumer_groups
from .schema import DEFAULT_TRADING_STREAM, normalize_event_payload

__all__ = [
    "DEFAULT_CONSUMER_GROUPS",
    "DEFAULT_TRADING_STREAM",
    "RedisStreamWorker",
    "TradingEvent",
    "TradingEventEnvelope",
    "TradingEventPublisher",
    "TradingEventType",
    "bootstrap_event_bus_on_startup",
    "bootstrap_consumer_groups",
    "ensure_consumer_group",
    "inspect_pending",
    "inspect_stream",
    "list_consumer_groups",
    "normalize_event_payload",
]
