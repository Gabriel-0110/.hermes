from __future__ import annotations

from backend.models import EventRiskSummary
from backend.tools._helpers import envelope, run_tool
from backend.tools.get_crypto_news import get_crypto_news
from backend.tools.get_general_news import get_general_news


def get_event_risk_summary(payload: dict | None = None) -> dict:
    def _run() -> dict:
        crypto_news = get_crypto_news(payload or {})
        general_news = get_general_news({"query": (payload or {}).get("query", "crypto macro"), "limit": 5})
        headlines = [row["title"] for row in crypto_news["data"][:3]] + [row["title"] for row in general_news["data"][:3]]
        summary = EventRiskSummary(
            headline_risk="elevated" if len(headlines) >= 3 else "contained",
            severity="medium" if headlines else "low",
            summary="Synthesized event risk summary from wrapped crypto and general news tools.",
            catalysts=headlines[:5],
            watch_items=headlines[5:8],
        )
        providers = crypto_news["meta"]["providers"] + general_news["meta"]["providers"]
        return envelope("get_event_risk_summary", providers, summary.model_dump(mode="json"))

    return run_tool("get_event_risk_summary", _run)

