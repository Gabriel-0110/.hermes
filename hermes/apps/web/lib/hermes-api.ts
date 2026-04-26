type ApiFetchOptions = {
  fallback?: unknown;
};

export interface WorkflowRunRecord {
  id: string;
  workflow_name: string;
  status: string;
  created_at: string;
  updated_at?: string | null;
  [key: string]: unknown;
}

export interface SystemErrorRecord {
  id: string;
  workflow_run_id?: string | null;
  error_type?: string | null;
  error_message?: string | null;
  created_at: string;
  [key: string]: unknown;
}

export interface ExecutionEventRecord {
  id: string;
  event_type: string;
  status: string;
  created_at: string;
  [key: string]: unknown;
}

export interface AgentDecisionRecord {
  id: string;
  agent_name: string;
  status: string;
  decision?: string | null;
  created_at: string;
  [key: string]: unknown;
}

export interface NotificationPayload {
  title?: string;
  message?: string;
  notification_type?: string;
  severity?: string;
  [key: string]: unknown;
}

export interface NotificationAuditRecord {
  id: string;
  channel: string | null;
  sent_time: string | null;
  detail?: string | null;
  delivered?: boolean;
  payload?: NotificationPayload;
  [key: string]: unknown;
}

export interface ObservabilityDashboard {
  recent_workflow_runs: WorkflowRunRecord[];
  pending_or_in_progress: WorkflowRunRecord[];
  recent_failures: SystemErrorRecord[];
  recent_execution_events: ExecutionEventRecord[];
  recent_risk_rejections: AgentDecisionRecord[];
  recent_notifications: NotificationAuditRecord[];
}

export interface ObservabilityDashboardResponse {
  status: string;
  dashboard: ObservabilityDashboard;
}

export interface WorkflowRunsResponse {
  status: string;
  count?: number;
  workflow_runs: WorkflowRunRecord[];
}

export interface FailuresResponse {
  status: string;
  count?: number;
  failures: SystemErrorRecord[];
}

// ── Positions & Portfolio ──────────────────────────────────────────────────

export interface PositionState {
  symbol: string;
  side: string;
  qty: number;
  entry_price: number | null;
  mark_price: number | null;
  unrealized_pnl: number | null;
  notional_usd: number | null;
  weight: number | null;
  leverage?: number | null;
  [key: string]: unknown;
}

export interface PortfolioSnapshot {
  account_id: string;
  total_equity_usd: number;
  cash_usd: number;
  exposure_usd: number | null;
  positions: PositionState[];
  updated_at: string | null;
  snapshot_metadata: {
    source: string;
    execution_mode: string;
    exchange: string;
    account_type: string;
    as_of: string;
    positions_count: number;
  } | null;
}

export interface RiskSummary {
  total_positions: number;
  largest_position_symbol: string | null;
  largest_position_notional_usd: number | null;
  largest_position_weight: number | null;
  cash_buffer_pct: number;
  gross_exposure_pct: number | null;
  warnings: string[];
}

export interface PositionMonitorResponse {
  status: string;
  monitor: {
    account_id: string;
    observed_at: string;
    portfolio: PortfolioSnapshot;
    risk_summary: RiskSummary;
    position_states: PositionState[];
    snapshot_metadata: {
      source: string;
      execution_mode: string;
      exchange: string;
      account_type: string;
      as_of: string;
      positions_count: number;
      snapshot_time: string;
      account_id: string;
    } | null;
    state_mode: string;
    last_execution: unknown | null;
    source: string;
  };
}

export interface PortfolioResponse {
  status: string;
  portfolio: {
    meta: {
      ok: boolean;
      warnings: string[];
    };
    data: PortfolioSnapshot;
  };
}

export interface MovementRecord {
  id: string;
  symbol?: string | null;
  side?: string | null;
  notional_usd?: number | null;
  cash_delta_usd?: number | null;
  created_at: string;
  [key: string]: unknown;
}

export interface MovementsResponse {
  status: string;
  count: number;
  movements: MovementRecord[];
}

// ── Kill Switch ────────────────────────────────────────────────────────────

export interface KillSwitchResponse {
  status: string;
  kill_switch: {
    active: boolean;
    reason: string | null;
    operator: string | null;
    updated_at: string | null;
  };
}

// ── Agents ─────────────────────────────────────────────────────────────────

export interface AgentRecord {
  name: string;
  canonical_agent_id: string;
  profile: string;
  role: string;
  allowed_toolsets: string[];
  allowed_tools?: string[];
  assigned_skills?: string[];
  [key: string]: unknown;
}

export interface AgentsResponse {
  status: string;
  team_name: string;
  trading_mode: {
    mode: string;
    execution_base_url?: string;
    enforcement_mode: string;
    live_execution_forbidden?: boolean;
    [key: string]: unknown;
  };
  count: number;
  agents: AgentRecord[];
}

// ── Resources ──────────────────────────────────────────────────────────────

export interface ResourceRecord {
  resource_id: string;
  name: string;
  purpose?: string;
  status: string;
  implemented: boolean;
  installed: boolean;
  tested: boolean;
  running: boolean;
  applied_to_agents: boolean;
  owning_agents?: string[];
  consumer_agents?: string[];
  [key: string]: unknown;
}

export interface ResourcesDetailResponse {
  status: string;
  contract: string;
  contract_version?: string;
  summary: {
    total_resources: number;
    live: number;
    needs_fix: number;
    running: number;
    implemented: number;
    installed: number;
    tested: number;
    applied_to_agents: number;
  };
  resources: ResourceRecord[];
}

const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

function getApiBaseUrl(): string {
  return (
    process.env.HERMES_API_BASE_URL ||
    process.env.NEXT_PUBLIC_HERMES_API_BASE_URL ||
    DEFAULT_API_BASE_URL
  ).replace(/\/$/, "");
}

export async function fetchHermesApi<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<{ data: T; ok: boolean; error: string | null }> {
  const target = `${getApiBaseUrl()}${path}`;

  try {
    const response = await fetch(target, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    if (!response.ok) {
      const detail = await response.text();
      return {
        data: (options.fallback ?? null) as T,
        ok: false,
        error: `HTTP ${response.status}: ${detail || "unknown error"}`,
      };
    }

    return {
      data: (await response.json()) as T,
      ok: true,
      error: null,
    };
  } catch (error) {
    return {
      data: (options.fallback ?? null) as T,
      ok: false,
      error: error instanceof Error ? error.message : "unknown fetch error",
    };
  }
}

/**
 * POST to a Hermes API endpoint with a JSON body.
 * Safe to call from client components.
 */
export async function postHermesApi<T>(
  path: string,
  body: Record<string, unknown> = {},
): Promise<{ data: T | null; ok: boolean; error: string | null }> {
  const target = `${getApiBaseUrl()}${path}`;

  try {
    const response = await fetch(target, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const detail = await response.text();
      return {
        data: null,
        ok: false,
        error: `HTTP ${response.status}: ${detail || "unknown error"}`,
      };
    }

    return {
      data: (await response.json()) as T,
      ok: true,
      error: null,
    };
  } catch (error) {
    return {
      data: null,
      ok: false,
      error: error instanceof Error ? error.message : "unknown fetch error",
    };
  }
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "Unavailable";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function getNotificationTitle(notification: NotificationAuditRecord): string {
  return (
    notification.payload?.title ||
    notification.payload?.notification_type ||
    notification.detail ||
    "—"
  );
}

export function formatUsd(value: number | null | undefined): string {
  if (value == null || isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPct(value: number | null | undefined, decimals = 1): string {
  if (value == null || isNaN(value)) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}
