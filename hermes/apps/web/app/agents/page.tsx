import Link from "next/link";

import { fetchHermesApi, formatTimestamp } from "../../lib/hermes-api";

type AgentSnapshot = {
  status: string;
  team_name: string;
  trading_mode: {
    mode?: string;
    enforcement_mode?: string;
    forbid_live_execution?: boolean;
  };
  count: number;
  agents: Array<{
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
    recent_decision_count: number;
    latest_decision: {
      status?: string;
      decision?: string | null;
      created_at?: string;
    } | null;
  }>;
};

export default async function AgentsPage() {
  const agentsResult = await fetchHermesApi<AgentSnapshot>("/agents", {
    fallback: {
      status: "offline",
      team_name: "hermes-trading-desk",
      trading_mode: {},
      count: 0,
      agents: [],
    },
  });

  return (
    <section className="page-shell">
      <div className="hero">
        <p className="eyebrow">Agent Layer</p>
        <h1>Specialized agents with explicit boundaries.</h1>
        <p className="lede">
          The agent roster below is now sourced from the trading desk manifest
          and annotated with recent live decision activity from the backend
          observability layer.
        </p>
      </div>

      <div className="grid stats">
        <article className="card">
          <div className="stat-label">Desk manifest</div>
          <div className="stat-value">{agentsResult.data.team_name}</div>
        </article>
        <article className="card">
          <div className="stat-label">Configured agents</div>
          <div className="stat-value">{agentsResult.data.count}</div>
        </article>
        <article className="card">
          <div className="stat-label">Trading mode</div>
          <div className="stat-value">{agentsResult.data.trading_mode.mode || "unknown"}</div>
        </article>
        <article className="card">
          <div className="stat-label">Execution safety</div>
          <div className="stat-value">
            {agentsResult.data.trading_mode.forbid_live_execution ? "live blocked" : "unrestricted"}
          </div>
        </article>
      </div>

      <div className="grid cards">
        {agentsResult.data.agents.map((agent) => (
          <article key={agent.canonical_agent_id} className="card">
            <div className="resource-row">
              <h2>
                <Link href={`/agents/${agent.canonical_agent_id}`} className="detail-link">
                  {agent.name}
                </Link>
              </h2>
              <span className="pill pill-partial">{agent.profile}</span>
            </div>
            <p>{agent.role}</p>
            <p className="muted">
              Reports to: {agent.reports_to || "direct control plane"}
            </p>
            <p className="muted">
              Recent decisions: {agent.recent_decision_count}
            </p>
            <p className="muted">
              Latest activity:{" "}
              {agent.latest_decision
                ? `${agent.latest_decision.decision || agent.latest_decision.status || "recorded"} · ${formatTimestamp(
                    agent.latest_decision.created_at,
                  )}`
                : "No decision history recorded yet"}
            </p>

            <h3>Responsibilities</h3>
            <ul className="list">
              {agent.responsibilities.slice(0, 3).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>

            <div className="agent-meta-grid">
              <div>
                <h3>Toolsets</h3>
                <div className="chip-row">
                  {agent.allowed_toolsets.map((toolset) => (
                    <span key={toolset} className="pill pill-partial">
                      {toolset}
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <h3>Skills</h3>
                <div className="chip-row">
                  {agent.assigned_skills.slice(0, 4).map((skill) => (
                    <span key={skill} className="pill pill-scaffolded">
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <p className="muted">
              <Link href={`/agents/${agent.canonical_agent_id}`} className="detail-link">
                Open detailed activity timeline
              </Link>
            </p>
          </article>
        ))}
        {agentsResult.data.agents.length === 0 ? (
          <article className="card">
            <h2>Agent data unavailable</h2>
            <p className="muted">
              {agentsResult.ok ? "No agents were returned." : agentsResult.error}
            </p>
          </article>
        ) : null}
      </div>
    </section>
  );
}
