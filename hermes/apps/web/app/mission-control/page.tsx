import { fetchHermesApi, formatTimestamp } from "../../lib/hermes-api";
import { KillSwitchPanel } from "../../components/KillSwitchPanel";
import { PortfolioSyncButton } from "../../components/PortfolioSyncButton";
import { ApprovalQueuePanel, type PendingApproval } from "../../components/ApprovalQueuePanel";

type ExecutionSnapshot = {
  status: string;
  execution: {
    exchange: string;
    configured: boolean;
    trading_mode?: string;
    pending_signal_count: number;
    pending_signal_events: Array<{
      id: string;
      event_type: string;
      symbol: string | null;
      delivery_status: string;
      ts: number;
      payload?: {
        correlation_id?: string;
        signal?: string;
        direction?: string;
        strategy?: string;
        timeframe?: string;
      };
    }>;
    recent_execution_events: Array<{
      id: string;
      event_type: string;
      status: string;
      created_at: string;
      symbol?: string | null;
    }>;
  };
};

type RiskSnapshot = {
  status: string;
  risk: {
    kill_switch?: { active: boolean; reason?: string | null; updated_at?: string | null };
    recent_risk_rejections: Array<{
      id: string;
      agent_name: string;
      status: string;
      decision: string | null;
      created_at: string;
    }>;
    recent_failures: Array<{
      id: string;
      error_type: string | null;
      error_message: string | null;
      created_at: string;
    }>;
  };
};

type WorkflowSnapshot = {
  status: string;
  workflow_runs: Array<{
    id: string;
    workflow_name: string;
    status: string;
    created_at: string;
    correlation_id?: string | null;
  }>;
};

type PortfolioSnapshot = {
  status: string;
  portfolio: {
    data: {
      account_id: string;
      total_equity_usd: number | null;
      cash_usd: number | null;
      exposure_usd: number | null;
      positions: Array<{ symbol: string; quantity: number; notional_usd: number | null }>;
      updated_at: string | null;
    };
    meta: { warnings: string[] };
  };
};

type AlertSnapshot = {
  status: string;
  count: number;
  alerts: Array<{
    id: string;
    symbol: string | null;
    signal: string | null;
    direction: string | null;
    strategy: string | null;
    timeframe: string | null;
    processing_status: string;
    event_time: string;
    price?: number | null;
  }>;
};

type MovementRecord = {
  id: string;
  movement_time: string;
  symbol: string | null;
  movement_type: string;
  status: string;
  side?: string | null;
  quantity?: number | null;
  cash_delta_usd?: number | null;
  notional_delta_usd?: number | null;
  price?: number | null;
  execution_mode?: string | null;
  correlation_id?: string | null;
};

type MovementSnapshot = {
  status: string;
  count: number;
  movements: MovementRecord[];
};

type ObservabilitySnapshot = {
  status: string;
  dashboard: {
    recent_failures: Array<{
      id: string;
      error_type?: string | null;
      error_message?: string | null;
      created_at: string;
    }>;
    recent_execution_events: Array<{
      id: string;
      event_type?: string | null;
      status: string;
      created_at: string;
      symbol?: string | null;
    }>;
    recent_movements?: MovementRecord[];
    recent_notifications: Array<{
      id: string;
      channel: string | null;
      sent_time: string | null;
      detail?: string | null;
    }>;
  };
};

function formatUsd(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatCompact(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatQuantity(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);
}

function buildSparkline(values: number[], width = 260, height = 74): string {
  if (values.length <= 1) return `M 0 ${height / 2} L ${width} ${height / 2}`;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  return values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * height;
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function tradingViewSymbol(symbol: string | null | undefined): string {
  return `BITMART:${(symbol || "BTCUSDT").replace(/[^A-Z0-9]/gi, "")}`;
}

export default async function MissionControlPage() {
  const [executionResult, riskResult, workflowResult, portfolioResult, approvalsResult, alertsResult, movementsResult, dashboardResult] =
    await Promise.all([
      fetchHermesApi<ExecutionSnapshot>("/execution", {
        fallback: {
          status: "offline",
          execution: {
            exchange: "BITMART",
            configured: false,
            trading_mode: "paper",
            pending_signal_count: 0,
            pending_signal_events: [],
            recent_execution_events: [],
          },
        },
      }),
      fetchHermesApi<RiskSnapshot>("/risk", {
        fallback: {
          status: "offline",
          risk: {
            kill_switch: { active: false },
            recent_risk_rejections: [],
            recent_failures: [],
          },
        },
      }),
      fetchHermesApi<WorkflowSnapshot>("/observability/workflows?limit=12", {
        fallback: { status: "offline", workflow_runs: [] },
      }),
      fetchHermesApi<PortfolioSnapshot>("/portfolio", {
        fallback: {
          status: "offline",
          portfolio: {
            data: {
              account_id: "paper",
              total_equity_usd: null,
              cash_usd: null,
              exposure_usd: null,
              positions: [],
              updated_at: null,
            },
            meta: { warnings: ["API offline"] },
          },
        },
      }),
      fetchHermesApi<{ approvals: PendingApproval[] }>("/execution/approvals/pending", {
        fallback: { approvals: [] },
      }),
      fetchHermesApi<AlertSnapshot>("/execution/alerts/recent?limit=10", {
        fallback: { status: "offline", count: 0, alerts: [] },
      }),
      fetchHermesApi<MovementSnapshot>("/execution/movements?limit=12", {
        fallback: { status: "offline", count: 0, movements: [] },
      }),
      fetchHermesApi<ObservabilitySnapshot>("/observability/", {
        fallback: {
          status: "offline",
          dashboard: {
            recent_failures: [],
            recent_execution_events: [],
            recent_movements: [],
            recent_notifications: [],
          },
        },
      }),
    ]);

  const killSwitchState = riskResult.data.risk.kill_switch ?? { active: false };
  const portfolio = portfolioResult.data.portfolio?.data;
  const portfolioWarnings = portfolioResult.data.portfolio?.meta?.warnings ?? [];
  const pendingApprovals = approvalsResult.data.approvals ?? [];
  const pendingSignals = executionResult.data.execution.pending_signal_events ?? [];
  const recentAlerts = alertsResult.data.alerts ?? [];
  const recentMovements = movementsResult.data.movements.length > 0
    ? movementsResult.data.movements
    : dashboardResult.data.dashboard.recent_movements ?? [];
  const activeWorkflows = workflowResult.data.workflow_runs.filter((run) =>
    ["pending", "running", "manual_review", "in_progress"].includes(run.status),
  );
  const focusSymbol =
    pendingSignals[0]?.symbol ??
    recentAlerts[0]?.symbol ??
    recentMovements[0]?.symbol ??
    portfolio?.positions[0]?.symbol ??
    "BTCUSDT";
  const focusSignal = pendingSignals[0]?.payload?.signal ?? recentAlerts[0]?.signal ?? "watch";
  const tradingViewUrl = `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(tradingViewSymbol(focusSymbol))}&interval=60&theme=dark&style=1&timezone=Etc%2FUTC&withdateranges=1&hide_side_toolbar=0&allow_symbol_change=1&saveimage=0`;
  const movementSeries = recentMovements
    .slice()
    .reverse()
    .map((movement) => Number(movement.notional_delta_usd ?? movement.cash_delta_usd ?? movement.quantity ?? 0));
  const sparklinePath = buildSparkline(movementSeries.length > 1 ? movementSeries : [0, 0]);
  const maxPositionNotional = Math.max(
    1,
    ...(portfolio?.positions ?? []).map((position) => Math.abs(position.notional_usd ?? 0)),
  );
  const openTaskCount = pendingApprovals.length + pendingSignals.length + activeWorkflows.length;

  const taskLanes = [
    {
      name: "Approval queue",
      items: pendingApprovals.slice(0, 4).map((approval) => ({
        key: approval.approval_id,
        title: `${approval.symbol ?? "Unknown"} ${approval.side?.toUpperCase() ?? "REVIEW"}`,
        detail: `Needs operator decision${approval.created_at ? ` · ${formatTimestamp(approval.created_at)}` : ""}`,
      })),
    },
    {
      name: "Signal intake",
      items: pendingSignals.slice(0, 4).map((event) => ({
        key: event.id,
        title: `${event.symbol ?? "Unknown"} ${event.payload?.signal ?? event.payload?.direction ?? event.event_type}`,
        detail: `${event.delivery_status} · queued ${formatTimestamp(new Date(event.ts * 1000).toISOString())}`,
      })),
    },
    {
      name: "Workflow tasks",
      items: activeWorkflows.slice(0, 4).map((run) => ({
        key: run.id,
        title: run.workflow_name,
        detail: `${run.status} · ${formatTimestamp(run.created_at)}`,
      })),
    },
  ];

  return (
    <section className="page-shell mission-control-page">
      <div className="hero mission-hero">
        <p className="eyebrow">Mission Control</p>
        <h1>Human oversight for trades, tasks, and runtime intervention.</h1>
        <p className="lede">
          Built from the Mission Control markdown contract: system state, trade proposals,
          approval queues, notifications, exception review, and TradingView-linked market
          context in one operator-facing surface.
        </p>
      </div>

      <div className="grid stats mission-metrics">
        <article className="card">
          <div className="stat-label">Open operator tasks</div>
          <div className="stat-value">{openTaskCount}</div>
          <div className="muted">Approvals, signal intake, and active workflow tasks.</div>
        </article>
        <article className="card">
          <div className="stat-label">Recorded trade movements</div>
          <div className="stat-value">{recentMovements.length}</div>
          <div className="muted">Journaled fills, projections, and portfolio sync records.</div>
        </article>
        <article className="card">
          <div className="stat-label">Portfolio equity</div>
          <div className="stat-value">{formatCompact(portfolio?.total_equity_usd)}</div>
          <div className="muted">Cash {formatUsd(portfolio?.cash_usd)} · exposure {formatUsd(portfolio?.exposure_usd)}</div>
        </article>
        <article className="card">
          <div className="stat-label">Focus symbol</div>
          <div className="stat-value">{focusSymbol}</div>
          <div className="muted">Signal context: {focusSignal}</div>
        </article>
      </div>

      <div className="mission-layout">
        <div className="mission-primary">
          <div className="grid split page-section">
            <article className="card tv-card">
              <div className="resource-row">
                <div>
                  <h2>TradingView-linked market focus</h2>
                  <p className="muted">Current spotlight chart for signal review and replay.</p>
                </div>
                <span className="pill pill-live">{focusSymbol}</span>
              </div>
              <div className="tv-meta-row">
                <span className="pill pill-partial">{executionResult.data.execution.exchange}</span>
                <span className="pill pill-live">Mode {executionResult.data.execution.trading_mode ?? "paper"}</span>
                <span className="pill pill-partial">{pendingSignals.length} queued signals</span>
              </div>
              <iframe
                className="tv-frame"
                title={`TradingView chart for ${focusSymbol}`}
                src={tradingViewUrl}
                loading="lazy"
              />
            </article>

            <article className="card chart-card">
              <h2>Movement pulse</h2>
              <p className="muted">Recent trade and portfolio deltas from the canonical movement journal.</p>
              <svg viewBox="0 0 260 74" className="sparkline" role="img" aria-label="Recent movement pulse">
                <path d={sparklinePath} fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" />
              </svg>
              <div className="mini-kpis">
                <div>
                  <span className="stat-label">Latest notional</span>
                  <div className="mini-kpi-value">{formatUsd(recentMovements[0]?.notional_delta_usd)}</div>
                </div>
                <div>
                  <span className="stat-label">Latest cash delta</span>
                  <div className="mini-kpi-value">{formatUsd(recentMovements[0]?.cash_delta_usd)}</div>
                </div>
              </div>
              <h3>Position map</h3>
              <div className="position-map">
                {(portfolio?.positions ?? []).slice(0, 5).map((position) => (
                  <div key={position.symbol} className="position-row">
                    <div className="resource-row">
                      <strong>{position.symbol}</strong>
                      <span className="muted">{formatUsd(position.notional_usd)}</span>
                    </div>
                    <div className="bar-track">
                      <div
                        className="bar-fill"
                        style={{
                          width: `${Math.max(8, (Math.abs(position.notional_usd ?? 0) / maxPositionNotional) * 100)}%`,
                        }}
                      />
                    </div>
                  </div>
                ))}
                {(portfolio?.positions ?? []).length === 0 ? (
                  <p className="muted">No live positions are currently recorded.</p>
                ) : null}
              </div>
            </article>
          </div>

          <div className="grid split page-section">
            <KillSwitchPanel initialState={killSwitchState} />

            <article className="card">
              <h2>Portfolio command center</h2>
              {portfolioWarnings.length > 0 ? <p className="mission-warning">{portfolioWarnings[0]}</p> : null}
              <div className="mission-summary-grid">
                <div>
                  <span className="stat-label">Account</span>
                  <div className="mini-kpi-value">{portfolio?.account_id ?? "paper"}</div>
                </div>
                <div>
                  <span className="stat-label">Total equity</span>
                  <div className="mini-kpi-value">{formatUsd(portfolio?.total_equity_usd)}</div>
                </div>
                <div>
                  <span className="stat-label">Last sync</span>
                  <div className="mini-kpi-value">{formatTimestamp(portfolio?.updated_at)}</div>
                </div>
              </div>
              <PortfolioSyncButton />
            </article>
          </div>

          <div className="grid split page-section">
            <article className="card">
              <h2>Task lanes</h2>
              <div className="task-lanes">
                {taskLanes.map((lane) => (
                  <div key={lane.name} className="task-lane">
                    <div className="resource-row">
                      <strong>{lane.name}</strong>
                      <span className="pill pill-partial">{lane.items.length}</span>
                    </div>
                    <ul className="list">
                      {lane.items.map((item) => (
                        <li key={item.key}>
                          <strong>{item.title}</strong>
                          <div className="muted">{item.detail}</div>
                        </li>
                      ))}
                      {lane.items.length === 0 ? <li className="muted">No open tasks in this lane.</li> : null}
                    </ul>
                  </div>
                ))}
              </div>
            </article>

            <ApprovalQueuePanel initialApprovals={pendingApprovals} />
          </div>

          <div className="grid split page-section">
            <article className="card">
              <h2>Trade tape / movement journal</h2>
              <div className="trade-table">
                {recentMovements.slice(0, 8).map((movement) => (
                  <div key={movement.id} className="trade-row">
                    <div>
                      <strong>{movement.symbol ?? "Unknown"}</strong>
                      <div className="muted">{movement.movement_type} · {movement.side ?? movement.status}</div>
                    </div>
                    <div>
                      <div>{formatQuantity(movement.quantity)}</div>
                      <div className="muted">qty</div>
                    </div>
                    <div>
                      <div>{formatUsd(movement.notional_delta_usd)}</div>
                      <div className="muted">notional</div>
                    </div>
                    <div>
                      <div>{formatUsd(movement.cash_delta_usd)}</div>
                      <div className="muted">cash</div>
                    </div>
                    <div className="muted">{formatTimestamp(movement.movement_time)}</div>
                  </div>
                ))}
                {recentMovements.length === 0 ? <p className="muted">No movement journal entries are available yet.</p> : null}
              </div>
            </article>

            <article className="card">
              <h2>TradingView signal board</h2>
              <ul className="list">
                {recentAlerts.slice(0, 6).map((alert) => (
                  <li key={alert.id}>
                    <strong>{alert.symbol ?? "Unknown"}</strong>
                    <div className="muted">
                      {alert.signal ?? alert.direction ?? alert.processing_status}
                      {alert.strategy ? ` · ${alert.strategy}` : ""}
                      {alert.timeframe ? ` · ${alert.timeframe}` : ""}
                    </div>
                    <div className="muted">
                      {formatTimestamp(alert.event_time)}
                      {alert.price != null ? ` · ${formatUsd(alert.price)}` : ""}
                    </div>
                  </li>
                ))}
                {recentAlerts.length === 0 ? <li className="muted">No recent TradingView alerts recorded.</li> : null}
              </ul>
            </article>
          </div>

          <div className="grid split page-section">
            <article className="card">
              <h2>Execution timeline</h2>
              <ul className="list">
                {dashboardResult.data.dashboard.recent_execution_events.slice(0, 6).map((event) => (
                  <li key={event.id}>
                    <strong>{event.symbol ?? focusSymbol}</strong>
                    <div className="muted">{event.event_type ?? "execution event"} · {event.status}</div>
                    <div className="muted">{formatTimestamp(event.created_at)}</div>
                  </li>
                ))}
                {dashboardResult.data.dashboard.recent_execution_events.length === 0 ? <li className="muted">No execution events available.</li> : null}
              </ul>
            </article>

            <article className="card">
              <h2>Failures & notifications</h2>
              <ul className="list">
                {dashboardResult.data.dashboard.recent_failures.slice(0, 3).map((failure) => (
                  <li key={failure.id}>
                    <strong>{failure.error_type || "UnknownError"}</strong>
                    <div className="muted">{failure.error_message || "No message"}</div>
                  </li>
                ))}
                {dashboardResult.data.dashboard.recent_notifications.slice(0, 3).map((notification) => (
                  <li key={notification.id}>
                    <strong>{notification.channel ?? "Notification"}</strong>
                    <div className="muted">{notification.detail ?? "Delivery recorded"} · {formatTimestamp(notification.sent_time)}</div>
                  </li>
                ))}
                {dashboardResult.data.dashboard.recent_failures.length === 0 && dashboardResult.data.dashboard.recent_notifications.length === 0 ? (
                  <li className="muted">No failures or notifications recorded.</li>
                ) : null}
              </ul>
            </article>
          </div>
        </div>

        <aside className="mission-rail">
          <article className="card">
            <h2>Runtime posture</h2>
            <ul className="list">
              <li>
                <strong>Execution mode</strong>
                <div className="muted">{executionResult.data.execution.trading_mode ?? "paper"}</div>
              </li>
              <li>
                <strong>Exchange</strong>
                <div className="muted">{executionResult.data.execution.exchange}</div>
              </li>
              <li>
                <strong>Configured</strong>
                <div className="muted">{executionResult.data.execution.configured ? "yes" : "paper-prep only"}</div>
              </li>
              <li>
                <strong>Kill switch</strong>
                <div className="muted">{killSwitchState.active ? "active" : "inactive"}</div>
              </li>
            </ul>
          </article>

          <article className="card">
            <h2>Workflow monitor</h2>
            <ul className="list">
              {workflowResult.data.workflow_runs.slice(0, 6).map((run) => (
                <li key={run.id}>
                  <strong>{run.workflow_name}</strong>
                  <div className="muted">{run.status} · {formatTimestamp(run.created_at)}</div>
                </li>
              ))}
              {workflowResult.data.workflow_runs.length === 0 ? <li className="muted">No workflow runs available.</li> : null}
            </ul>
          </article>

          <article className="card">
            <h2>Risk watch</h2>
            <ul className="list">
              {riskResult.data.risk.recent_risk_rejections.slice(0, 5).map((rejection) => (
                <li key={rejection.id}>
                  <strong>{rejection.agent_name}</strong>
                  <div className="muted">{rejection.decision || rejection.status} · {formatTimestamp(rejection.created_at)}</div>
                </li>
              ))}
              {riskResult.data.risk.recent_risk_rejections.length === 0 ? <li className="muted">No recent risk rejections recorded.</li> : null}
            </ul>
          </article>

          <article className="card">
            <h2>Mission Control notes</h2>
            <ul className="list">
              <li>Surface system state and agent activity.</li>
              <li>Present trade proposals and approval queues.</li>
              <li>Route notifications and exception alerts.</li>
              <li>Keep human override paths explicit and auditable.</li>
            </ul>
          </article>
        </aside>
      </div>
    </section>
  );
}
