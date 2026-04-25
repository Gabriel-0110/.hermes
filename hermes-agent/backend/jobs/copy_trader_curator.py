"""Daily BitMart AIHub copy-trader curation and operator recommendation job.

The curator consumes leaderboard snapshots from the existing research-memo store
so the market-researcher can publish AIHub leaderboard observations without
introducing another fragile scraper into the trading path.

Accepted research memo payload shapes:

1. Raw JSON list of leaderboard rows
2. JSON object containing one of: ``leaderboard``, ``rows``, ``traders``,
   ``masters``, ``results``, ``data``
3. Either of the above embedded in a fenced ```json block

Each row should expose enough information to derive:

- trader identifier/name
- 30-day Sharpe
- 30-day max drawdown
- follower fee percentage
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from typing import Any, Iterable, Sequence

from sqlalchemy import desc, select

from backend.copy_trader_proposals import (
    create_or_get_pending_copy_trader_switch_proposal,
    mark_copy_trader_switch_proposal_notified,
)
from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import CopyTraderScoreRow, ResearchMemoRow
from backend.db.session import get_engine
from backend.integrations.notifications.telegram_client import TelegramNotificationClient
from hermes_constants import get_config_path

logger = logging.getLogger(__name__)

LEADERBOARD_MEMO_TAGS = (
    "bitmart_aihub",
    "copy_trader",
    "copy_trader_curator",
    "copy_trader_leaderboard",
)
DEFAULT_LOOKBACK_HOURS = 72
DEFAULT_THRESHOLD_PERCENTILE = 0.60
DEFAULT_THRESHOLD_DAYS = 7
SCORING_WEIGHTS = {
    "sharpe": 0.55,
    "drawdown": 0.30,
    "fee": 0.15,
}


@dataclass(slots=True)
class ActiveMasterReference:
    trader_id: str | None = None
    trader_name: str | None = None
    aliases: set[str] = field(default_factory=set)


@dataclass(slots=True)
class LeaderboardEntry:
    trader_id: str
    trader_name: str
    sharpe_30d: float
    max_drawdown_pct_30d: float
    fee_pct: float
    source: str = "bitmart_aihub"
    snapshot_ref: str | None = None
    is_active_master: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScoredLeaderboardEntry(LeaderboardEntry):
    rank: int = 0
    score: float = 0.0
    score_percentile: float = 0.0


@dataclass(slots=True)
class CopyTraderProposalSummary:
    proposal_id: str
    active_trader_name: str
    candidate_trader_name: str | None
    streak_days: int
    status: str
    telegram_message_id: str | None = None


@dataclass(slots=True)
class CopyTraderCuratorSummary:
    source: str | None = None
    source_refs: list[str] = field(default_factory=list)
    active_masters: list[str] = field(default_factory=list)
    loaded_rows: int = 0
    scored_rows: int = 0
    score_rows_written: int = 0
    skipped_missing_metrics: int = 0
    proposals_created: int = 0
    notifications_sent: int = 0
    warnings: list[str] = field(default_factory=list)
    proposals: list[CopyTraderProposalSummary] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Copy-trader curator",
            "",
            f"- Source: `{self.source or 'unavailable'}`",
            f"- Source refs: {', '.join(f'`{ref}`' for ref in self.source_refs) if self.source_refs else 'none'}",
            f"- Active masters: {', '.join(f'`{name}`' for name in self.active_masters) if self.active_masters else 'none configured'}",
            f"- Leaderboard rows loaded: {self.loaded_rows}",
            f"- Rows scored: {self.scored_rows}",
            f"- Score rows written: {self.score_rows_written}",
            f"- Rows skipped (missing metrics): {self.skipped_missing_metrics}",
            f"- Switch proposals created: {self.proposals_created}",
            f"- Telegram notifications sent: {self.notifications_sent}",
        ]

        if self.proposals:
            lines.extend(["", "## Switch proposals", ""])
            for proposal in self.proposals:
                lines.append(
                    f"- `{proposal.active_trader_name}` → `{proposal.candidate_trader_name or 'n/a'}` "
                    f"after {proposal.streak_days} below-threshold days "
                    f"(status={proposal.status}, proposal_id=`{proposal.proposal_id}`)"
                )

        if self.warnings:
            lines.extend(["", "## Notes", ""])
            for warning in self.warnings:
                lines.append(f"- {warning}")

        if not self.proposals and not self.warnings:
            lines.extend(["", "No curator action was required today."])

        return "\n".join(lines)


def run_copy_trader_curator(
    *,
    database_url: str | None = None,
    observed_at: datetime | None = None,
    leaderboard_rows: Sequence[dict[str, Any]] | None = None,
    active_masters: Sequence[str | dict[str, Any]] | None = None,
    notification_client: TelegramNotificationClient | None = None,
    threshold_percentile: float = DEFAULT_THRESHOLD_PERCENTILE,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS,
) -> CopyTraderCuratorSummary:
    observed_at = (observed_at or datetime.now(UTC)).astimezone(UTC)
    summary = CopyTraderCuratorSummary()

    ensure_time_series_schema(get_engine(database_url=database_url))

    active_refs = _resolve_active_masters(
        active_masters=active_masters,
        database_url=database_url,
    )
    summary.active_masters = [ref.trader_name or ref.trader_id or "unknown" for ref in active_refs]

    raw_rows: Sequence[dict[str, Any]]
    if leaderboard_rows is not None:
        raw_rows = list(leaderboard_rows)
        summary.source = "injected"
        summary.source_refs = ["runtime:leaderboard_rows"]
    else:
        raw_rows, source, source_refs = _load_leaderboard_rows_from_research_memos(
            database_url=database_url,
            observed_at=observed_at,
        )
        summary.source = source
        summary.source_refs = source_refs

    summary.loaded_rows = len(raw_rows)
    if not raw_rows:
        summary.warnings.append(
            "No BitMart AIHub leaderboard snapshot was available in research memos; "
            "persist a memo tagged with `copy_trader_leaderboard` and `bitmart_aihub` to activate this job."
        )
        return summary

    normalized_rows: list[LeaderboardEntry] = []
    for row in raw_rows:
        normalized = _normalize_leaderboard_row(
            row,
            active_refs=active_refs,
            source=summary.source or "bitmart_aihub",
            snapshot_ref=summary.source_refs[0] if summary.source_refs else None,
        )
        if normalized is None:
            summary.skipped_missing_metrics += 1
            continue
        normalized_rows.append(normalized)

    if not normalized_rows:
        summary.warnings.append("Leaderboard rows were present, but none had Sharpe/max drawdown/fee data usable for scoring.")
        return summary

    scored_rows = _score_leaderboard(normalized_rows)
    summary.scored_rows = len(scored_rows)

    with session_scope(database_url=database_url) as session:
        for entry in scored_rows:
            session.add(
                CopyTraderScoreRow(
                    score_time=observed_at,
                    source=entry.source,
                    snapshot_ref=entry.snapshot_ref,
                    trader_id=entry.trader_id,
                    trader_name=entry.trader_name,
                    rank=entry.rank,
                    score=entry.score,
                    score_percentile=entry.score_percentile,
                    sharpe_30d=entry.sharpe_30d,
                    max_drawdown_pct_30d=entry.max_drawdown_pct_30d,
                    fee_pct=entry.fee_pct,
                    is_active_master=entry.is_active_master,
                    metadata_json=entry.metadata,
                )
            )
    summary.score_rows_written = len(scored_rows)

    active_scored_rows = [entry for entry in scored_rows if entry.is_active_master]
    if active_refs and not active_scored_rows:
        summary.warnings.append("Configured active masters were not found in the latest leaderboard snapshot.")
    if not active_refs:
        summary.warnings.append("No active copy-trader masters are configured yet; scores were stored without switch evaluation.")
        return summary

    notification_client = notification_client or TelegramNotificationClient()

    for active_entry in active_scored_rows:
        streak_days = _recent_underperformance_streak(
            trader_id=active_entry.trader_id,
            database_url=database_url,
            threshold_percentile=threshold_percentile,
            threshold_days=threshold_days,
        )
        if streak_days < threshold_days:
            continue

        replacement = _select_replacement_candidate(active_entry, scored_rows)
        if replacement is None:
            summary.warnings.append(
                f"`{active_entry.trader_name}` fell below the threshold, but no stronger replacement candidate was available today."
            )
            continue

        rationale = (
            f"{active_entry.trader_name} has remained below the {threshold_percentile:.0%} percentile "
            f"for {streak_days} daily snapshots. Recommended replacement: {replacement.trader_name}."
        )
        proposal_payload = {
            "active_trader": {
                "trader_id": active_entry.trader_id,
                "trader_name": active_entry.trader_name,
                "rank": active_entry.rank,
                "score": active_entry.score,
                "score_percentile": active_entry.score_percentile,
                "sharpe_30d": active_entry.sharpe_30d,
                "max_drawdown_pct_30d": active_entry.max_drawdown_pct_30d,
                "fee_pct": active_entry.fee_pct,
            },
            "candidate_trader": {
                "trader_id": replacement.trader_id,
                "trader_name": replacement.trader_name,
                "rank": replacement.rank,
                "score": replacement.score,
                "score_percentile": replacement.score_percentile,
                "sharpe_30d": replacement.sharpe_30d,
                "max_drawdown_pct_30d": replacement.max_drawdown_pct_30d,
                "fee_pct": replacement.fee_pct,
            },
            "threshold_days": threshold_days,
            "threshold_percentile": threshold_percentile,
            "source_refs": summary.source_refs,
            "observed_at": observed_at.isoformat(),
            "source": summary.source,
        }
        proposal, created = create_or_get_pending_copy_trader_switch_proposal(
            active_trader_id=active_entry.trader_id,
            active_trader_name=active_entry.trader_name,
            candidate_trader_id=replacement.trader_id,
            candidate_trader_name=replacement.trader_name,
            rationale=rationale,
            active_score=active_entry.score,
            active_percentile=active_entry.score_percentile,
            candidate_score=replacement.score,
            candidate_percentile=replacement.score_percentile,
            threshold_days=threshold_days,
            payload=proposal_payload,
            database_url=database_url,
        )

        telegram_message_id = None
        if created:
            summary.proposals_created += 1
            telegram_message_id = _notify_operator_of_switch_proposal(
                proposal=proposal,
                active_entry=active_entry,
                replacement=replacement,
                threshold_days=threshold_days,
                notification_client=notification_client,
                database_url=database_url,
            )
            if telegram_message_id:
                summary.notifications_sent += 1

        summary.proposals.append(
            CopyTraderProposalSummary(
                proposal_id=proposal["id"],
                active_trader_name=active_entry.trader_name,
                candidate_trader_name=replacement.trader_name,
                streak_days=streak_days,
                status=proposal["status"],
                telegram_message_id=telegram_message_id,
            )
        )

    return summary


def main() -> int:
    summary = run_copy_trader_curator()
    print(summary.to_markdown())
    return 0


def _resolve_active_masters(
    *,
    active_masters: Sequence[str | dict[str, Any]] | None,
    database_url: str | None,
) -> list[ActiveMasterReference]:
    resolved: list[ActiveMasterReference] = []
    for raw in active_masters or _load_active_masters_from_env_or_config():
        reference = _parse_active_master_reference(raw)
        if reference is not None:
            resolved.append(reference)

    if resolved:
        return resolved

    with session_scope(database_url=database_url) as session:
        rows = list(
            session.scalars(
                select(CopyTraderScoreRow)
                .where(CopyTraderScoreRow.is_active_master.is_(True))
                .order_by(desc(CopyTraderScoreRow.score_time))
                .limit(20)
            )
        )

    seen: set[str] = set()
    fallback: list[ActiveMasterReference] = []
    for row in rows:
        if row.trader_id in seen:
            continue
        seen.add(row.trader_id)
        fallback.append(
            ActiveMasterReference(
                trader_id=row.trader_id,
                trader_name=row.trader_name,
                aliases={_normalize_lookup_token(row.trader_id), _normalize_lookup_token(row.trader_name)},
            )
        )
    return fallback


def _load_active_masters_from_env_or_config() -> list[str | dict[str, Any]]:
    env_value = os.getenv("HERMES_COPY_TRADER_ACTIVE_MASTERS", "").strip()
    if env_value:
        parsed = _parse_json_candidate(env_value)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, (str, dict))]
        return [part.strip() for part in env_value.split(",") if part.strip()]

    config_path = get_config_path()
    if not config_path.exists():
        return []

    try:
        import yaml
    except ImportError:
        logger.debug("copy_trader_curator: PyYAML unavailable, skipping config.yaml active master lookup")
        return []

    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("copy_trader_curator: failed to read %s: %s", config_path, exc)
        return []

    if not isinstance(config, dict):
        return []
    section = config.get("copy_trader") or {}
    if not isinstance(section, dict):
        return []
    active = section.get("active_masters") or []
    return active if isinstance(active, list) else []


def _parse_active_master_reference(raw: str | dict[str, Any]) -> ActiveMasterReference | None:
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return None
        token = _normalize_lookup_token(value)
        return ActiveMasterReference(trader_id=value, trader_name=value, aliases={token})

    if not isinstance(raw, dict):
        return None

    trader_id = _first_present(raw, "trader_id", "master_id", "id", "slug")
    trader_name = _first_present(raw, "trader_name", "name", "display_name", "nickname")
    aliases = {
        _normalize_lookup_token(item)
        for item in [
            trader_id,
            trader_name,
            *list(raw.get("aliases") or []),
        ]
        if item
    }
    if not aliases:
        return None
    return ActiveMasterReference(
        trader_id=str(trader_id).strip() if trader_id else None,
        trader_name=str(trader_name).strip() if trader_name else None,
        aliases=aliases,
    )


def _load_leaderboard_rows_from_research_memos(
    *,
    database_url: str | None,
    observed_at: datetime,
) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    since_dt = observed_at - timedelta(hours=DEFAULT_LOOKBACK_HOURS)
    with session_scope(database_url=database_url) as session:
        rows = list(
            session.scalars(
                select(ResearchMemoRow)
                .where(ResearchMemoRow.memo_time >= since_dt)
                .order_by(desc(ResearchMemoRow.memo_time))
                .limit(25)
            )
        )

    for memo in rows:
        memo_tags = {_normalize_lookup_token(tag) for tag in (memo.tags or [])}
        if memo_tags and not memo_tags.intersection({_normalize_lookup_token(tag) for tag in LEADERBOARD_MEMO_TAGS}):
            continue
        payload = _extract_json_payload(memo.content)
        leaderboard_rows = _rows_from_payload(payload)
        if leaderboard_rows:
            return leaderboard_rows, "research_memo", [f"research_memo:{memo.id}"]

    return [], None, []


def _extract_json_payload(text: str) -> Any:
    for candidate in _json_candidates(text):
        parsed = _parse_json_candidate(candidate)
        if parsed is not None:
            return parsed
    return None


def _json_candidates(text: str) -> Iterable[str]:
    raw = (text or "").strip()
    if raw:
        yield raw

    for pattern in (
        r"```json\s*(.*?)```",
        r"```\s*(.*?)```",
    ):
        for match in re.findall(pattern, text or "", flags=re.IGNORECASE | re.DOTALL):
            candidate = str(match).strip()
            if candidate:
                yield candidate


def _parse_json_candidate(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("leaderboard", "rows", "traders", "masters", "results", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _normalize_leaderboard_row(
    row: dict[str, Any],
    *,
    active_refs: Sequence[ActiveMasterReference],
    source: str,
    snapshot_ref: str | None,
) -> LeaderboardEntry | None:
    trader_id = _stringify(_first_present(row, "trader_id", "master_id", "id", "uid", "slug", "user_id"))
    trader_name = _stringify(_first_present(row, "trader_name", "name", "display_name", "nickname", "master_name"))
    trader_id = trader_id or trader_name
    trader_name = trader_name or trader_id
    if not trader_id or not trader_name:
        return None

    sharpe = _coerce_float(_first_present(row, "sharpe_30d", "sharpe30d", "rolling_sharpe_30d", "sharpe"))
    max_drawdown = _normalize_percent_metric(
        _first_present(
            row,
            "max_drawdown_pct_30d",
            "max_drawdown_30d",
            "max_dd_30d",
            "max_drawdown",
            "maxdrawdown",
            "drawdown_30d",
            "drawdown",
        )
    )
    fee_pct = _normalize_percent_metric(
        _first_present(
            row,
            "fee_pct",
            "copy_fee_pct",
            "performance_fee_pct",
            "fee",
            "fee_rate",
            "copy_trade_fee",
        )
    )
    if sharpe is None or max_drawdown is None or fee_pct is None:
        return None

    if not isfinite(sharpe) or not isfinite(max_drawdown) or not isfinite(fee_pct):
        return None

    normalized_tokens = {
        _normalize_lookup_token(trader_id),
        _normalize_lookup_token(trader_name),
    }
    is_active = any(normalized_tokens.intersection(ref.aliases) for ref in active_refs)
    return LeaderboardEntry(
        trader_id=trader_id,
        trader_name=trader_name,
        sharpe_30d=sharpe,
        max_drawdown_pct_30d=max_drawdown,
        fee_pct=fee_pct,
        source=source,
        snapshot_ref=snapshot_ref,
        is_active_master=is_active,
        metadata={"raw": row},
    )


def _score_leaderboard(rows: Sequence[LeaderboardEntry]) -> list[ScoredLeaderboardEntry]:
    sharpe_values = [row.sharpe_30d for row in rows]
    drawdown_values = [row.max_drawdown_pct_30d for row in rows]
    fee_values = [row.fee_pct for row in rows]

    scored: list[ScoredLeaderboardEntry] = []
    for row in rows:
        sharpe_component = _scale_high_is_good(row.sharpe_30d, sharpe_values)
        drawdown_component = _scale_low_is_good(row.max_drawdown_pct_30d, drawdown_values)
        fee_component = _scale_low_is_good(row.fee_pct, fee_values)
        total_score = (
            SCORING_WEIGHTS["sharpe"] * sharpe_component
            + SCORING_WEIGHTS["drawdown"] * drawdown_component
            + SCORING_WEIGHTS["fee"] * fee_component
        )
        scored.append(
            ScoredLeaderboardEntry(
                trader_id=row.trader_id,
                trader_name=row.trader_name,
                sharpe_30d=row.sharpe_30d,
                max_drawdown_pct_30d=row.max_drawdown_pct_30d,
                fee_pct=row.fee_pct,
                source=row.source,
                snapshot_ref=row.snapshot_ref,
                is_active_master=row.is_active_master,
                metadata={
                    **row.metadata,
                    "score_components": {
                        "sharpe": round(sharpe_component, 6),
                        "drawdown": round(drawdown_component, 6),
                        "fee": round(fee_component, 6),
                    },
                },
                score=round(total_score, 6),
            )
        )

    scored.sort(
        key=lambda entry: (
            -entry.score,
            -entry.sharpe_30d,
            entry.max_drawdown_pct_30d,
            entry.fee_pct,
            entry.trader_name.lower(),
        )
    )
    total = len(scored)
    for index, entry in enumerate(scored, start=1):
        entry.rank = index
        entry.score_percentile = 1.0 if total == 1 else round(1.0 - ((index - 1) / (total - 1)), 6)
    return scored


def _recent_underperformance_streak(
    *,
    trader_id: str,
    database_url: str | None,
    threshold_percentile: float,
    threshold_days: int,
) -> int:
    with session_scope(database_url=database_url) as session:
        rows = list(
            session.scalars(
                select(CopyTraderScoreRow)
                .where(CopyTraderScoreRow.trader_id == trader_id)
                .order_by(desc(CopyTraderScoreRow.score_time))
                .limit(max(30, threshold_days * 4))
            )
        )

    streak = 0
    seen_dates: set[date] = set()
    for row in rows:
        score_date = row.score_time.astimezone(UTC).date()
        if score_date in seen_dates:
            continue
        seen_dates.add(score_date)
        if row.score_percentile < threshold_percentile:
            streak += 1
        else:
            break
        if streak >= threshold_days:
            break
    return streak


def _select_replacement_candidate(
    active_entry: ScoredLeaderboardEntry,
    scored_rows: Sequence[ScoredLeaderboardEntry],
) -> ScoredLeaderboardEntry | None:
    for candidate in scored_rows:
        if candidate.is_active_master:
            continue
        if candidate.score <= active_entry.score:
            continue
        return candidate
    return None


def _notify_operator_of_switch_proposal(
    *,
    proposal: dict[str, Any],
    active_entry: ScoredLeaderboardEntry,
    replacement: ScoredLeaderboardEntry,
    threshold_days: int,
    notification_client: TelegramNotificationClient,
    database_url: str | None,
) -> str | None:
    if not notification_client.configured:
        logger.warning("copy_trader_curator: Telegram is not configured; proposal %s was stored but not sent", proposal["id"])
        return None

    text = "\n".join(
        [
            "📈 Copy-trader curator recommendation",
            "",
            f"Active master: {active_entry.trader_name}",
            f"- Rank: #{active_entry.rank}",
            f"- Score: {active_entry.score:.3f}",
            f"- Percentile: {active_entry.score_percentile:.0%}",
            f"- Sharpe (30d): {active_entry.sharpe_30d:.2f}",
            f"- Max DD (30d): {active_entry.max_drawdown_pct_30d:.2f}%",
            f"- Fee: {active_entry.fee_pct:.2f}%",
            "",
            f"Suggested replacement: {replacement.trader_name}",
            f"- Rank: #{replacement.rank}",
            f"- Score: {replacement.score:.3f}",
            f"- Percentile: {replacement.score_percentile:.0%}",
            f"- Sharpe (30d): {replacement.sharpe_30d:.2f}",
            f"- Max DD (30d): {replacement.max_drawdown_pct_30d:.2f}%",
            f"- Fee: {replacement.fee_pct:.2f}%",
            "",
            f"Trigger: below 60th percentile for {threshold_days} daily snapshots.",
            "Approving this recommendation records operator intent only; the actual BitMart copy-trader switch remains manual until exchange automation is supported.",
        ]
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Approve switch", "callback_data": f"cts:a:{proposal['id']}"},
                {"text": "❌ Keep current", "callback_data": f"cts:r:{proposal['id']}"},
            ]
        ]
    }

    try:
        response = notification_client.send_message(text, reply_markup=keyboard)
    except Exception as exc:
        logger.warning("copy_trader_curator: failed to send Telegram approval for proposal %s: %s", proposal["id"], exc)
        return None

    message_id = response.get("message_id") if isinstance(response, dict) else None
    if message_id is not None:
        mark_copy_trader_switch_proposal_notified(
            proposal["id"],
            channel="telegram",
            message_id=str(message_id),
            database_url=database_url,
        )
    return str(message_id) if message_id is not None else None


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        lowered_key = key.lower()
        if lowered_key in lowered and lowered[lowered_key] not in (None, ""):
            return lowered[lowered_key]

    metrics = row.get("metrics")
    if isinstance(metrics, dict):
        return _first_present(metrics, *keys)
    stats = row.get("stats")
    if isinstance(stats, dict):
        return _first_present(stats, *keys)
    return None


def _normalize_percent_metric(value: Any) -> float | None:
    numeric = _coerce_float(value)
    if numeric is None:
        return None
    numeric = abs(numeric)
    if numeric <= 1.0:
        numeric *= 100.0
    return numeric


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip().replace("%", "")
        if not stripped:
            return None
        value = stripped
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _scale_high_is_good(value: float, population: Sequence[float]) -> float:
    minimum = min(population)
    maximum = max(population)
    if maximum == minimum:
        return 1.0
    return (value - minimum) / (maximum - minimum)


def _scale_low_is_good(value: float, population: Sequence[float]) -> float:
    minimum = min(population)
    maximum = max(population)
    if maximum == minimum:
        return 1.0
    return (maximum - value) / (maximum - minimum)


def _normalize_lookup_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    raise SystemExit(main())