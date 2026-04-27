from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from backend.models import EventRiskSummary
from backend.tools._helpers import envelope, run_tool
from backend.tools.get_crypto_news import get_crypto_news
from backend.tools.get_general_news import get_general_news


_HIGH_IMPACT_EVENT_KEYWORDS = {
    "cpi": "CPI",
    "fomc": "FOMC",
    "fed": "Fed",
    "rate decision": "Rate decision",
    "nfp": "NFP",
    "payroll": "Payrolls",
    "pce": "PCE",
    "ecb": "ECB",
    "boj": "BoJ",
    "inflation": "Inflation",
}
_IMMEDIATE_HINTS = ("today", "this hour", "minutes", "minute", "later today", "shortly")


class GetEventRiskSummaryInput(BaseModel):
    query: str = Field(default="crypto macro")
    event_time_iso: str | None = None
    window_minutes: int = Field(default=60, ge=1, le=1440)


def _parse_event_time(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _matched_keywords(headlines: list[str]) -> list[str]:
    lowered = "\n".join(headlines).lower()
    return [label for needle, label in _HIGH_IMPACT_EVENT_KEYWORDS.items() if needle in lowered]


def _headline_implies_immediacy(headlines: list[str]) -> bool:
    lowered = "\n".join(headlines).lower()
    return any(token in lowered for token in _IMMEDIATE_HINTS)


def get_event_risk_summary(payload: dict | None = None) -> dict:
    def _run() -> dict:
        args = GetEventRiskSummaryInput.model_validate(payload or {})
        crypto_news = get_crypto_news({"query": args.query})
        general_news = get_general_news({"query": args.query, "limit": 5})
        crypto_data = crypto_news.get("data", []) if isinstance(crypto_news.get("data"), list) else []
        general_data = general_news.get("data", []) if isinstance(general_news.get("data"), list) else []
        headlines = [row["title"] for row in crypto_data[:3] if isinstance(row, dict) and "title" in row] + [row["title"] for row in general_data[:3] if isinstance(row, dict) and "title" in row]
        matched_keywords = _matched_keywords(headlines)
        event_time = _parse_event_time(args.event_time_iso)
        minutes_to_event = None
        blackout_active = False
        blackout_reason = None
        if event_time is not None:
            minutes_to_event = round((event_time - datetime.now(UTC)).total_seconds() / 60.0, 2)
            blackout_active = abs(minutes_to_event) <= args.window_minutes and bool(matched_keywords)
            if blackout_active:
                blackout_reason = (
                    f"High-impact event window active ({minutes_to_event:+.0f} minutes to event, "
                    f"window={args.window_minutes}m)."
                )
        elif matched_keywords and _headline_implies_immediacy(headlines):
            blackout_active = True
            blackout_reason = (
                f"High-impact headlines imply an active event window: {', '.join(matched_keywords)}."
            )

        severity = "high" if matched_keywords else ("medium" if headlines else "low")
        summary = EventRiskSummary(
            headline_risk="elevated" if len(headlines) >= 3 or matched_keywords else "contained",
            severity=severity,
            summary="Synthesized event risk summary from wrapped crypto and general news tools.",
            catalysts=headlines[:5],
            watch_items=headlines[5:8],
            matched_keywords=matched_keywords,
            blackout_active=blackout_active,
            blackout_reason=blackout_reason,
            blackout_window_minutes=args.window_minutes,
            minutes_to_event=minutes_to_event,
            event_time=event_time.isoformat() if event_time is not None else None,
        )
        crypto_providers = crypto_news.get("meta", {}).get("providers", [])
        general_providers = general_news.get("meta", {}).get("providers", [])
        providers = (crypto_providers if isinstance(crypto_providers, list) else []) + (general_providers if isinstance(general_providers, list) else [])
        return envelope("get_event_risk_summary", providers, summary.model_dump(mode="json"))

    return run_tool("get_event_risk_summary", _run)

