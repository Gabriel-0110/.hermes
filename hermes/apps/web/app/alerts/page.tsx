import { fetchHermesApi, formatTimestamp } from "../../lib/hermes-api";

type PendingSignalsSnapshot = {
  status: string;
  count: number;
  events: Array<{
    id: string;
    event_type: string;
    alert_event_id: string;
    symbol: string | null;
    payload: {
      correlation_id?: string;
      event_id?: string;
      signal?: string;
      direction?: string;
      alert_id?: string;
      symbol?: string;
    };
    delivery_status: string;
    ts: number;
  }>;
};

type TimelineSnapshot = {
  status: string;
  count: number;
  timeline: Array<{
    kind: string;
    status?: string;
    workflow_name?: string;
    workflow_step?: string;
    tool_name?: string;
    event_type?: string;
    error_type?: string | null;
    decision?: string | null;
    timestamp?: string;
  }>;
};

export default async function AlertsPage() {
  const pendingSignalsResult = await fetchHermesApi<PendingSignalsSnapshot>(
    "/execution/signals/pending",
    {
      fallback: {
        status: "offline",
        count: 0,
        events: [],
      },
    },
  );

  const correlationIds = Array.from(
    new Set(
      pendingSignalsResult.data.events
        .map((event) => event.payload?.correlation_id)
        .filter((value): value is string => Boolean(value)),
    ),
  ).slice(0, 5);

  const timelineEntries = await Promise.all(
    correlationIds.map(async (correlationId) => {
      const result = await fetchHermesApi<TimelineSnapshot>(
        `/observability/timeline/${correlationId}`,
        {
          fallback: {
            status: "offline",
            count: 0,
            timeline: [],
          },
        },
      );
      return {
        correlationId,
        ...result,
      };
    }),
  );

  const timelineByCorrelation = new Map(
    timelineEntries.map((entry) => [entry.correlationId, entry]),
  );

  return (
    <section className="page-shell">
      <div className="hero">
        <p className="eyebrow">Alerts</p>
        <h1>TradingView signal intake and operator traceability.</h1>
        <p className="lede">
          This page is fed from the live pending-signal queue and correlated
          observability timelines. It is intended for operator review of signals
          before downstream execution handling is hardened.
        </p>
      </div>

      <div className="grid stats">
        <article className="card">
          <div className="stat-label">Pending TradingView signals</div>
          <div className="stat-value">{pendingSignalsResult.data.count}</div>
        </article>
        <article className="card">
          <div className="stat-label">Timelines loaded</div>
          <div className="stat-value">{timelineEntries.length}</div>
        </article>
        <article className="card">
          <div className="stat-label">Queue source</div>
          <div className="stat-value">/execution/signals/pending</div>
        </article>
      </div>

      <div className="grid cards page-section">
        {pendingSignalsResult.data.events.map((event) => {
          const correlationId = event.payload?.correlation_id;
          const timeline = correlationId
            ? timelineByCorrelation.get(correlationId)?.data.timeline ?? []
            : [];

          return (
            <article key={event.id} className="card">
              <div className="resource-row">
                <h2>{event.symbol || event.payload?.symbol || "Unknown symbol"}</h2>
                <span className="pill pill-partial">{event.delivery_status}</span>
              </div>

              <p className="muted">
                Event: {event.event_type} · Alert ID: {event.alert_event_id}
              </p>
              <p className="muted">
                Correlation: {correlationId || "not provided"}
              </p>
              <p className="muted">
                Queued at: {formatTimestamp(new Date(event.ts * 1000).toISOString())}
              </p>

              <h3>Correlated timeline</h3>
              <ul className="list">
                {timeline.slice(0, 6).map((item, index) => (
                  <li key={`${event.id}-${item.kind}-${index}`}>
                    <strong>{item.kind}</strong>
                    <div className="muted">
                      {item.decision ||
                        item.event_type ||
                        item.tool_name ||
                        item.workflow_step ||
                        item.error_type ||
                        item.status ||
                        "recorded"}
                      {" · "}
                      {formatTimestamp(item.timestamp)}
                    </div>
                  </li>
                ))}
                {timeline.length === 0 ? (
                  <li>No correlated observability timeline is available yet.</li>
                ) : null}
              </ul>
            </article>
          );
        })}

        {pendingSignalsResult.data.events.length === 0 ? (
          <article className="card">
            <h2>No pending TradingView signals</h2>
            <p className="muted">
              {pendingSignalsResult.ok
                ? "The execution queue is currently empty."
                : pendingSignalsResult.error}
            </p>
          </article>
        ) : null}
      </div>
    </section>
  );
}
