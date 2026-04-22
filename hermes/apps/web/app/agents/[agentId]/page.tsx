import Link from "next/link";

import { fetchHermesApi, formatTimestamp } from "../../../lib/hermes-api";

type AgentDetailSnapshot = {
  status: string;
  team_name: string;
  trading_mode: {
    mode?: string;
    enforcement_mode?: string;
  };
  agent: {
    name: string;
    canonical_agent_id: string;
    profile: string;
    role: string;
    reports_to: string | null;
    responsibilities: string[];
    allowed_toolsets: string[];
    allowed_tools: string[];
    assigned_skills: string[];
    expected_outputs: string[];
    recent_decisions: Array<{
      id: string;
      status: string;
      decision: string | null;
      created_at: string;
      correlation_id: string | null;
    }>;
    recent_workflow_runs: Array<{
      id: string;
      workflow_name: string;
      status: string;
      created_at: string;
    }>;
    correlated_timelines: Array<{
      correlation_id: string;
      timeline_count: number;
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
    }>;
  };
};

type AgentTimelineSnapshot = {
  status: string;
  agent_id: string;
  count: number;
  timeline: Array<{
    correlation_id: string;
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

export default async function AgentDetailPage({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = await params;

  const [detailResult, timelineResult] = await Promise.all([
    fetchHermesApi<AgentDetailSnapshot>(`/agents/${agentId}`, {
      fallback: null,
    }),
    fetchHermesApi<AgentTimelineSnapshot>(`/agents/${agentId}/timeline`, {
      fallback: {
        status: "offline",
        agent_id: agentId,
        count: 0,
        timeline: [],
      },
    }),
  ]);

  if (!detailResult.ok || !detailResult.data) {
    return (
      <section className="page-shell">
        <div className="hero">
          <p className="eyebrow">Agent Detail</p>
          <h1>Agent detail unavailable.</h1>
          <p className="lede">{detailResult.error || "The requested agent could not be loaded."}</p>
        </div>
      </section>
    );
  }

  const agent = detailResult.data.agent;

  return (
    <section className="page-shell">
      <div className="hero">
        <p className="eyebrow">Agent Detail</p>
        <h1>{agent.name}</h1>
        <p className="lede">{agent.role}</p>
        <p className="muted">
          <Link href="/agents">Back to agents</Link>
        </p>
      </div>

      <div className="grid stats">
        <article className="card">
          <div className="stat-label">Profile</div>
          <div className="stat-value">{agent.profile}</div>
        </article>
        <article className="card">
          <div className="stat-label">Reports to</div>
          <div className="stat-value">{agent.reports_to || "direct control"}</div>
        </article>
        <article className="card">
          <div className="stat-label">Recent decisions</div>
          <div className="stat-value">{agent.recent_decisions.length}</div>
        </article>
        <article className="card">
          <div className="stat-label">Timeline events</div>
          <div className="stat-value">{timelineResult.data.count}</div>
        </article>
      </div>

      <div className="grid split page-section">
        <article className="card">
          <h2>Responsibilities</h2>
          <ul className="list">
            {agent.responsibilities.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>

        <article className="card">
          <h2>Expected outputs</h2>
          <ul className="list">
            {agent.expected_outputs.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </div>

      <div className="grid split page-section">
        <article className="card">
          <h2>Allowed tools</h2>
          <div className="chip-row">
            {agent.allowed_tools.map((item) => (
              <span key={item} className="pill pill-partial">
                {item}
              </span>
            ))}
          </div>
        </article>

        <article className="card">
          <h2>Assigned skills</h2>
          <div className="chip-row">
            {agent.assigned_skills.map((item) => (
              <span key={item} className="pill pill-scaffolded">
                {item}
              </span>
            ))}
          </div>
        </article>
      </div>

      <div className="grid split page-section">
        <article className="card">
          <h2>Recent decisions</h2>
          <ul className="list">
            {agent.recent_decisions.map((decision) => (
              <li key={decision.id}>
                <strong>{decision.decision || decision.status}</strong>
                <div className="muted">
                  {decision.correlation_id || "no correlation"} ·{" "}
                  {formatTimestamp(decision.created_at)}
                </div>
              </li>
            ))}
            {agent.recent_decisions.length === 0 ? (
              <li>No decisions recorded for this agent yet.</li>
            ) : null}
          </ul>
        </article>

        <article className="card">
          <h2>Recent workflow runs</h2>
          <ul className="list">
            {agent.recent_workflow_runs.map((run) => (
              <li key={run.id}>
                <strong>{run.workflow_name}</strong>
                <div className="muted">
                  {run.status} · {formatTimestamp(run.created_at)}
                </div>
              </li>
            ))}
            {agent.recent_workflow_runs.length === 0 ? (
              <li>No workflow runs recorded for this agent yet.</li>
            ) : null}
          </ul>
        </article>
      </div>

      <div className="grid page-section">
        <article className="card">
          <h2>Correlated activity timeline</h2>
          <ul className="list">
            {timelineResult.data.timeline.slice(0, 20).map((item, index) => (
              <li key={`${item.correlation_id}-${item.kind}-${index}`}>
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
                  {item.correlation_id}
                  {" · "}
                  {formatTimestamp(item.timestamp)}
                </div>
              </li>
            ))}
            {timelineResult.data.timeline.length === 0 ? (
              <li>No correlated activity timeline is available yet.</li>
            ) : null}
          </ul>
        </article>
      </div>
    </section>
  );
}
