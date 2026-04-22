"""Validation utility for the Hermes Redis Streams event bus."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from redis.exceptions import RedisError

from .consumer import RedisStreamWorker
from .models import TradingEvent
from .publisher import TradingEventPublisher
from .runtime import bootstrap_event_bus_on_startup, inspect_pending, inspect_stream, list_consumer_groups
from .schema import DEFAULT_TRADING_STREAM

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def cmd_bootstrap(_: argparse.Namespace) -> int:
    bootstrap_event_bus_on_startup()
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    bootstrap_event_bus_on_startup()
    payload = json.loads(args.payload) if args.payload else {}
    event = TradingEvent(
        event_type=args.event_type,
        source=args.source,
        producer="backend.event_bus.validate",
        symbol=args.symbol,
        correlation_id=args.correlation_id,
        payload=payload,
    )
    envelope = TradingEventPublisher(stream=args.stream).publish(event)
    print(json.dumps({"redis_id": envelope.redis_id, "event_id": event.event_id, "stream": args.stream}))
    return 0


def cmd_groups(args: argparse.Namespace) -> int:
    bootstrap_event_bus_on_startup(stream=args.stream)
    print(json.dumps(list_consumer_groups(stream=args.stream), indent=2, default=str))
    return 0


def cmd_stream(args: argparse.Namespace) -> int:
    bootstrap_event_bus_on_startup(stream=args.stream)
    print(json.dumps(inspect_stream(stream=args.stream), indent=2, default=str))
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    bootstrap_event_bus_on_startup(stream=args.stream)
    print(json.dumps(inspect_pending(args.group, stream=args.stream), indent=2, default=str))
    return 0


def cmd_consume_once(args: argparse.Namespace) -> int:
    bootstrap_event_bus_on_startup(stream=args.stream)
    worker = RedisStreamWorker(
        group_name=args.group,
        consumer_name=args.consumer,
        stream=args.stream,
        block_ms=args.block_ms,
        count=1,
    )

    def handler(envelope: Any) -> bool:
        logger.info(
            "Validation worker received event_type=%s redis_id=%s group=%s mode=%s",
            envelope.event.event_type,
            envelope.redis_id,
            args.group,
            args.mode,
        )
        if args.mode == "fail":
            raise RuntimeError("intentional validation failure")
        return True

    processed = worker.poll_once(handler)
    print(json.dumps({"processed": processed, "group": args.group, "consumer": args.consumer, "mode": args.mode}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Hermes Redis Streams runtime wiring")
    subparsers = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Ping Redis and bootstrap consumer groups")
    bootstrap_parser.set_defaults(func=cmd_bootstrap)

    publish_parser = subparsers.add_parser("publish", help="Publish a test event into the trading stream")
    publish_parser.add_argument("--stream", default=DEFAULT_TRADING_STREAM)
    publish_parser.add_argument("--event-type", default="notification_requested")
    publish_parser.add_argument("--source", default="event-bus-validate")
    publish_parser.add_argument("--symbol", default=None)
    publish_parser.add_argument("--correlation-id", default=None)
    publish_parser.add_argument("--payload", default='{"message":"redis validation event"}')
    publish_parser.set_defaults(func=cmd_publish)

    groups_parser = subparsers.add_parser("groups", help="List consumer groups for the trading stream")
    groups_parser.add_argument("--stream", default=DEFAULT_TRADING_STREAM)
    groups_parser.set_defaults(func=cmd_groups)

    stream_parser = subparsers.add_parser("stream", help="Inspect the trading stream")
    stream_parser.add_argument("--stream", default=DEFAULT_TRADING_STREAM)
    stream_parser.set_defaults(func=cmd_stream)

    pending_parser = subparsers.add_parser("pending", help="Inspect pending messages for a consumer group")
    pending_parser.add_argument("group")
    pending_parser.add_argument("--stream", default=DEFAULT_TRADING_STREAM)
    pending_parser.set_defaults(func=cmd_pending)

    consume_parser = subparsers.add_parser("consume-once", help="Run a single worker poll and optionally fail")
    consume_parser.add_argument("group")
    consume_parser.add_argument("--stream", default=DEFAULT_TRADING_STREAM)
    consume_parser.add_argument("--consumer", default="validation-worker")
    consume_parser.add_argument("--mode", choices=("success", "fail"), default="success")
    consume_parser.add_argument("--block-ms", type=int, default=1000)
    consume_parser.set_defaults(func=cmd_consume_once)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except RedisError:
        logger.exception("Redis validation command failed")
        return 1
    except Exception:
        logger.exception("Validation command failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
