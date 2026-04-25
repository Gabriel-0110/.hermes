"""Portfolio-level drawdown guard and kill-switch enforcement."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import PortfolioSnapshotRow
from backend.db.session import get_engine
from backend.redis_client import get_redis_client
from backend.tools.send_notification import send_notification
from backend.tools.set_kill_switch import set_kill_switch

logger = logging.getLogger(__name__)

_EQUITY_PEAK_KEY = "hermes:risk:equity_peak"


@dataclass(slots=True)
class DrawdownGuardSummary:
    account_id: str
    current_equity_usd: float | None
    peak_equity_usd: float | None
    drawdown_pct: float | None
    trigger_pct: float
    breached: bool
    kill_switch_set: bool = False
    notification_delivered: bool = False
    detail: str | None = None

    def to_markdown(self) -> str:
        lines = [
            "# Drawdown guard",
            "",
            f"- Account: `{self.account_id}`",
            f"- Current equity: {self.current_equity_usd if self.current_equity_usd is not None else 'n/a'}",
            f"- 30d high-water mark: {self.peak_equity_usd if self.peak_equity_usd is not None else 'n/a'}",
            f"- Drawdown: {self.drawdown_pct if self.drawdown_pct is not None else 'n/a'}%",
            f"- Trigger: {self.trigger_pct}%",
            f"- Breached: {'yes' if self.breached else 'no'}",
            f"- Kill switch set: {'yes' if self.kill_switch_set else 'no'}",
            f"- Notification delivered: {'yes' if self.notification_delivered else 'no'}",
        ]
        if self.detail:
            lines.extend(["", self.detail])
        return "\n".join(lines)


def run_drawdown_guard(
    *,
    account_id: str | None = None,
    lookback_days: int = 30,
    trigger_pct: float | None = None,
) -> DrawdownGuardSummary:
    account = account_id or os.getenv("TRADING_PORTFOLIO_ACCOUNT_ID") or "paper"
    threshold = float(trigger_pct or _configured_drawdown_limit(default=8.0))
    cutoff = datetime.now(UTC) - timedelta(days=max(1, lookback_days))

    ensure_time_series_schema(get_engine())
    with session_scope() as session:
        rows = list(
            session.scalars(
                select(PortfolioSnapshotRow)
                .where(PortfolioSnapshotRow.account_id == account)
                .where(PortfolioSnapshotRow.snapshot_time >= cutoff)
                .where(PortfolioSnapshotRow.total_equity_usd.is_not(None))
                .order_by(desc(PortfolioSnapshotRow.snapshot_time))
            )
        )

    if not rows:
        return DrawdownGuardSummary(
            account_id=account,
            current_equity_usd=None,
            peak_equity_usd=None,
            drawdown_pct=None,
            trigger_pct=threshold,
            breached=False,
            detail="No portfolio snapshots are available for drawdown evaluation.",
        )

    current_equity = float(rows[0].total_equity_usd or 0.0)
    peak_equity = max(float(row.total_equity_usd or 0.0) for row in rows)
    drawdown_pct = round(((peak_equity - current_equity) / peak_equity) * 100.0, 2) if peak_equity > 0 else None

    _persist_peak_equity(peak_equity)

    breached = bool(drawdown_pct is not None and drawdown_pct > threshold)
    summary = DrawdownGuardSummary(
        account_id=account,
        current_equity_usd=round(current_equity, 2),
        peak_equity_usd=round(peak_equity, 2),
        drawdown_pct=drawdown_pct,
        trigger_pct=threshold,
        breached=breached,
    )
    if not breached:
        summary.detail = "Portfolio drawdown is within the allowed threshold."
        return summary

    reason = (
        f"Drawdown guard tripped: {drawdown_pct:.2f}% > {threshold:.2f}% "
        f"(peak={peak_equity:.2f} current={current_equity:.2f})"
    )
    logger.warning(reason)

    try:
        set_kill_switch({"active": True, "reason": reason})
        summary.kill_switch_set = True
    except Exception as exc:
        logger.error("drawdown_guard: failed to set kill switch: %s", exc)
        summary.detail = f"{reason}. Failed to set kill switch: {exc}"
        return summary

    try:
        notification = send_notification(
            {
                "channel": "telegram",
                "title": "Hermes critical drawdown guard",
                "message": reason,
                "severity": "critical",
                "notification_type": "drawdown_guard",
                "metadata": {
                    "account_id": account,
                    "current_equity_usd": round(current_equity, 2),
                    "peak_equity_usd": round(peak_equity, 2),
                    "drawdown_pct": drawdown_pct,
                    "trigger_pct": threshold,
                },
            }
        )
        summary.notification_delivered = bool(notification.get("data", {}).get("delivered"))
    except Exception as exc:
        logger.warning("drawdown_guard: failed to send critical telegram alert: %s", exc)

    summary.detail = reason
    return summary


def _configured_drawdown_limit(*, default: float) -> float:
    try:
        from backend.tools.get_risk_state import get_risk_state

        response = get_risk_state({})
        data = response.get("data") if isinstance(response, dict) else {}
        if isinstance(data, dict) and data.get("drawdown_limit_pct") is not None:
            return float(data["drawdown_limit_pct"])
    except Exception as exc:
        logger.debug("drawdown_guard: get_risk_state failed: %s", exc)
    return default


def _persist_peak_equity(peak_equity: float) -> None:
    try:
        redis = get_redis_client()
        redis.set(
            _EQUITY_PEAK_KEY,
            json.dumps({"equity": round(peak_equity, 2), "updated_at": datetime.now(UTC).isoformat()}),
        )
    except Exception as exc:
        logger.debug("drawdown_guard: failed to persist peak equity in redis: %s", exc)


def main() -> int:
    summary = run_drawdown_guard()
    print(summary.to_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())