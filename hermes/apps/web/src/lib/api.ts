const API_BASE = "/api/v1";

async function fetchApi<T>(path: string, opts?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...opts,
    redirect: "follow",
    headers: {
      "Content-Type": "application/json",
      ...opts?.headers,
    },
  });
  if (!res.ok) {
    if (res.status === 307 || res.status === 308) {
      const location = res.headers.get("location");
      if (location) {
        const retry = await fetch(location, {
          ...opts,
          redirect: "follow",
          headers: { "Content-Type": "application/json", ...opts?.headers },
        });
        if (retry.ok) return retry.json();
      }
    }
    throw new Error(`API ${path}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// Response envelope types matching the real API
interface Envelope<T> {
  status: string;
  [key: string]: unknown;
  // data lives at different keys per endpoint
}

export const api = {
  health: () => fetchApi<{ status: string }>("/healthz"),

  execution: {
    surface: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/execution/");
      const exec = (raw.execution ?? raw) as Record<string, unknown>;
      return {
        exchange: exec.exchange as string ?? "BITMART",
        trading_mode: exec.trading_mode as string ?? "paper",
        safety: exec.safety as Record<string, unknown> ?? {},
        kill_switch_active: exec.kill_switch_active as boolean ?? false,
        pending_signals: exec.pending_signal_events as SignalEvent[] ?? [],
        pending_signal_count: exec.pending_signal_count as number ?? 0,
        recent_events: exec.recent_execution_events as ExecutionEvent[] ?? [],
        live_trading_enabled: exec.live_trading_enabled as boolean ?? false,
      } as ExecutionSurface;
    },
    pendingSignals: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/execution/signals/pending");
      return (raw.events ?? []) as SignalEvent[];
    },
    recentAlerts: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/execution/alerts/recent");
      return (raw.alerts ?? raw.events ?? []) as TvAlert[];
    },
    movements: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/execution/movements");
      return (raw.movements ?? []) as MovementEntry[];
    },
    pendingApprovals: async () => {
      try {
        const raw = await fetchApi<Record<string, unknown>>("/execution/approvals/pending");
        return (raw.approvals ?? raw.data ?? []) as Approval[];
      } catch {
        return [] as Approval[];
      }
    },
    approve: (id: string) =>
      fetchApi(`/execution/approvals/${id}/approve`, { method: "POST" }),
    reject: (id: string) =>
      fetchApi(`/execution/approvals/${id}/reject`, { method: "POST" }),
  },

  risk: {
    dashboard: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/risk/");
      const risk = (raw.risk ?? raw) as Record<string, unknown>;
      const ks = (risk.kill_switch ?? {}) as Record<string, unknown>;
      const safety = (risk.execution_safety ?? {}) as Record<string, unknown>;
      const posMonitor = (risk.position_monitor ?? {}) as Record<string, unknown>;
      const portfolio = (posMonitor.portfolio ?? {}) as Record<string, unknown>;
      const positions = (portfolio.positions ?? []) as PositionSnapshot[];
      return {
        kill_switch: {
          active: ks.active as boolean ?? false,
          reason: ks.reason as string | undefined,
          operator: ks.operator as string | undefined,
          updated_at: ks.updated_at as string | undefined,
        },
        execution_safety: safety,
        positions,
        total_equity_usd: portfolio.total_equity_usd as number ?? 0,
        risk_summary: posMonitor.risk_summary as Record<string, unknown> ?? {},
      } as RiskDashboard;
    },
    killSwitch: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/risk/kill-switch");
      const ks = (raw.kill_switch ?? raw) as Record<string, unknown>;
      return {
        active: ks.active as boolean ?? false,
        reason: ks.reason as string | undefined,
        operator: ks.operator as string | undefined,
        updated_at: ks.updated_at as string | undefined,
      } as KillSwitchState;
    },
    activateKillSwitch: (reason: string) =>
      fetchApi("/risk/kill-switch/activate", {
        method: "POST",
        body: JSON.stringify({ reason, operator: "dashboard" }),
      }),
    deactivateKillSwitch: () =>
      fetchApi("/risk/kill-switch/deactivate", {
        method: "POST",
        body: JSON.stringify({ operator: "dashboard" }),
      }),
    rejections: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/risk/rejections");
      return (raw.rejections ?? []) as RiskRejection[];
    },
    candidates: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/risk/candidates");
      const result = (raw.result ?? raw) as Record<string, unknown>;
      return (result.data ?? []) as TradeCandidateScore[];
    },
  },

  portfolio: {
    state: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/portfolio/");
      const port = (raw.portfolio ?? raw) as Record<string, unknown>;
      const data = (port.data ?? port) as Record<string, unknown>;
      return {
        account_id: data.account_id as string ?? "paper",
        total_equity_usd: data.total_equity_usd as number ?? 0,
        available_balance_usd: data.cash_usd as number ?? 0,
        exposure_usd: data.exposure_usd as number ?? 0,
        positions: (data.positions ?? []) as PositionSnapshot[],
        last_sync: data.updated_at as string | undefined,
      } as PortfolioState;
    },
    sync: () => fetchApi("/portfolio/sync", { method: "POST" }),
  },

  agents: {
    list: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/agents/");
      return (raw.agents ?? []) as AgentSummary[];
    },
    detail: (id: string) => fetchApi<AgentDetail>(`/agents/${id}`),
    timeline: (id: string) => fetchApi<TimelineEvent[]>(`/agents/${id}/timeline`),
  },

  observability: {
    dashboard: async () => {
      const raw = await fetchApi<Record<string, unknown>>("/observability/");
      const dash = (raw.dashboard ?? raw) as Record<string, unknown>;
      return {
        recent_workflows: (dash.recent_workflow_runs ?? []) as WorkflowRun[],
        recent_failures: (dash.recent_failures ?? []) as FailureEvent[],
        recent_execution_events: (dash.recent_execution_events ?? []) as ExecutionEvent[],
        recent_movements: (dash.recent_movements ?? []) as MovementEntry[],
        recent_rejections: (dash.recent_risk_rejections ?? []) as RiskRejection[],
      } as ObsDashboard;
    },
    workflows: async () => {
      try {
        const raw = await fetchApi<Record<string, unknown>>("/observability/workflows");
        return (raw.workflows ?? raw.data ?? []) as WorkflowRun[];
      } catch {
        return [] as WorkflowRun[];
      }
    },
    failures: async () => {
      try {
        const raw = await fetchApi<Record<string, unknown>>("/observability/failures");
        return (raw.failures ?? raw.data ?? []) as FailureEvent[];
      } catch {
        return [] as FailureEvent[];
      }
    },
  },
};

// Types
export interface ExecutionSurface {
  exchange: string;
  trading_mode: string;
  safety: Record<string, unknown>;
  kill_switch_active: boolean;
  pending_signals: SignalEvent[];
  pending_signal_count: number;
  recent_events: ExecutionEvent[];
  live_trading_enabled: boolean;
}

export interface SignalEvent {
  id: string;
  symbol: string;
  signal: string;
  direction: string;
  price: number;
  event_time: string;
  processing_status: string;
  [key: string]: unknown;
}

export interface ExecutionEvent {
  id: string;
  event_type: string;
  symbol: string;
  status: string;
  created_at: string;
  [key: string]: unknown;
}

export interface TvAlert {
  id: string;
  symbol: string;
  signal: string;
  direction: string;
  price: number;
  event_time: string;
  [key: string]: unknown;
}

export interface MovementEntry {
  id: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  execution_mode: string;
  movement_time: string;
  [key: string]: unknown;
}

export interface Approval {
  id: string;
  symbol: string;
  side: string;
  amount: number;
  status: string;
  created_at: string;
  [key: string]: unknown;
}

export interface PositionSnapshot {
  symbol: string;
  side: string;
  size: number;
  entry_price: number;
  mark_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  leverage: number;
  [key: string]: unknown;
}

export interface KillSwitchState {
  active: boolean;
  reason?: string;
  operator?: string;
  updated_at?: string;
}

export interface RiskDashboard {
  kill_switch: KillSwitchState;
  execution_safety: Record<string, unknown>;
  positions: PositionSnapshot[];
  total_equity_usd: number;
  risk_summary: Record<string, unknown>;
}

export interface RiskRejection {
  id: string;
  symbol: string;
  reason: string;
  created_at: string;
  [key: string]: unknown;
}

export interface TradeCandidateScore {
  symbol: string;
  strategy_name: string;
  direction: string;
  confidence: number;
  chronos_score?: number;
  rationale?: string;
  strategy_version?: string;
  [key: string]: unknown;
}

export interface PortfolioState {
  account_id: string;
  total_equity_usd: number;
  available_balance_usd: number;
  exposure_usd: number;
  positions: PositionSnapshot[];
  last_sync?: string;
}

export interface AgentSummary {
  name: string;
  canonical_agent_id: string;
  profile: string;
  role: string;
  reports_to: string | null;
  responsibilities: string[];
  allowed_toolsets: string[];
  allowed_tools: string[];
  assigned_skills: string[];
  [key: string]: unknown;
}

export interface AgentDetail extends AgentSummary {
  decisions: AgentDecision[];
  workflows: WorkflowRun[];
}

export interface AgentDecision {
  id: string;
  decision: string;
  status: string;
  created_at: string;
  [key: string]: unknown;
}

export interface TimelineEvent {
  id: string;
  event_type: string;
  timestamp: string;
  details: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ObsDashboard {
  recent_workflows: WorkflowRun[];
  recent_failures: FailureEvent[];
  recent_execution_events: ExecutionEvent[];
  recent_movements: MovementEntry[];
  recent_rejections: RiskRejection[];
}

export interface WorkflowRun {
  id: string;
  workflow_name: string;
  status: string;
  correlation_id: string;
  created_at: string;
  [key: string]: unknown;
}

export interface WorkflowRunDetail extends WorkflowRun {
  steps: WorkflowStep[];
}

export interface WorkflowStep {
  id: string;
  workflow_step: string;
  status: string;
  agent_name: string;
  created_at: string;
  [key: string]: unknown;
}

export interface FailureEvent {
  id: string;
  error_type: string;
  message: string;
  created_at: string;
  [key: string]: unknown;
}
