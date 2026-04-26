import Link from "next/link";
import {
  fetchHermesApi,
  formatTimestamp,
  formatUsd,
  formatPct,
  type PositionMonitorResponse,
  type MovementsResponse,
} from "../../lib/hermes-api";

function PnlValue({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="muted">—</span>;
  const cls = value >= 0 ? "pnl-positive" : "pnl-negative";
  const sign = value >= 0 ? "+" : "";
  return <span className={cls}>{sign}{formatUsd(value)}</span>;
}

function SideBadge({ side }: { side: string }) {
  const isLong = side?.toUpperCase() === "LONG" || side?.toUpperCase() === "BUY";
  return (
    <span className={`side-badge ${isLong ? "side-badge-long" : "side-badge-short"}`}>
      {side?.toUpperCase() ?? "—"}
    </span>
  );
}

export default async function PositionsPage() {
  const [positionsResult, movementsResult] = await Promise.all([
    fetchHermesApi<PositionMonitorResponse>("/execution/positions/monitor", {
      fallback: {
        status: "offline",
        monitor: {
          account_id: "—",
          observed_at: new Date().toISOString(),
          portfolio: {
            account_id: "—",
            total_equity_usd: 0,
            cash_usd: 0,
            exposure_usd: null,
            positions: [],
            updated_at: null,
            snapshot_metadata: null,
          },
          risk_summary: {
            total_positions: 0,
            largest_position_symbol: null,
            largest_position_notional_usd: null,
            largest_position_weight: null,
            cash_buffer_pct: 1,
            gross_exposure_pct: null,
            warnings: [],
          },
          position_states: [],
          snapshot_metadata: null,
          state_mode: "unknown",
          last_execution: null,
          source: "offline",
        },
      },
    }),
    fetchHermesApi<MovementsResponse>("/execution/movements", {
      fallback: { status: "offline", count: 0, movements: [] },
    }),
  ]);

  const monitor = positionsResult.data.monitor;
  const portfolio = monitor?.portfolio;
  const riskSummary = monitor?.risk_summary;
  const positions = monitor?.position_states ?? portfolio?.positions ?? [];
  const meta = monitor?.snapshot_metadata;
  const movements = movementsResult.data.movements ?? [];

  const equity = portfolio?.total_equity_usd ?? 0;
  const cashUsd = portfolio?.cash_usd ?? 0;
  const exposureUsd = portfolio?.exposure_usd ?? null;
  const positionCount = riskSummary?.total_positions ?? positions.length;
  const cashBufferPct = riskSummary?.cash_buffer_pct ?? null;
  const grossExposurePct = riskSummary?.gross_exposure_pct ?? null;

  const exchange = meta?.exchange ?? "BITMART";
  const executionMode = meta?.execution_mode ?? "unknown";
  const asOf = meta?.as_of ?? null;
  const warnings = riskSummary?.warnings ?? [];

  const isLive = positionsResult.ok;

  return (
    <section className="page-shell">

      {/* ── HEADER ──────────────────────────────────────────────────── */}
      <div className="positions-page-header">
        <div>
          <p className="eyebrow">
            <Link href="/" className="eyebrow-link">Dashboard</Link>
            <span className="eyebrow-sep">·</span>
            Positions
          </p>
          <h1 className="positions-page-title">Live Positions</h1>
          <p className="lede">
            Real-time position monitor for {exchange} · {executionMode.toUpperCase()}.
            {asOf && <> Snapshot as of {formatTimestamp(asOf)}.</>}
          </p>
        </div>
        <div className="positions-header-badges">
          <span className={`live-indicator ${isLive ? "live-indicator-on" : "live-indicator-off"}`}>
            <span className="live-indicator-dot" />
            {isLive ? "LIVE" : "OFFLINE"}
          </span>
          <span className="mode-badge mode-badge-live">{executionMode.toUpperCase()}</span>
          <span className="status-bar-exchange">{exchange}</span>
        </div>
      </div>

      {/* ── PORTFOLIO STATS ──────────────────────────────────────────── */}
      <div className="grid stats positions-stats">
        <article className="card stat-card">
          <div className="stat-label">Total Equity</div>
          <div className="stat-value positions-equity">{formatUsd(equity)}</div>
          <div className="muted">Account {portfolio?.account_id ?? "—"}</div>
        </article>
        <article className="card stat-card">
          <div className="stat-label">Cash</div>
          <div className="stat-value">{formatUsd(cashUsd)}</div>
          <div className="muted">Available balance</div>
        </article>
        <article className="card stat-card">
          <div className="stat-label">Exposure</div>
          <div className="stat-value">{formatUsd(exposureUsd)}</div>
          <div className="muted">Gross deployed</div>
        </article>
        <article className="card stat-card">
          <div className="stat-label">Cash Buffer</div>
          <div className="stat-value">{formatPct(cashBufferPct)}</div>
          <div className="muted">Liquidity cushion</div>
        </article>
        <article className="card stat-card">
          <div className="stat-label">Gross Exposure</div>
          <div className="stat-value">{formatPct(grossExposurePct)}</div>
          <div className="muted">Portfolio weight</div>
        </article>
        <article className="card stat-card">
          <div className="stat-label">Open Positions</div>
          <div className={`stat-value ${positionCount > 0 ? "text-accent" : ""}`}>{positionCount}</div>
          <div className="muted">Active contracts</div>
        </article>
      </div>

      {/* ── RISK WARNINGS ────────────────────────────────────────────── */}
      {warnings.length > 0 && (
        <div className="risk-warnings-bar page-section">
          {warnings.map((w, i) => (
            <div key={i} className="risk-warning-item">
              <span className="risk-warning-icon">⚠</span>
              {w}
            </div>
          ))}
        </div>
      )}

      {/* ── POSITIONS TABLE ──────────────────────────────────────────── */}
      <article className="card page-section">
        <div className="card-header">
          <h2>Open Positions</h2>
          <span className={`pill ${positionCount > 0 ? "pill-live" : ""}`}>
            {positionCount} positions
          </span>
        </div>

        {positions.length > 0 ? (
          <div className="positions-table-wrapper">
            <table className="positions-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Entry</th>
                  <th>Mark</th>
                  <th>Notional</th>
                  <th>Unrealised P&L</th>
                  <th>Weight</th>
                  <th>Lev</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos, i) => (
                  <tr key={pos.symbol ?? i}>
                    <td className="pos-symbol">{pos.symbol}</td>
                    <td><SideBadge side={pos.side} /></td>
                    <td className="pos-num">{pos.qty ?? "—"}</td>
                    <td className="pos-num">{formatUsd(pos.entry_price)}</td>
                    <td className="pos-num">{formatUsd(pos.mark_price)}</td>
                    <td className="pos-num">{formatUsd(pos.notional_usd)}</td>
                    <td className="pos-num"><PnlValue value={pos.unrealized_pnl} /></td>
                    <td className="pos-num">{formatPct(pos.weight)}</td>
                    <td className="pos-num">{pos.leverage != null ? `${pos.leverage}x` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="positions-empty">
            <div className="positions-empty-icon">◈</div>
            <p>No open positions.</p>
            <p className="muted">
              Portfolio is fully in cash — {formatUsd(cashUsd)} available.
            </p>
          </div>
        )}
      </article>

      {/* ── RECENT MOVEMENTS ────────────────────────────────────────── */}
      <article className="card page-section">
        <div className="card-header">
          <h2>Recent Movements</h2>
          <span className="pill">{movementsResult.data.count ?? 0} recorded</span>
        </div>

        {movements.length > 0 ? (
          <div className="positions-table-wrapper">
            <table className="positions-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Notional</th>
                  <th>Cash Delta</th>
                </tr>
              </thead>
              <tbody>
                {movements.slice(0, 20).map((mov) => (
                  <tr key={mov.id}>
                    <td className="muted">{formatTimestamp(mov.created_at)}</td>
                    <td className="pos-symbol">{mov.symbol ?? "—"}</td>
                    <td>{mov.side ? <SideBadge side={String(mov.side)} /> : <span className="muted">—</span>}</td>
                    <td className="pos-num">{formatUsd(mov.notional_usd)}</td>
                    <td className="pos-num"><PnlValue value={mov.cash_delta_usd} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="positions-empty positions-empty-sm">
            <p className="muted">No movement history recorded yet.</p>
          </div>
        )}
      </article>

      {/* ── SNAPSHOT META ─────────────────────────────────────────────── */}
      {meta && (
        <article className="card page-section snapshot-meta-card">
          <h2>Snapshot Metadata</h2>
          <div className="snapshot-meta-grid">
            <div><span className="stat-label">Source</span><div>{meta.source}</div></div>
            <div><span className="stat-label">Mode</span><div>{meta.execution_mode}</div></div>
            <div><span className="stat-label">Exchange</span><div>{meta.exchange}</div></div>
            <div><span className="stat-label">Account Type</span><div>{meta.account_type}</div></div>
            <div><span className="stat-label">As Of</span><div className="muted">{formatTimestamp(meta.as_of)}</div></div>
            <div><span className="stat-label">Positions Count</span><div>{meta.positions_count}</div></div>
          </div>
        </article>
      )}

    </section>
  );
}
