"""Shared TradingView storage facade.

TimescaleDB/PostgreSQL is the primary source of truth when `DATABASE_URL` is
configured. The old SQLite `state.db` storage remains only as a fallback for
local or legacy environments that have not been migrated yet.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, get_database_backend, session_scope
from backend.db.session import get_database_url, get_engine, get_sqlite_fallback_url

from .models import (
    TradingViewAlertRecord,
    TradingViewIngestionResult,
    TradingViewInternalEvent,
)

_SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tradingview_alert_events (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    source TEXT NOT NULL,
    symbol TEXT,
    timeframe TEXT,
    alert_name TEXT,
    signal TEXT,
    direction TEXT,
    strategy TEXT,
    price REAL,
    payload TEXT NOT NULL,
    processing_status TEXT NOT NULL,
    processing_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_tv_alert_events_ts
    ON tradingview_alert_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_tv_alert_events_symbol
    ON tradingview_alert_events(symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_tv_alert_events_status
    ON tradingview_alert_events(processing_status, ts DESC);

CREATE TABLE IF NOT EXISTS tradingview_internal_events (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    event_type TEXT NOT NULL,
    alert_event_id TEXT NOT NULL REFERENCES tradingview_alert_events(id),
    symbol TEXT,
    payload TEXT NOT NULL,
    delivery_status TEXT NOT NULL DEFAULT 'pending',
    delivery_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_tv_internal_events_ts
    ON tradingview_internal_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_tv_internal_events_type_status
    ON tradingview_internal_events(event_type, delivery_status, ts DESC);
CREATE INDEX IF NOT EXISTS idx_tv_internal_events_symbol
    ON tradingview_internal_events(symbol, ts DESC);
"""


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _ts_to_datetime(ts: float | None) -> datetime:
    return datetime.fromtimestamp(ts if ts is not None else time.time(), tz=UTC)


def _datetime_to_ts(value: datetime) -> float:
    return value.timestamp()


class TradingViewStore:
    """Shared storage for TradingView alert ingestion and agent reads."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (get_hermes_home() / "state.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path is not None:
            self.database_url = get_sqlite_fallback_url(self.db_path)
        else:
            self.database_url = get_database_url() or get_sqlite_fallback_url(self.db_path)
        self.backend = get_database_backend(self.database_url)
        ensure_time_series_schema(get_engine(database_url=self.database_url))

    def _connect_sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=1.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def ensure_schema(self) -> None:
        ensure_time_series_schema(get_engine(database_url=self.database_url))

    def insert_alert(
        self,
        *,
        source: str,
        symbol: str | None,
        timeframe: str | None,
        alert_name: str | None,
        signal: str | None,
        direction: str | None,
        strategy: str | None,
        price: float | None,
        payload: dict[str, Any],
        processing_status: str,
        processing_error: str | None,
        ts: float | None = None,
        alert_id: str | None = None,
    ) -> TradingViewAlertRecord:
        self.ensure_schema()
        with session_scope(database_url=self.database_url) as session:
            row = HermesTimeSeriesRepository(session).insert_tradingview_alert(
                source=source,
                symbol=symbol.upper() if symbol else None,
                timeframe=timeframe,
                alert_name=alert_name,
                signal=signal,
                direction=direction,
                strategy=strategy,
                price=price,
                payload=payload,
                processing_status=processing_status,
                processing_error=processing_error,
                alert_id=alert_id,
                event_time=_ts_to_datetime(ts),
            )
            return self._alert_from_row(row)

    def publish_event(
        self,
        *,
        event_type: str,
        alert_event_id: str,
        symbol: str | None,
        payload: dict[str, Any],
        delivery_status: str = "pending",
        delivery_error: str | None = None,
        ts: float | None = None,
        event_id: str | None = None,
    ) -> TradingViewInternalEvent:
        self.ensure_schema()
        with session_scope(database_url=self.database_url) as session:
            row = HermesTimeSeriesRepository(session).insert_internal_event(
                event_type=event_type,
                alert_event_id=alert_event_id,
                symbol=symbol.upper() if symbol else None,
                payload=payload,
                delivery_status=delivery_status,
                delivery_error=delivery_error,
                event_id=event_id,
                event_time=_ts_to_datetime(ts),
            )
            return self._internal_event_from_row(row)

    def list_alerts(
        self,
        *,
        limit: int = 20,
        symbol: str | None = None,
        processing_status: str | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        with session_scope(database_url=self.database_url) as session:
            rows = HermesTimeSeriesRepository(session).list_tradingview_alerts(
                limit=limit,
                symbol=symbol.upper() if symbol else None,
                processing_status=processing_status,
            )
            return [self._alert_dict_from_row(row) for row in rows]

    def list_internal_events(
        self,
        *,
        limit: int = 20,
        event_type: str | None = None,
        delivery_status: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        with session_scope(database_url=self.database_url) as session:
            rows = HermesTimeSeriesRepository(session).list_internal_events(
                limit=limit,
                event_type=event_type,
                delivery_status=delivery_status,
                symbol=symbol.upper() if symbol else None,
            )
            return [self._internal_event_dict_from_row(row) for row in rows]

    def get_alert_context(
        self,
        *,
        alert_id: str | None = None,
        symbol: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        self.ensure_schema()

        if alert_id:
            with session_scope(database_url=self.database_url) as session:
                repo = HermesTimeSeriesRepository(session)
                alert = repo.get_tradingview_alert_by_id(alert_id)
                if alert is None:
                    return {"alert": None, "related_alerts": [], "related_events": []}
                target_symbol = alert.symbol
                related_alerts = repo.list_tradingview_alerts(limit=limit, symbol=target_symbol) if target_symbol else []
                related_events = repo.list_internal_events(limit=limit, symbol=target_symbol) if target_symbol else []
                return {
                    "alert": self._alert_dict_from_row(alert),
                    "related_alerts": [self._alert_dict_from_row(row) for row in related_alerts],
                    "related_events": [self._internal_event_dict_from_row(row) for row in related_events],
                }

        if symbol:
            normalized_symbol = symbol.upper()
            with session_scope(database_url=self.database_url) as session:
                repo = HermesTimeSeriesRepository(session)
                related_alerts = repo.list_tradingview_alerts(limit=limit, symbol=normalized_symbol)
                related_events = repo.list_internal_events(limit=limit, symbol=normalized_symbol)
                return {
                    "alert": self._alert_dict_from_row(related_alerts[0]) if related_alerts else None,
                    "related_alerts": [self._alert_dict_from_row(row) for row in related_alerts],
                    "related_events": [self._internal_event_dict_from_row(row) for row in related_events],
                }

        return {"alert": None, "related_alerts": [], "related_events": []}

    def record_ingestion_result(self, result: TradingViewIngestionResult) -> TradingViewIngestionResult:
        return result

    def _insert_alert_sqlite(
        self,
        *,
        source: str,
        symbol: str | None,
        timeframe: str | None,
        alert_name: str | None,
        signal: str | None,
        direction: str | None,
        strategy: str | None,
        price: float | None,
        payload: dict[str, Any],
        processing_status: str,
        processing_error: str | None,
        ts: float | None = None,
        alert_id: str | None = None,
    ) -> TradingViewAlertRecord:
        ts = ts if ts is not None else time.time()
        alert_id = alert_id or f"tv_alert_{uuid.uuid4().hex}"
        with self._connect_sqlite() as conn:
            conn.execute(
                """
                INSERT INTO tradingview_alert_events (
                    id, ts, source, symbol, timeframe, alert_name, signal,
                    direction, strategy, price, payload, processing_status,
                    processing_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert_id,
                    ts,
                    source,
                    symbol.upper() if symbol else None,
                    timeframe,
                    alert_name,
                    signal,
                    direction,
                    strategy,
                    price,
                    _json_dumps(payload),
                    processing_status,
                    processing_error,
                ),
            )
        return TradingViewAlertRecord(
            id=alert_id,
            ts=ts,
            source=source,
            symbol=symbol.upper() if symbol else None,
            timeframe=timeframe,
            alert_name=alert_name,
            signal=signal,
            direction=direction,
            strategy=strategy,
            price=price,
            payload=payload,
            processing_status=processing_status,
            processing_error=processing_error,
        )

    def _publish_event_sqlite(
        self,
        *,
        event_type: str,
        alert_event_id: str,
        symbol: str | None,
        payload: dict[str, Any],
        delivery_status: str = "pending",
        delivery_error: str | None = None,
        ts: float | None = None,
        event_id: str | None = None,
    ) -> TradingViewInternalEvent:
        ts = ts if ts is not None else time.time()
        event_id = event_id or f"tv_evt_{uuid.uuid4().hex}"
        with self._connect_sqlite() as conn:
            conn.execute(
                """
                INSERT INTO tradingview_internal_events (
                    id, ts, event_type, alert_event_id, symbol, payload,
                    delivery_status, delivery_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    ts,
                    event_type,
                    alert_event_id,
                    symbol.upper() if symbol else None,
                    _json_dumps(payload),
                    delivery_status,
                    delivery_error,
                ),
            )
        return TradingViewInternalEvent(
            id=event_id,
            ts=ts,
            event_type=event_type,
            alert_event_id=alert_event_id,
            symbol=symbol.upper() if symbol else None,
            payload=payload,
            delivery_status=delivery_status,
            delivery_error=delivery_error,
        )

    def _list_alerts_sqlite(
        self,
        *,
        limit: int = 20,
        symbol: str | None = None,
        processing_status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol.upper())
        if processing_status:
            clauses.append("processing_status = ?")
            params.append(processing_status)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 200)))
        with self._connect_sqlite() as conn:
            rows = conn.execute(
                f"""
                SELECT id, ts, source, symbol, timeframe, alert_name, signal,
                       direction, strategy, price, payload, processing_status,
                       processing_error
                FROM tradingview_alert_events
                {where_sql}
                ORDER BY ts DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_alert_sqlite(row) for row in rows]

    def _list_internal_events_sqlite(
        self,
        *,
        limit: int = 20,
        event_type: str | None = None,
        delivery_status: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if delivery_status:
            clauses.append("delivery_status = ?")
            params.append(delivery_status)
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol.upper())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 200)))
        with self._connect_sqlite() as conn:
            rows = conn.execute(
                f"""
                SELECT id, ts, event_type, alert_event_id, symbol, payload,
                       delivery_status, delivery_error
                FROM tradingview_internal_events
                {where_sql}
                ORDER BY ts DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._row_to_internal_event_sqlite(row) for row in rows]

    def _get_alert_context_sqlite(
        self,
        *,
        alert_id: str | None = None,
        symbol: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        if alert_id:
            alerts = self._get_alerts_by_id_sqlite([alert_id])
            if not alerts:
                return {"alert": None, "related_alerts": [], "related_events": []}
            alert = alerts[0]
            target_symbol = alert.get("symbol")
            related_alerts = self._list_alerts_sqlite(limit=limit, symbol=target_symbol) if target_symbol else []
            related_events = self._list_internal_events_sqlite(limit=limit, symbol=target_symbol) if target_symbol else []
            return {"alert": alert, "related_alerts": related_alerts, "related_events": related_events}

        if symbol:
            normalized_symbol = symbol.upper()
            related_alerts = self._list_alerts_sqlite(limit=limit, symbol=normalized_symbol)
            related_events = self._list_internal_events_sqlite(limit=limit, symbol=normalized_symbol)
            return {"alert": related_alerts[0] if related_alerts else None, "related_alerts": related_alerts, "related_events": related_events}

        return {"alert": None, "related_alerts": [], "related_events": []}

    def _get_alerts_by_id_sqlite(self, alert_ids: list[str]) -> list[dict[str, Any]]:
        if not alert_ids:
            return []
        placeholders = ", ".join("?" for _ in alert_ids)
        with self._connect_sqlite() as conn:
            rows = conn.execute(
                f"""
                SELECT id, ts, source, symbol, timeframe, alert_name, signal,
                       direction, strategy, price, payload, processing_status,
                       processing_error
                FROM tradingview_alert_events
                WHERE id IN ({placeholders})
                ORDER BY ts DESC
                """,
                alert_ids,
            ).fetchall()
        return [self._row_to_alert_sqlite(row) for row in rows]

    @staticmethod
    def _row_to_alert_sqlite(row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload"]) if row["payload"] else {}
        return {
            "id": row["id"],
            "ts": row["ts"],
            "source": row["source"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "alert_name": row["alert_name"],
            "signal": row["signal"],
            "direction": row["direction"],
            "strategy": row["strategy"],
            "price": row["price"],
            "payload": payload,
            "processing_status": row["processing_status"],
            "processing_error": row["processing_error"],
        }

    @staticmethod
    def _row_to_internal_event_sqlite(row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload"]) if row["payload"] else {}
        return {
            "id": row["id"],
            "ts": row["ts"],
            "event_type": row["event_type"],
            "alert_event_id": row["alert_event_id"],
            "symbol": row["symbol"],
            "payload": payload,
            "delivery_status": row["delivery_status"],
            "delivery_error": row["delivery_error"],
        }

    @staticmethod
    def _alert_from_row(row: Any) -> TradingViewAlertRecord:
        return TradingViewAlertRecord(
            id=row.id,
            ts=_datetime_to_ts(row.event_time),
            source=row.source,
            symbol=row.symbol,
            timeframe=row.timeframe,
            alert_name=row.alert_name,
            signal=row.signal,
            direction=row.direction,
            strategy=row.strategy,
            price=row.price,
            payload=row.payload or {},
            processing_status=row.processing_status,
            processing_error=row.processing_error,
        )

    @staticmethod
    def _internal_event_from_row(row: Any) -> TradingViewInternalEvent:
        return TradingViewInternalEvent(
            id=row.id,
            ts=_datetime_to_ts(row.event_time),
            event_type=row.event_type,
            alert_event_id=row.alert_event_id,
            symbol=row.symbol,
            payload=row.payload or {},
            delivery_status=row.delivery_status,
            delivery_error=row.delivery_error,
        )

    @classmethod
    def _alert_dict_from_row(cls, row: Any) -> dict[str, Any]:
        return cls._alert_from_row(row).model_dump(mode="python")

    @classmethod
    def _internal_event_dict_from_row(cls, row: Any) -> dict[str, Any]:
        return cls._internal_event_from_row(row).model_dump(mode="python")
