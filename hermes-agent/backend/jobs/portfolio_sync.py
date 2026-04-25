"""Exchange-backed portfolio snapshot sync job."""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass

from backend.integrations.base import IntegrationError, MissingCredentialError
from backend.services.portfolio_sync import sync_portfolio_from_exchange

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PortfolioSyncSummary:
    account_id: str
    total_equity_usd: float | None
    cash_usd: float | None
    exposure_usd: float | None
    positions_count: int
    updated_at: str | None
    success: bool
    detail: str | None = None

    def to_markdown(self) -> str:
        lines = [
            "# Portfolio sync",
            "",
            f"- Account: `{self.account_id}`",
            f"- Total equity: {self.total_equity_usd if self.total_equity_usd is not None else 'n/a'}",
            f"- Cash: {self.cash_usd if self.cash_usd is not None else 'n/a'}",
            f"- Exposure: {self.exposure_usd if self.exposure_usd is not None else 'n/a'}",
            f"- Positions: {self.positions_count}",
            f"- Updated at: {self.updated_at if self.updated_at is not None else 'n/a'}",
            f"- Success: {'yes' if self.success else 'no'}",
        ]
        if self.detail:
            lines.extend(["", self.detail])
        return "\n".join(lines)


def run_portfolio_sync(*, account_id: str | None = None) -> PortfolioSyncSummary:
    try:
        state = sync_portfolio_from_exchange(account_id=account_id)
        return PortfolioSyncSummary(
            account_id=state.account_id,
            total_equity_usd=state.total_equity_usd,
            cash_usd=state.cash_usd,
            exposure_usd=state.exposure_usd,
            positions_count=len(state.positions),
            updated_at=state.updated_at,
            success=True,
            detail="Portfolio snapshot synced and persisted successfully.",
        )
    except (MissingCredentialError, IntegrationError) as exc:
        logger.error("portfolio_sync job failed: %s", exc)
        return PortfolioSyncSummary(
            account_id=account_id or "paper",
            total_equity_usd=None,
            cash_usd=None,
            exposure_usd=None,
            positions_count=0,
            updated_at=None,
            success=False,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("portfolio_sync job failed unexpectedly: %s", exc)
        return PortfolioSyncSummary(
            account_id=account_id or "paper",
            total_equity_usd=None,
            cash_usd=None,
            exposure_usd=None,
            positions_count=0,
            updated_at=None,
            success=False,
            detail="Unexpected portfolio sync failure:\n" + traceback.format_exc(),
        )


def main() -> int:
    summary = run_portfolio_sync()
    print(summary.to_markdown())
    return 0 if summary.success else 1


if __name__ == "__main__":
    raise SystemExit(main())