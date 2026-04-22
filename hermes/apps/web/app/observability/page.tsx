import {
  fetchHermesApi,
  formatTimestamp,
  getNotificationTitle,
  type FailuresResponse,
  type ObservabilityDashboardResponse,
  type WorkflowRunsResponse,
} from "../../lib/hermes-api";

export default async function ObservabilityPage() {
  const [snapshotResult, workflowResult, failuresResult] = await Promise.all([
    fetchHermesApi<ObservabilityDashboardResponse>("/observability/", {
      fallback: {
        status: "offline",
        dashboard: {
          recent_workflow_runs: [],
          pending_or_in_progress: [],
          recent_failures: [],
          recent_execution_events: [],
          recent_risk_rejections: [],
          recent_notifications: [],
        },
      },
    }),
    fetchHermesApi<WorkflowRunsResponse>("/observability/workflows?limit=15", {
      fallback: { status: "offline", workflow_runs: [] },
    }),
    fetchHermesApi<FailuresResponse>("/observability/failures?limit=10", {
      fallback: { status: "offline", failures: [] },
    }),
  ]);

  const dashboard = snapshotResult.data.dashboard;
  const pendingRuns = dashboard.pending_or_in_progress.filter(
    (run) => run.status === "pending" || run.status === "manual_review",
  ).length;
  const runningRuns = dashboard.pending_or_in_progress.filter(
    (run) => run.status === "running" || run.status === "in_progress",
  ).length;

  return (
    <section className="page-shell">
      <div className="hero">
        <p className="eyebrow">Observability</p>
        <h1>End-to-end workflow and system health.</h1>
        <p className="lede">
          Workflow runs, agent decisions, execution events, and system errors —
          wired directly to the backend observability service.
        </p>
      </div>

      {/* ── System health summary ──────────────────────────────────────────── */}
      <div className="grid split page-section">
        <article className="card">
          <h2>System health</h2>
          <p className="status" style={{ color: snapshotResult.ok ? "#38a169" : "#e53e3e" }}>
            {snapshotResult.ok ? "Backend connected" : "Backend offline"}
          </p>
          <ul className="list" style={{ marginTop: "0.5rem" }}>
            <li>
              <strong>Pending runs:</strong>{" "}
              <span className={pendingRuns > 0 ? "" : "muted"}>
                {pendingRuns}
              </span>
            </li>
            <li>
              <strong>Running runs:</strong>{" "}
              <span className={runningRuns > 0 ? "" : "muted"}>
                {runningRuns}
              </span>
            </li>
            <li>
              <strong>Recent failures:</strong>{" "}
              <span
                className={dashboard.recent_failures.length > 0 ? "" : "muted"}
                style={dashboard.recent_failures.length > 0 ? { color: "#e53e3e" } : {}}
              >
                {dashboard.recent_failures.length}
              </span>
            </li>
          </ul>
        </article>

        <article className="card">
          <h2>Recent notifications</h2>
          <ul className="list">
            {dashboard.recent_notifications.slice(0, 5).map((n) => (
              <li key={n.id}>
                <strong>{n.channel ?? "Unknown channel"}</strong>
                <div className="muted">
                  {getNotificationTitle(n)} · {formatTimestamp(n.sent_time)}
                </div>
              </li>
            ))}
            {dashboard.recent_notifications.length === 0 && (
              <li className="muted">No notifications recorded.</li>
            )}
          </ul>
        </article>
      </div>

      {/* ── Workflow runs ──────────────────────────────────────────────────── */}
      <div className="page-section">
        <article className="card">
          <h2>Recent workflow runs</h2>
          {!workflowResult.ok && (
            <p className="muted" style={{ color: "#dd6b20" }}>
              {workflowResult.error}
            </p>
          )}
          <ul className="list">
            {workflowResult.data.workflow_runs.map((run) => (
              <li key={run.id}>
                <strong>{run.workflow_name}</strong>
                <span
                  className="muted"
                  style={
                    run.status === "failed"
                      ? { color: "#e53e3e" }
                      : run.status === "running"
                        ? { color: "#3182ce" }
                        : {}
                  }
                >
                  {" "}· {run.status}
                </span>
                <div className="muted">{formatTimestamp(run.created_at)}</div>
              </li>
            ))}
            {workflowResult.data.workflow_runs.length === 0 && (
              <li className="muted">No workflow runs recorded.</li>
            )}
          </ul>
        </article>
      </div>

      {/* ── Failures + risk rejections ─────────────────────────────────────── */}
      <div className="grid split page-section">
        <article className="card">
          <h2>Recent failures</h2>
          <ul className="list">
            {failuresResult.data.failures.map((f) => (
              <li key={f.id}>
                <strong style={{ color: "#e53e3e" }}>{f.error_type ?? "UnknownError"}</strong>
                <div className="muted">{f.error_message ?? "No message"}</div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  {formatTimestamp(f.created_at)}
                </div>
              </li>
            ))}
            {failuresResult.data.failures.length === 0 && (
              <li className="muted">No recent failures. System is healthy.</li>
            )}
          </ul>
        </article>

        <article className="card">
          <h2>Risk rejections</h2>
          <ul className="list">
            {dashboard.recent_risk_rejections.slice(0, 8).map((r) => (
              <li key={r.id}>
                <strong>{r.agent_name}</strong>
                <div className="muted">
                  {r.decision ?? r.status} · {formatTimestamp(r.created_at)}
                </div>
              </li>
            ))}
            {dashboard.recent_risk_rejections.length === 0 && (
              <li className="muted">No recent risk rejections.</li>
            )}
          </ul>
        </article>
      </div>
    </section>
  );
}
