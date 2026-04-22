import { fetchHermesApi, formatTimestamp } from "../../lib/hermes-api";
import { KillSwitchPanel } from "../../components/KillSwitchPanel";
import { PortfolioSyncButton } from "../../components/PortfolioSyncButton";
import { ApprovalQueuePanel, type PendingApproval } from "../../components/ApprovalQueuePanel";

type ExecutionSnapshot = {
  status: string;
  execution: {
    exchange: string;
    configured: boolean;
    pending_signal_count: number;
    pending_signal_events: Array<{
      id: string;
      event_type: string;
      symbol: string | null;
      delivery_status: string;
      ts: number;
    }>;
    recent_execution_events: Array<{
      id: string;
      event_type: string;
      status: string;
      created_at: string;
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

export default async function MissionControlPage() {
  const [executionResult, riskResult, workflowResult, portfolioResult, approvalsResult] =
    await Promise.all([
      fetchHermesApi<ExecutionSnapshot>("/execution", {
        fallback: {
          status: "offline",
          execution: {
            exchange: "BITMART",
            configured: false,
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
    fetchHermesApi<WorkflowSnapshot>("/observability/workflows", {
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
  ]);

  const killSwitchState = riskResult.data.risk.kill_switch ?? { active: false };
  const portfolio = portfolioResult.data.portfolio?.data;
  const portfolioWarnings = portfolioResult.data.portfolio?.meta?.warnings ?? [];
  const pendingApprovals = approvalsResult.data.approvals ?? [];

  return (
    <section className="page-shell">
      <div className="hero">
        <p className="eyebrow">Mission Control</p>
        <h1>Human oversight stays in the loop.</h1>
        <p className="lede">
          Live execution queue, workflow history, portfolio state, and risk
          controls — all wired to the backend bridge.
        </p>
      </div>

      {/* ── Operator controls row ──────────────────────────────────────────── */}
      <div className="grid split page-section">
        <KillSwitchPanel initialState={killSwitchState} />

        <article className="card">
          <h2>Portfolio state</h2>
          {portfolioWarnings.length > 0 && (
            <p className="muted" style={{ color: "#dd6b20" }}>
              {portfolioWarnings[0]}
            </p>
          )}
          {portfolio ? (
            <>
              <p>
                <strong>Total equity:</strong>{" "}
                {portfolio.total_equity_usd != null
                  ? `$${portfolio.total_equity_usd.toFixed(2)}`
                  : "Unknown"}
              </p>
              <p className="muted">
                Cash: {portfolio.cash_usd != null ? `$${portfolio.cash_usd.toFixed(2)}` : "—"} ·
                Exposure:{" "}
                {portfolio.exposure_usd != null ? `$${portfolio.exposure_usd.toFixed(2)}` : "—"}
              </p>
              <p className="muted">
                Last sync: {formatTimestamp(portfolio.updated_at)}
              </p>
              {portfolio.positions.length > 0 && (
                <ul className="list" style={{ marginTop: "0.5rem" }}>
                  {portfolio.positions.slice(0, 5).map((p) => (
                    <li key={p.symbol}>
                      <strong>{p.symbol}</strong>
                      <span className="muted">
                        {" "}
                        ·{" "}
                        {p.notional_usd != null ? `$${p.notional_usd.toFixed(2)}` : `${p.quantity}`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : null}
          <PortfolioSyncButton />
        </article>
      </div>

      {/* ── Operator approval queue ────────────────────────────────────────── */}
      <div className="page-section">
        <ApprovalQueuePanel initialApprovals={pendingApprovals} />
      </div>

      {/* ── Execution queue + operating mode ──────────────────────────────── */}
      <div className="grid split page-section">
        <article className="card">
          <h2>Execution queue</h2>
          <ul className="list">
            {executionResult.data.execution.pending_signal_events.slice(0, 5).map((event) => (
              <li key={event.id}>
                <strong>{event.symbol || "Unknown symbol"}</strong>
                <div className="muted">
                  {event.event_type} · {event.delivery_status}
                </div>
              </li>
            ))}
            {executionResult.data.execution.pending_signal_events.length === 0 ? (
              <li>No pending signal events in the execution queue.</li>
            ) : null}
          </ul>
        </article>

        <article className="card">
          <h2>Current operating mode</h2>
          <p className="status">
            {executionResult.data.execution.configured ? "Execution configured" : "Paper-prep only"}
          </p>
          <p className="muted">
            Exchange: {executionResult.data.execution.exchange}
          </p>
          <p className="muted">
            Pending signals: {executionResult.data.execution.pending_signal_count}
          </p>
          <p className="muted">
            Workflow feed: {workflowResult.ok ? "connected" : workflowResult.error}
          </p>
        </article>
      </div>

      {/* ── Workflow runs + risk rejections ───────────────────────────────── */}
      <div className="grid split page-section">
        <article className="card">
          <h2>Recent workflow runs</h2>
          <ul className="list">
            {workflowResult.data.workflow_runs.slice(0, 6).map((run) => (
              <li key={run.id}>
                <strong>{run.workflow_name}</strong>
                <div className="muted">
                  {run.status} · {formatTimestamp(run.created_at)}
                </div>
              </li>
            ))}
            {workflowResult.data.workflow_runs.length === 0 ? (
              <li>No workflow runs available.</li>
            ) : null}
          </ul>
        </article>

        <article className="card">
          <h2>Risk rejections</h2>
          <ul className="list">
            {riskResult.data.risk.recent_risk_rejections.slice(0, 5).map((rejection) => (
              <li key={rejection.id}>
                <strong>{rejection.agent_name}</strong>
                <div className="muted">
                  {rejection.decision || rejection.status} · {formatTimestamp(rejection.created_at)}
                </div>
              </li>
            ))}
            {riskResult.data.risk.recent_risk_rejections.length === 0 ? (
              <li>No recent risk rejections recorded.</li>
            ) : null}
          </ul>
        </article>
      </div>

      {/* ── Execution events + failure watch ──────────────────────────────── */}
      <div className="grid split page-section">
        <article className="card">
          <h2>Recent execution events</h2>
          <ul className="list">
            {executionResult.data.execution.recent_execution_events.slice(0, 5).map((event) => (
              <li key={event.id}>
                <strong>{event.event_type}</strong>
                <div className="muted">
                  {event.status} · {formatTimestamp(event.created_at)}
                </div>
              </li>
            ))}
            {executionResult.data.execution.recent_execution_events.length === 0 ? (
              <li>No execution events available.</li>
            ) : null}
          </ul>
        </article>

        <article className="card">
          <h2>Failure watch</h2>
          <ul className="list">
            {riskResult.data.risk.recent_failures.slice(0, 5).map((failure) => (
              <li key={failure.id}>
                <strong>{failure.error_type || "UnknownError"}</strong>
                <div className="muted">
                  {failure.error_message || "No message"} · {formatTimestamp(failure.created_at)}
                </div>
              </li>
            ))}
            {riskResult.data.risk.recent_failures.length === 0 ? (
              <li>No recent failures recorded.</li>
            ) : null}
          </ul>
        </article>
      </div>
    </section>
  );
}
