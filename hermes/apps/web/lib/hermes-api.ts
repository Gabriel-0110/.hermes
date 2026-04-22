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
