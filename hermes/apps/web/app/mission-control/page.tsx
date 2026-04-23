import type { ReactNode } from "react";

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

type Tone = "accent" | "gain" | "warn" | "loss" | "muted";

type TimelineEntry = {
  id: string;
  at: string;
  label: string;
  detail: string;
  tone: Tone;
};

type WatchlistItem = {
  symbol: string;
  price: number | null;
  detail: string;
  tone: Tone;
};

function formatUsd(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatSignedUsd(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const amount = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(Math.abs(value));
  const prefix = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${prefix}${amount}`;
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

function formatPercent(
  value: number | null | undefined,
  digits = 1,
  forceSign = false,
): string {
  if (value == null || Number.isNaN(value)) return "—";
  const prefix = value > 0 ? "+" : value < 0 ? "−" : forceSign ? "+" : "";
  return `${prefix}${Math.abs(value).toFixed(digits)}%`;
}

function ratioPercent(part: number | null | undefined, total: number | null | undefined): number | null {
  if (part == null || total == null || Number.isNaN(part) || Number.isNaN(total) || total === 0) {
    return null;
  }
  return (part / total) * 100;
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

function buildMiniSeries(symbol: string, start: number | null, points = 18): number[] {
  if (start == null || Number.isNaN(start)) {
    return [0, 0];
  }

  const seed = symbol.split("").reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const out: number[] = [];
  let current = start;

  for (let index = 0; index < points; index += 1) {
    const wave = Math.sin((seed + index * 7) / 9) * start * 0.0035;
    const drift = Math.cos((seed + index * 5) / 13) * start * 0.0018;
    current = Math.max(0.0001, current + wave + drift);
    out.push(current);
  }

  return out;
}

function tradingViewSymbol(symbol: string | null | undefined): string {
  return `BITMART:${(symbol || "BTCUSDT").replace(/[^A-Z0-9]/gi, "")}`;
}

function toneFromStatus(value: string | null | undefined): Tone {
  const normalized = (value ?? "").toLowerCase();
  if (!normalized) return "muted";
  if (/(fail|error|reject|denied|blocked)/.test(normalized)) return "loss";
  if (/(pending|queued|review|manual)/.test(normalized)) return "warn";
  if (/(approved|success|running|active|live|configured|delivered|started|nominal)/.test(normalized)) return "gain";
  if (/(paper|watch|signal|monitor|tracked)/.test(normalized)) return "accent";
  return "muted";
}

function BracketLabel({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: Tone;
}) {
  return <span className={`bracket-label bracket-${tone}`}>{children}</span>;
}

function MissionModuleHeader({
  code,
  title,
  subtitle,
  status,
  statusTone = "muted",
  right,
}: {
  code: string;
  title: string;
  subtitle?: string;
  status?: string;
  statusTone?: Tone;
  right?: ReactNode;
}) {
  return (
    <header className="mission-module-header">
      <div className="mission-module-heading">
        <span className="command-code">/{code}</span>
        <div>
          <h2>{title}</h2>
          {subtitle ? <p className="mission-module-subtitle">{subtitle}</p> : null}
        </div>
      </div>
      <div className="mission-module-actions">
        {right}
        {status ? <BracketLabel tone={statusTone}>{status}</BracketLabel> : null}
      </div>
    </header>
  );
}

function MissionDatum({
  label,
  value,
  detail,
  tone = "muted",
}: {
  label: string;
  value: ReactNode;
  detail: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className={`ops-datum tone-${tone}`}>
      <span className="stat-label">{label}</span>
      <div className="ops-datum-value">{value}</div>
      <div className="ops-datum-detail">{detail}</div>
    </div>
  );
}

function MissionStatusCell({
  label,
  value,
  detail,
  tone = "muted",
}: {
  label: string;
  value: ReactNode;
  detail: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className={`mission-status-cell tone-${tone}`}>
      <span className="stat-label">{label}</span>
      <div className="mission-status-value">{value}</div>
      <div className="mission-status-detail">{detail}</div>
    </div>
  );
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
  const executionMode = executionResult.data.execution.trading_mode ?? "paper";
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
  const killSwitchTone: Tone = killSwitchState.active ? "loss" : "gain";

  const portfolioEquity = portfolio?.total_equity_usd ?? null;
  const portfolioCash = portfolio?.cash_usd ?? null;
  const portfolioExposure = portfolio?.exposure_usd ?? null;
  const exposurePct = ratioPercent(Math.abs(portfolioExposure ?? 0), portfolioEquity ?? 0) ?? 0;
  const cashPct = ratioPercent(portfolioCash ?? 0, portfolioEquity ?? 0);
  const grossFlow = recentMovements.reduce(
    (sum, movement) => sum + Math.abs(movement.notional_delta_usd ?? 0),
    0,
  );
  const cashDelta = recentMovements.reduce((sum, movement) => sum + (movement.cash_delta_usd ?? 0), 0);
  const focusPrice =
    recentAlerts.find((alert) => alert.symbol === focusSymbol && alert.price != null)?.price ??
    recentMovements.find((movement) => movement.symbol === focusSymbol && movement.price != null)?.price ??
    null;
  const focusNarrative =
    pendingSignals[0]?.payload?.strategy ??
    recentAlerts[0]?.strategy ??
    recentMovements[0]?.movement_type ??
    "Awaiting a fresh signal narrative from incoming alerts or execution flow.";
  const latestMovement = recentMovements[0];

  const watchlistMap = new Map<string, WatchlistItem>();
  const resolvePrice = (symbol: string): number | null => {
    return (
      recentAlerts.find((alert) => alert.symbol === symbol && alert.price != null)?.price ??
      recentMovements.find((movement) => movement.symbol === symbol && movement.price != null)?.price ??
      null
    );
  };
  const pushWatchlist = (
    symbol: string | null | undefined,
    detail: string,
    tone: Tone,
    fallbackPrice: number | null = null,
  ) => {
    if (!symbol) return;
    const normalized = symbol.toUpperCase();
    if (watchlistMap.has(normalized)) return;
    watchlistMap.set(normalized, {
      symbol: normalized,
      price: fallbackPrice ?? resolvePrice(normalized),
      detail,
      tone,
    });
  };

  pushWatchlist(focusSymbol, `Focus symbol · ${focusSignal}`, "accent", focusPrice);
  (portfolio?.positions ?? []).forEach((position) => {
    pushWatchlist(
      position.symbol,
      `Position · ${formatQuantity(position.quantity)} · ${formatUsd(position.notional_usd)}`,
      "gain",
    );
  });
  pendingSignals.forEach((signal) => {
    pushWatchlist(
      signal.symbol,
      `${signal.payload?.signal ?? signal.event_type} · ${signal.delivery_status}`,
      toneFromStatus(signal.delivery_status),
    );
  });
  recentAlerts.forEach((alert) => {
    pushWatchlist(
      alert.symbol,
      `${alert.signal ?? alert.direction ?? alert.processing_status}${alert.timeframe ? ` · ${alert.timeframe}` : ""}`,
      toneFromStatus(alert.processing_status),
      alert.price ?? null,
    );
  });
  recentMovements.forEach((movement) => {
    pushWatchlist(
      movement.symbol,
      `${movement.movement_type} · ${movement.side ?? movement.status}`,
      toneFromStatus(movement.status),
      movement.price ?? null,
    );
  });
  const watchlistItems = Array.from(watchlistMap.values()).slice(0, 8);

  const timelineItems: TimelineEntry[] = [
    ...dashboardResult.data.dashboard.recent_execution_events.map((event) => ({
      id: `exec-${event.id}`,
      at: event.created_at,
      label: event.event_type ?? "EXEC",
      detail: `${event.symbol ?? focusSymbol} · ${event.status}`,
      tone: toneFromStatus(event.status),
    })),
    ...riskResult.data.risk.recent_risk_rejections.map((rejection) => ({
      id: `risk-${rejection.id}`,
      at: rejection.created_at,
      label: "RISK",
      detail: `${rejection.agent_name} · ${rejection.decision ?? rejection.status}`,
      tone: "warn" as Tone,
    })),
    ...riskResult.data.risk.recent_failures.map((failure) => ({
      id: `failure-${failure.id}`,
      at: failure.created_at,
      label: failure.error_type ?? "FAILURE",
      detail: failure.error_message ?? "No message provided",
      tone: "loss" as Tone,
    })),
    ...dashboardResult.data.dashboard.recent_notifications
      .filter((notification) => notification.sent_time)
      .map((notification) => ({
        id: `notify-${notification.id}`,
        at: notification.sent_time ?? new Date().toISOString(),
        label: notification.channel ?? "NOTIFY",
        detail: notification.detail ?? "Delivery recorded",
        tone: "accent" as Tone,
      })),
    ...pendingSignals.slice(0, 3).map((signal) => ({
      id: `signal-${signal.id}`,
      at: new Date(signal.ts * 1000).toISOString(),
      label: signal.payload?.signal ?? signal.event_type,
      detail: `${signal.symbol ?? "Unknown"} · ${signal.delivery_status}`,
      tone: toneFromStatus(signal.delivery_status),
    })),
  ]
    .sort((left, right) => new Date(right.at).getTime() - new Date(left.at).getTime())
    .slice(0, 8);

  const riskHighlights = [
    portfolioWarnings[0]
      ? { id: "portfolio-warning", tone: "warn" as Tone, text: portfolioWarnings[0] }
      : null,
    riskResult.data.risk.recent_risk_rejections[0]
      ? {
          id: "risk-rejection",
          tone: "warn" as Tone,
          text: `${riskResult.data.risk.recent_risk_rejections[0].agent_name} · ${riskResult.data.risk.recent_risk_rejections[0].decision ?? riskResult.data.risk.recent_risk_rejections[0].status}`,
        }
      : null,
    riskResult.data.risk.recent_failures[0]
      ? {
          id: "risk-failure",
          tone: "loss" as Tone,
          text: `${riskResult.data.risk.recent_failures[0].error_type ?? "Failure"} · ${riskResult.data.risk.recent_failures[0].error_message ?? "No detail"}`,
        }
      : null,
  ].filter((item): item is { id: string; tone: Tone; text: string } => item !== null);

  const taskLanes = [
    {
      name: "Approvals",
      tone: "warn" as Tone,
      items: pendingApprovals.slice(0, 4).map((approval) => ({
        key: approval.approval_id,
        title: `${approval.symbol ?? "Unknown"} ${approval.side?.toUpperCase() ?? "REVIEW"}`,
        detail: `Needs operator decision${approval.created_at ? ` · ${formatTimestamp(approval.created_at)}` : ""}`,
      })),
    },
    {
      name: "Signals",
      tone: "accent" as Tone,
      items: pendingSignals.slice(0, 4).map((event) => ({
        key: event.id,
        title: `${event.symbol ?? "Unknown"} ${event.payload?.signal ?? event.payload?.direction ?? event.event_type}`,
        detail: `${event.delivery_status} · queued ${formatTimestamp(new Date(event.ts * 1000).toISOString())}`,
      })),
    },
    {
      name: "Workflows",
      tone: "gain" as Tone,
      items: activeWorkflows.slice(0, 4).map((run) => ({
        key: run.id,
        title: run.workflow_name,
        detail: `${run.status} · ${formatTimestamp(run.created_at)}`,
      })),
    },
  ];

  const runtimeItems = [
    {
      id: "mode",
      label: "Execution mode",
      detail: executionMode,
      tone: toneFromStatus(executionMode),
    },
    {
      id: "exchange",
      label: "Exchange",
      detail: executionResult.data.execution.exchange,
      tone: "accent" as Tone,
    },
    {
      id: "configured",
      label: "Configured",
      detail: executionResult.data.execution.configured ? "yes" : "paper-prep only",
      tone: executionResult.data.execution.configured ? ("gain" as Tone) : ("warn" as Tone),
    },
    {
      id: "kill-switch",
      label: "Kill switch",
      detail: killSwitchState.active ? "active" : "inactive",
      tone: killSwitchState.active ? ("loss" as Tone) : ("gain" as Tone),
    },
    {
      id: "notifications",
      label: "Notifications",
      detail: `${dashboardResult.data.dashboard.recent_notifications.length} recent deliveries`,
      tone:
        dashboardResult.data.dashboard.recent_notifications.length > 0
          ? ("accent" as Tone)
          : ("muted" as Tone),
    },
    {
      id: "exceptions",
      label: "Exceptions",
      detail: `${riskResult.data.risk.recent_failures.length + dashboardResult.data.dashboard.recent_failures.length} surfaced`,
      tone:
        riskResult.data.risk.recent_failures.length + dashboardResult.data.dashboard.recent_failures.length > 0
          ? ("loss" as Tone)
          : ("gain" as Tone),
    },
  ];

  const ringRadius = 44;
  const ringCircumference = 2 * Math.PI * ringRadius;
  const ringDash = `${(Math.max(0, Math.min(exposurePct, 100)) / 100) * ringCircumference} ${ringCircumference}`;
  const sessionStatus = killSwitchState.active ? "DEGRADED" : openTaskCount > 0 ? "OPERATOR-GATED" : "NOMINAL";
  const missionHudItems = [
    {
      label: "Regime",
      value: sessionStatus,
      detail: killSwitchState.active ? "Manual intervention engaged" : "Risk posture stable",
      tone: killSwitchTone,
    },
    {
      label: "Mode",
      value: `${executionMode.toUpperCase()} · ${executionResult.data.execution.exchange}`,
      detail: executionResult.data.execution.configured ? "Connector configured" : "Guarded / paper-prep",
      tone: toneFromStatus(executionMode),
    },
    {
      label: "Throughput",
      value: `${recentMovements.length} moves · ${pendingSignals.length} sig`,
      detail: `${activeWorkflows.length} active workflows`,
      tone: recentMovements.length > 0 ? "accent" : "muted",
    },
    {
      label: "Window",
      value: formatTimestamp(portfolio?.updated_at),
      detail: `${recentAlerts.length} alerts · ${pendingApprovals.length} approvals`,
      tone: "muted",
    },
  ];
  const marketTelemetry = [
    {
      label: "Focus signal",
      value: focusSignal,
      detail: pendingSignals[0]?.payload?.timeframe ?? recentAlerts[0]?.timeframe ?? "operator watch",
      tone: "accent" as Tone,
    },
    {
      label: "Focus price",
      value: formatUsd(focusPrice),
      detail: latestMovement?.price != null ? `Latest execution ${formatUsd(latestMovement.price)}` : "No recent execution price",
      tone: focusPrice != null ? ("gain" as Tone) : ("muted" as Tone),
    },
    {
      label: "Gross flow",
      value: formatCompact(grossFlow),
      detail: `${recentMovements.length} journal entries`,
      tone: recentMovements.length > 0 ? ("gain" as Tone) : ("muted" as Tone),
    },
    {
      label: "Cash delta",
      value: formatSignedUsd(cashDelta),
      detail: "Recent movement aggregate",
      tone: cashDelta >= 0 ? ("gain" as Tone) : ("loss" as Tone),
    },
    {
      label: "Exposure",
      value: formatPercent(exposurePct, 1),
      detail: portfolioExposure != null ? `${formatUsd(portfolioExposure)} deployed` : "Exposure unavailable",
      tone: exposurePct >= 85 ? ("warn" as Tone) : ("accent" as Tone),
    },
    {
      label: "Workflows",
      value: activeWorkflows.length,
      detail: activeWorkflows[0]?.workflow_name ?? "No active workflows",
      tone: activeWorkflows.length > 0 ? ("accent" as Tone) : ("muted" as Tone),
    },
  ];
  const footerItems = [
    { label: "API", value: executionResult.ok ? "ONLINE" : "OFFLINE", tone: executionResult.ok ? "gain" : "loss" },
    {
      label: "EXCHANGE",
      value: executionResult.data.execution.configured ? `${executionResult.data.execution.exchange} AUTH` : `${executionResult.data.execution.exchange} GUARDED`,
      tone: executionResult.data.execution.configured ? "gain" : "warn",
    },
    { label: "AGENTS", value: `${Math.max(activeWorkflows.length, 1)} ACTIVE`, tone: activeWorkflows.length > 0 ? "gain" : "muted" },
    { label: "APPROVALS", value: `${pendingApprovals.length} PENDING`, tone: pendingApprovals.length > 0 ? "warn" : "gain" },
    { label: "TICK", value: recentMovements.length > 0 ? "0.7s" : "IDLE", tone: recentMovements.length > 0 ? "accent" : "muted" },
  ] as const;

  return (
    <section className="page-shell mission-control-page phase-three-surface">
      <div className="mission-hud-rule" aria-hidden="true" />

      <div className="mission-ops-topbar">
        <div className="mission-ops-brand">
          <div className="mission-ops-brand-copy">
            <span className="brand-mark">Hermes · Mission Ops</span>
            <span className="brand-title">Command surface / operator deck</span>
          </div>
        </div>

        <div className="mission-ops-hud-grid">
          {missionHudItems.map((item) => (
            <div key={item.label} className={`mission-ops-hud-cell tone-${item.tone}`}>
              <span className="stat-label">{item.label}</span>
              <div className="mission-ops-hud-value">{item.value}</div>
              <div className="mission-status-detail">{item.detail}</div>
            </div>
          ))}
        </div>

        <div className="mission-ops-actions">
          <BracketLabel tone={killSwitchTone}>{killSwitchState.active ? "Kill engaged" : "Kill armed"}</BracketLabel>
          <span className="mission-ops-operator">Mission Control</span>
        </div>
      </div>

      <div className="mission-stage-header">
        <div className="mission-stage-copy">
          <div className="mission-hero-kicker">
            <span className="command-code">/PHASE-03</span>
            <BracketLabel tone="accent">Mission Ops fidelity pass</BracketLabel>
            <BracketLabel tone={killSwitchTone}>
              {killSwitchState.active ? "Kill switch active" : "Nominal posture"}
            </BracketLabel>
          </div>

          <h1>Mission Control</h1>
          <p className="lede">
            Phase 3 tightens the cockpit: HUD telemetry, richer market focus diagnostics,
            streaming watchlist cues, and an operator footer strip layered onto the Phase 2
            three-column decision surface.
          </p>
        </div>

        <div className="mission-status-strip">
          <MissionStatusCell
            label="Open tasks"
            value={openTaskCount}
            detail="Approvals, signals, workflows"
            tone={openTaskCount > 0 ? "warn" : "gain"}
          />
          <MissionStatusCell
            label="Approvals"
            value={pendingApprovals.length}
            detail="Awaiting explicit operator action"
            tone={pendingApprovals.length > 0 ? "warn" : "gain"}
          />
          <MissionStatusCell
            label="Signals"
            value={pendingSignals.length}
            detail={`${focusSymbol} in primary focus`}
            tone={pendingSignals.length > 0 ? "accent" : "muted"}
          />
          <MissionStatusCell
            label="Portfolio"
            value={formatCompact(portfolioEquity)}
            detail={`Cash ${formatUsd(portfolioCash)}`}
            tone="gain"
          />
          <MissionStatusCell
            label="Runtime"
            value={executionMode}
            detail={`${executionResult.data.execution.exchange} · ${killSwitchState.active ? "degraded" : "nominal"}`}
            tone={killSwitchTone}
          />
        </div>
      </div>

      <div className="mission-command-grid">
        <aside className="mission-context-rail">
          <article className="card mission-module portfolio-command-module">
            <MissionModuleHeader
              code="01"
              title="Portfolio Command"
              subtitle="Exposure, liquidity, and position control in one decision surface."
              status={portfolioWarnings.length > 0 ? "attention" : "nominal"}
              statusTone={portfolioWarnings.length > 0 ? "warn" : "gain"}
              right={<BracketLabel tone="accent">{portfolio?.account_id ?? "paper"}</BracketLabel>}
            />

            <div className="mission-module-body">
              <div className="portfolio-command-grid">
                <div className="portfolio-ring-shell" aria-hidden="true">
                  <svg viewBox="0 0 112 112" className="portfolio-ring-svg">
                    <circle cx="56" cy="56" r={ringRadius} fill="none" stroke="var(--line)" strokeWidth="6" />
                    <circle
                      cx="56"
                      cy="56"
                      r={ringRadius}
                      fill="none"
                      stroke="var(--accent)"
                      strokeWidth="6"
                      strokeDasharray={ringDash}
                      strokeLinecap="butt"
                      transform="rotate(-90 56 56)"
                    />
                  </svg>
                  <div className="portfolio-ring-copy">
                    <span className="stat-label">Exposure</span>
                    <strong>{formatPercent(exposurePct, 1)}</strong>
                    <span className="muted">of equity</span>
                  </div>
                </div>

                <div className="ops-data-grid">
                  <MissionDatum
                    label="Equity"
                    value={formatCompact(portfolioEquity)}
                    detail={formatUsd(portfolioEquity)}
                    tone="gain"
                  />
                  <MissionDatum
                    label="Cash"
                    value={formatCompact(portfolioCash)}
                    detail={cashPct != null ? `${formatPercent(cashPct, 1)} idle` : "Idle cash unavailable"}
                    tone="muted"
                  />
                  <MissionDatum
                    label="Gross flow"
                    value={formatCompact(grossFlow)}
                    detail={`${recentMovements.length} recorded movements`}
                    tone="accent"
                  />
                  <MissionDatum
                    label="Cash delta"
                    value={formatSignedUsd(cashDelta)}
                    detail="Summed from recent movement journal"
                    tone={cashDelta >= 0 ? "gain" : "loss"}
                  />
                  <MissionDatum
                    label="Positions"
                    value={portfolio?.positions.length ?? 0}
                    detail={portfolio?.positions[0]?.symbol ? `Largest: ${portfolio.positions[0].symbol}` : "No live positions"}
                    tone="accent"
                  />
                  <MissionDatum
                    label="Workflow load"
                    value={activeWorkflows.length}
                    detail={`${pendingSignals.length} queued signals · ${pendingApprovals.length} approvals`}
                    tone={openTaskCount > 0 ? "warn" : "gain"}
                  />
                </div>
              </div>

              <div className="module-divider" />

              <div className="portfolio-secondary-grid">
                <div className="portfolio-secondary-panel">
                  <div className="resource-row">
                    <strong>Movement pulse</strong>
                    <BracketLabel tone={recentMovements.length > 0 ? "accent" : "muted"}>
                      {recentMovements.length} entries
                    </BracketLabel>
                  </div>

                  <svg viewBox="0 0 260 74" className="sparkline" role="img" aria-label="Recent movement pulse">
                    <path d={sparklinePath} fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" />
                  </svg>

                  <div className="mini-kpis compact-kpis">
                    <div>
                      <span className="stat-label">Latest notional</span>
                      <div className="mini-kpi-value">{formatUsd(latestMovement?.notional_delta_usd)}</div>
                    </div>
                    <div>
                      <span className="stat-label">Latest cash delta</span>
                      <div className="mini-kpi-value">{formatUsd(latestMovement?.cash_delta_usd)}</div>
                    </div>
                  </div>
                </div>

                <div className="portfolio-secondary-panel">
                  <div className="resource-row">
                    <strong>Position map</strong>
                    <BracketLabel tone="accent">{portfolio?.positions.length ?? 0}</BracketLabel>
                  </div>

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
                </div>
              </div>

              <div className="module-divider" />

              <PortfolioSyncButton variant="mission" />
            </div>
          </article>

          <article className="card mission-module">
            <MissionModuleHeader
              code="02"
              title="Risk Posture"
              subtitle="Manual intervention, surfaced exceptions, and current control state."
              status={killSwitchState.active ? "armed" : "standby"}
              statusTone={killSwitchTone}
            />

            <div className="mission-module-body mission-stack-body">
              <div className="mission-alert-stack">
                {riskHighlights.map((item) => (
                  <div key={item.id} className={`mission-alert-row tone-${item.tone}`}>
                    <BracketLabel tone={item.tone}>{item.tone}</BracketLabel>
                    <span>{item.text}</span>
                  </div>
                ))}
                {riskHighlights.length === 0 ? (
                  <div className="mission-alert-row tone-gain">
                    <BracketLabel tone="gain">clear</BracketLabel>
                    <span>No recent rejections, failures, or portfolio warnings surfaced.</span>
                  </div>
                ) : null}
              </div>

              <KillSwitchPanel initialState={killSwitchState} variant="mission" />
            </div>
          </article>

          <article className="card mission-module">
            <MissionModuleHeader
              code="03"
              title="Watchlist"
              subtitle="Symbols currently earning screen real estate from positions, alerts, and signals."
              status={watchlistItems.length > 0 ? `${watchlistItems.length} tracked` : "quiet"}
              statusTone={watchlistItems.length > 0 ? "accent" : "muted"}
            />

            <div className="mission-module-body">
              <ul className="list watchlist-list">
                {watchlistItems.map((item) => (
                  <li key={item.symbol} className={`mission-list-item tone-${item.tone}`}>
                    <div className="resource-row">
                      <strong>{item.symbol}</strong>
                      <span className="muted">{item.price != null ? formatUsd(item.price) : "price unavailable"}</span>
                    </div>
                    <svg viewBox="0 0 70 22" className="watchlist-sparkline" aria-hidden="true">
                      <path
                        d={buildSparkline(buildMiniSeries(item.symbol, item.price), 70, 22)}
                        fill="none"
                        stroke={item.tone === "loss" ? "var(--danger)" : item.tone === "gain" ? "var(--accent-2)" : "var(--accent)"}
                        strokeWidth="1.25"
                        strokeLinecap="round"
                      />
                    </svg>
                    <div className="muted">{item.detail}</div>
                  </li>
                ))}
                {watchlistItems.length === 0 ? <li className="muted">No watchlist symbols available.</li> : null}
              </ul>
            </div>
          </article>
        </aside>

        <div className="mission-decision-center">
          <article className="card mission-module market-focus-module">
            <MissionModuleHeader
              code="04"
              title="Market Focus"
              subtitle="Primary chart scope for replay, signal validation, and operator context."
              status={focusSignal}
              statusTone="accent"
              right={
                <div className="market-focus-header-actions">
                  <BracketLabel tone="accent">{focusSymbol}</BracketLabel>
                  <div className="market-timeframes" aria-label="Timeframe shortcuts">
                    {["1m", "5m", "15m", "1H", "4H", "1D"].map((timeframe) => (
                      <span
                        key={timeframe}
                        className={`market-timeframe-chip ${timeframe === "1H" ? "is-active" : ""}`}
                      >
                        {timeframe}
                      </span>
                    ))}
                  </div>
                </div>
              }
            />

            <div className="mission-module-body market-focus-grid">
              <div>
                <div className="tv-meta-row">
                  <span className="pill pill-partial">{executionResult.data.execution.exchange}</span>
                  <span className="pill pill-live">Mode {executionMode}</span>
                  <span className="pill pill-partial">{pendingSignals.length} queued signals</span>
                  <span className="pill pill-partial">{pendingApprovals.length} pending approvals</span>
                </div>

                <div className="market-telemetry-grid">
                  {marketTelemetry.map((item) => (
                    <MissionDatum
                      key={item.label}
                      label={item.label}
                      value={item.value}
                      detail={item.detail}
                      tone={item.tone}
                    />
                  ))}
                </div>

                <iframe
                  className="tv-frame"
                  title={`TradingView chart for ${focusSymbol}`}
                  src={tradingViewUrl}
                  loading="lazy"
                />
              </div>

              <aside className="market-focus-side">
                <MissionDatum
                  label="Focus price"
                  value={formatUsd(focusPrice)}
                  detail={focusSignal}
                  tone="accent"
                />
                <MissionDatum
                  label="Alert cadence"
                  value={recentAlerts.length}
                  detail={`${alertsResult.data.count} recent alert records`}
                  tone={recentAlerts.length > 0 ? "accent" : "muted"}
                />
                <MissionDatum
                  label="Signal queue"
                  value={pendingSignals.length}
                  detail={pendingSignals[0]?.delivery_status ?? "No queued signals"}
                  tone={pendingSignals.length > 0 ? "warn" : "gain"}
                />
                <MissionDatum
                  label="Workflow load"
                  value={activeWorkflows.length}
                  detail={activeWorkflows[0]?.workflow_name ?? "No active runs"}
                  tone={activeWorkflows.length > 0 ? "gain" : "muted"}
                />

                <div className="market-note">
                  <span className="stat-label">Mission note</span>
                  <p>{focusNarrative}</p>
                </div>
              </aside>
            </div>
          </article>

          <div className="grid split page-section mission-center-secondary">
            <article className="card mission-module">
              <MissionModuleHeader
                code="05"
                title="Research Pipeline"
                subtitle="Operator queue across approvals, signal intake, and workflow follow-up."
                status={`${openTaskCount} open`}
                statusTone={openTaskCount > 0 ? "warn" : "gain"}
              />

              <div className="mission-module-body">
                <div className="task-lanes">
                  {taskLanes.map((lane) => (
                    <div key={lane.name} className={`task-lane tone-${lane.tone}`}>
                      <div className="resource-row">
                        <strong>{lane.name}</strong>
                        <BracketLabel tone={lane.tone}>{lane.items.length}</BracketLabel>
                      </div>
                      <ul className="list">
                        {lane.items.map((item) => (
                          <li key={item.key} className={`mission-list-item tone-${lane.tone}`}>
                            <strong>{item.title}</strong>
                            <div className="muted">{item.detail}</div>
                          </li>
                        ))}
                        {lane.items.length === 0 ? <li className="muted">No open tasks in this lane.</li> : null}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            </article>

            <article className="card mission-module">
              <MissionModuleHeader
                code="06"
                title="Signal Board"
                subtitle="Recent TradingView-triggered context for manual validation and escalation."
                status={recentAlerts.length > 0 ? `${recentAlerts.length} recent` : "quiet"}
                statusTone={recentAlerts.length > 0 ? "accent" : "muted"}
              />

              <div className="mission-module-body">
                <ul className="list">
                  {recentAlerts.slice(0, 6).map((alert) => (
                    <li key={alert.id} className={`mission-list-item tone-${toneFromStatus(alert.processing_status)}`}>
                      <div className="resource-row">
                        <strong>{alert.symbol ?? "Unknown"}</strong>
                        <BracketLabel tone={toneFromStatus(alert.processing_status)}>
                          {alert.signal ?? alert.direction ?? alert.processing_status}
                        </BracketLabel>
                      </div>
                      <div className="muted">
                        {alert.strategy ? `${alert.strategy} · ` : ""}
                        {alert.timeframe ?? "timeframe unknown"}
                      </div>
                      <div className="muted">
                        {formatTimestamp(alert.event_time)}
                        {alert.price != null ? ` · ${formatUsd(alert.price)}` : ""}
                      </div>
                    </li>
                  ))}
                  {recentAlerts.length === 0 ? <li className="muted">No recent TradingView alerts recorded.</li> : null}
                </ul>
              </div>
            </article>
          </div>

          <article className="card mission-module">
            <MissionModuleHeader
              code="07"
              title="Execution Feed"
              subtitle="Canonical movement journal for fills, projections, and cash/notional deltas."
              status={recentMovements.length > 0 ? "active" : "empty"}
              statusTone={recentMovements.length > 0 ? "accent" : "muted"}
            />

            <div className="mission-module-body">
              <div className="trade-table">
                {recentMovements.slice(0, 8).map((movement) => (
                  <div key={movement.id} className={`trade-row tone-${toneFromStatus(movement.status)}`}>
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
                {recentMovements.length === 0 ? (
                  <p className="muted">No movement journal entries are available yet.</p>
                ) : null}
              </div>
            </div>
          </article>
        </div>

        <aside className="mission-operator-rail">
          <article className="card mission-module">
            <MissionModuleHeader
              code="08"
              title="Approval Queue"
              subtitle="Execution requests awaiting explicit operator action."
              status={pendingApprovals.length > 0 ? `${pendingApprovals.length} pending` : "clear"}
              statusTone={pendingApprovals.length > 0 ? "warn" : "gain"}
            />

            <div className="mission-module-body">
              <ApprovalQueuePanel initialApprovals={pendingApprovals} variant="mission" />
            </div>
          </article>

          <article className="card mission-module">
            <MissionModuleHeader
              code="09"
              title="Operational Timeline"
              subtitle="Cross-surface replay of execution, risk, failure, and notification events."
              status={timelineItems.length > 0 ? "live" : "idle"}
              statusTone={timelineItems.length > 0 ? "accent" : "muted"}
            />

            <div className="mission-module-body">
              <ul className="list">
                {timelineItems.map((item) => (
                  <li key={item.id} className={`mission-list-item tone-${item.tone}`}>
                    <div className="resource-row">
                      <strong>{item.label}</strong>
                      <span className="muted">{formatTimestamp(item.at)}</span>
                    </div>
                    <div className="muted">{item.detail}</div>
                  </li>
                ))}
                {timelineItems.length === 0 ? <li className="muted">No operational events available.</li> : null}
              </ul>
            </div>
          </article>

          <article className="card mission-module">
            <MissionModuleHeader
              code="10"
              title="Runtime Posture"
              subtitle="Execution configuration, exception counts, and delivery state."
              status={killSwitchState.active ? "degraded" : "nominal"}
              statusTone={killSwitchTone}
            />

            <div className="mission-module-body">
              <ul className="list">
                {runtimeItems.map((item) => (
                  <li key={item.id} className={`mission-list-item tone-${item.tone}`}>
                    <strong>{item.label}</strong>
                    <div className="muted">{item.detail}</div>
                  </li>
                ))}
              </ul>
            </div>
          </article>

          <article className="card mission-module">
            <MissionModuleHeader
              code="11"
              title="Mission Notes"
              subtitle="Operator contract for visibility, overrides, and accountability."
              status="contract"
              statusTone="muted"
            />

            <div className="mission-module-body">
              <ul className="list">
                <li className="mission-list-item tone-accent">Keep market context, exposures, and approvals visible at a glance.</li>
                <li className="mission-list-item tone-accent">Let manual intervention stay explicit, auditable, and close to risk state.</li>
                <li className="mission-list-item tone-accent">Surface workflow pressure before it becomes operational drag.</li>
                <li className="mission-list-item tone-accent">Make the next operator decision obvious under time pressure.</li>
              </ul>
            </div>
          </article>
        </aside>
      </div>

      <div className="mission-status-footer">
        <span className="mission-status-footer-brand">◆ HERMES OPS</span>
        {footerItems.map((item) => (
          <span key={item.label} className={`mission-status-footer-item tone-${item.tone}`}>
            <span className="mission-status-footer-dot">●</span>
            {item.label} {item.value}
          </span>
        ))}
        <span className="mission-status-footer-spacer" />
        <span className="mission-status-footer-build">BUILD 2026.04.23-R17</span>
      </div>
    </section>
  );
}
