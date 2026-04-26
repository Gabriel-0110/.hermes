import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function getApiBaseUrl(): string {
  return (
    process.env.HERMES_API_BASE_URL ||
    process.env.NEXT_PUBLIC_HERMES_API_BASE_URL ||
    "http://localhost:8000/api/v1"
  ).replace(/\/$/, "");
}

async function safeJson<T>(url: string, timeoutMs = 4000): Promise<{ ok: boolean; data: T | null; latency: number; status: number }> {
  const start = Date.now();
  try {
    const res = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    const latency = Date.now() - start;
    if (!res.ok) {
      return { ok: false, data: null, latency, status: res.status };
    }
    const data = (await res.json()) as T;
    return { ok: true, data, latency, status: res.status };
  } catch {
    return { ok: false, data: null, latency: Date.now() - start, status: 0 };
  }
}

async function probe(url: string, timeoutMs = 2500): Promise<{ ok: boolean; latency: number }> {
  const start = Date.now();
  try {
    const res = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(timeoutMs) });
    return { ok: res.ok, latency: Date.now() - start };
  } catch {
    return { ok: false, latency: Date.now() - start };
  }
}

export async function GET() {
  const apiBase = getApiBaseUrl();

  // Internal Docker hostnames for service health
  const internalLitellm = process.env.LITELLM_INTERNAL_URL || "http://litellm:4000/health/liveliness";
  const internalDashboard = process.env.DASHBOARD_INTERNAL_URL || "http://dashboard:9119/api/status";
  const internalRedisProbe = `${apiBase}/healthz`; // API health doubles as redis/db probe via dependency

  const [
    portfolio,
    positionsMonitor,
    killSwitch,
    agents,
    movements,
    riskPortfolio,
    svcApi,
    svcLitellm,
    svcDashboard,
  ] = await Promise.all([
    safeJson<{ status: string; portfolio?: { data?: Record<string, unknown> } }>(`${apiBase}/portfolio/`),
    safeJson<{ status: string; monitor?: Record<string, unknown> }>(`${apiBase}/execution/positions/monitor`),
    safeJson<{ status: string; kill_switch?: { active?: boolean; reason?: string | null; updated_at?: string | null } }>(`${apiBase}/risk/kill-switch`),
    safeJson<{ status: string; count?: number; agents?: Array<{ name: string; role: string }>; trading_mode?: { mode: string } }>(`${apiBase}/agents/`),
    safeJson<{ status: string; movements?: Array<Record<string, unknown>> }>(`${apiBase}/execution/movements?limit=10`),
    safeJson<Record<string, unknown>>(`${apiBase}/risk/portfolio`),
    probe(internalRedisProbe),
    probe(internalLitellm),
    probe(internalDashboard),
  ]);

  return NextResponse.json(
    {
      now: new Date().toISOString(),
      api_base: apiBase,
      services: {
        api: svcApi,
        litellm: svcLitellm,
        dashboard: svcDashboard,
      },
      portfolio: portfolio.data?.portfolio?.data ?? null,
      portfolio_status: portfolio.ok ? portfolio.data?.status ?? "unknown" : "offline",
      monitor: positionsMonitor.data?.monitor ?? null,
      monitor_status: positionsMonitor.ok ? positionsMonitor.data?.status ?? "unknown" : "offline",
      kill_switch: killSwitch.data?.kill_switch ?? null,
      kill_switch_status: killSwitch.ok ? "live" : "offline",
      agents: {
        status: agents.ok ? agents.data?.status ?? "unknown" : "offline",
        count: agents.data?.count ?? 0,
        list: agents.data?.agents ?? [],
        trading_mode: agents.data?.trading_mode?.mode ?? "unknown",
      },
      movements: movements.data?.movements ?? [],
      risk_portfolio_ok: riskPortfolio.ok,
    },
    {
      headers: {
        "Cache-Control": "no-store, no-cache, must-revalidate",
      },
    },
  );
}
