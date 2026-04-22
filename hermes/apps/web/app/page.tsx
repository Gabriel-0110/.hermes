import {
  fetchHermesApi,
  formatTimestamp,
  type ObservabilityDashboardResponse,
} from "../lib/hermes-api";

type ResourceSnapshot = {
  contract?: string;
  contract_version?: string;
  generated_at?: string;
  status: string;
  summary?: {
    total_resources: number;
    live_resource_count: number;
    status_counts: Record<string, number>;
  };
  resources: Array<{
    name: string;
    status: "live" | "backend_only" | "not_exposed";
    evidence: string;
  }>;
};

const metrics = [
  { label: "Agents active in desk model", value: "5" },
  { label: "Channels in scope", value: "4" },
];

function formatResourceStatus(
  status: ResourceSnapshot["resources"][number]["status"],
): string {
  switch (status) {
    case "live":
      return "live";
    case "backend_only":
      return "backend only";
    case "not_exposed":
      return "not exposed";
  }
}

export default async function HomePage() {
  const [dashboardResult, resourcesResult] = await Promise.all([
    fetchHermesApi<ObservabilityDashboardResponse>("/observability", {
      fallback: {
        status: "offline",
        dashboard: {
          recent_workflow_runs: [],
          pending_or_in_progress: [],
          recent_failures: [],
          recent_execution_events: [],
          recent_notifications: [],
        },
      },
    }),
    fetchHermesApi<ResourceSnapshot>("/resources", {
      fallback: {
        status: "offline",
        contract: "descriptive-capability-catalog",
        resources: [],
        summary: {
          total_resources: 0,
          live_resource_count: 0,
          status_counts: {
            live: 0,
            backend_only: 0,
            not_exposed: 0,
          },
        },
      },
    }),
  ]);

  const pendingRuns = dashboardResult.data.dashboard.pending_or_in_progress.length;
  const recentFailures = dashboardResult.data.dashboard.recent_failures.length;
  const totalResources =
    resourcesResult.data.summary?.total_resources ?? resourcesResult.data.resources.length;
  const healthyResources =
    resourcesResult.data.summary?.live_resource_count ??
    resourcesResult.data.resources.filter((resource) => resource.status === "live").length;

  return (
    <section className="page-shell">
      <div className="hero">
        <p className="eyebrow">Dashboard</p>
        <h1>Mission-ready foundation for agentic crypto operations.</h1>
        <p className="lede">
          Hermes now reads live backend state from the consolidated API bridge.
          This surface shows workflow pressure, recent failures, execution
          activity, and shared resource coverage without relying on placeholder
          copy.
        </p>
      </div>

      <div className="grid stats">
        {metrics.map((metric) => (
          <article key={metric.label} className="card">
            <div className="stat-label">{metric.label}</div>
            <div className="stat-value">{metric.value}</div>
          </article>
        ))}
        <article className="card">
          <div className="stat-label">Shared resources tracked</div>
          <div className="stat-value">{totalResources}</div>
        </article>
        <article className="card">
          <div className="stat-label">Pending workflow runs</div>
          <div className="stat-value">{pendingRuns}</div>
        </article>
        <article className="card">
          <div className="stat-label">Recent failures</div>
          <div className="stat-value">{recentFailures}</div>
        </article>
        <article className="card">
          <div className="stat-label">Resources with live backing</div>
          <div className="stat-value">{healthyResources}</div>
        </article>
      </div>

      <div className="grid split">
        <article className="card">
          <h2>Runtime health</h2>
          <ul className="list">
            {dashboardResult.data.dashboard.pending_or_in_progress.slice(0, 4).map((run) => (
              <li key={run.id}>
                <strong>{run.workflow_name}</strong>
                <div className="muted">
                  Status: {run.status}
                </div>
              </li>
            ))}
            {dashboardResult.data.dashboard.pending_or_in_progress.length === 0 ? (
              <li>No workflows are currently pending or in progress.</li>
            ) : null}
          </ul>
        </article>

        <article className="card">
          <h2>API bridge status</h2>
          <p className="status">
            {dashboardResult.ok && resourcesResult.ok ? "Live data connected" : "Degraded"}
          </p>
          <p className="muted">
            Observability: {dashboardResult.ok ? "connected" : dashboardResult.error}
          </p>
          <p className="muted">
            Resources: {resourcesResult.ok ? "connected" : resourcesResult.error}
          </p>
          <p className="muted">
            Contract: {resourcesResult.data.contract ?? "descriptive-capability-catalog"}
          </p>
        </article>
      </div>

      <div className="grid split page-section">
        <article className="card">
          <h2>Recent execution events</h2>
          <ul className="list">
            {dashboardResult.data.dashboard.recent_execution_events.slice(0, 5).map((event) => (
              <li key={event.id}>
                <strong>{event.event_type}</strong>
                <div className="muted">
                  {event.status} · {formatTimestamp(event.created_at)}
                </div>
              </li>
            ))}
            {dashboardResult.data.dashboard.recent_execution_events.length === 0 ? (
              <li>No execution events recorded yet.</li>
            ) : null}
          </ul>
        </article>

        <article className="card">
          <h2>Shared resource coverage</h2>
          <ul className="list">
            {resourcesResult.data.resources.slice(0, 6).map((resource) => (
              <li key={resource.name}>
                <div className="resource-row">
                  <strong>{resource.name}</strong>
                  <span className={`pill pill-${resource.status}`}>
                    {formatResourceStatus(resource.status)}
                  </span>
                </div>
                <div className="muted">{resource.evidence}</div>
              </li>
            ))}
            {resourcesResult.data.resources.length === 0 ? (
              <li>No shared resource data available.</li>
            ) : null}
          </ul>
        </article>
      </div>

      <div className="grid split page-section">
        <article className="card">
          <h2>Recent failures</h2>
          <ul className="list">
            {dashboardResult.data.dashboard.recent_failures.slice(0, 5).map((failure) => (
              <li key={failure.id}>
                <strong>{failure.error_type || "UnknownError"}</strong>
                <div className="muted">
                  {failure.error_message || "No message"} · {formatTimestamp(failure.created_at)}
                </div>
              </li>
            ))}
            {dashboardResult.data.dashboard.recent_failures.length === 0 ? (
              <li>No recent failures recorded.</li>
            ) : null}
          </ul>
        </article>

        <article className="card">
          <h2>Notification flow</h2>
          <ul className="list">
            {dashboardResult.data.dashboard.recent_notifications.slice(0, 5).map((notification) => (
              <li key={notification.id}>
                <strong>{notification.channel}</strong>
                <div className="muted">{formatTimestamp(notification.sent_time)}</div>
              </li>
            ))}
            {dashboardResult.data.dashboard.recent_notifications.length === 0 ? (
              <li>No notification deliveries recorded yet.</li>
            ) : null}
          </ul>
        </article>
      </div>
    </section>
  );
}
