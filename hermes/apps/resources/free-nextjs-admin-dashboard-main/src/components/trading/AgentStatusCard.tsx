"use client";
import React from "react";
import { useHermesData } from "@/hooks/useHermesData";
import Badge from "../ui/badge/Badge";

interface AgentData {
  status: string;
  count: number;
  agents: Array<{
    name: string;
    role: string;
    reports_to: string | null;
    recent_decision_count: number;
    latest_decision: string | null;
    allowed_toolsets: string[];
  }>;
}

const agentColors: Record<string, string> = {
  orchestrator: "bg-brand-500",
  "execution-agent": "bg-success-500",
  "market-researcher": "bg-warning-500",
  "portfolio-monitor": "bg-info-500",
  "risk-manager": "bg-error-500",
  "strategy-agent": "bg-purple-500",
};

const agentIcons: Record<string, string> = {
  orchestrator: "🎯",
  "execution-agent": "⚡",
  "market-researcher": "🔬",
  "portfolio-monitor": "📊",
  "risk-manager": "🛡️",
  "strategy-agent": "🧠",
};

export default function AgentStatusCard() {
  const { data, loading } = useHermesData<AgentData>("/api/agents", 60000);

  const agents = data?.agents ?? [];

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03] sm:p-6">
      <div className="flex justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-gray-800 dark:text-white/90">
            Agent Network
          </h3>
          <p className="mt-1 text-gray-500 text-theme-sm dark:text-gray-400">
            {loading ? "Loading..." : `${agents.length} agents registered`}
          </p>
        </div>
        <Badge color={data?.status === "live" ? "success" : "warning"}>
          {data?.status?.toUpperCase() ?? "..."}
        </Badge>
      </div>

      <div className="space-y-4">
        {loading ? (
          <div className="text-center py-8 text-gray-400">Loading agents...</div>
        ) : (
          agents.map((agent) => (
            <div
              key={agent.name}
              className="flex items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-gray-800/50"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`flex items-center justify-center w-10 h-10 rounded-lg text-lg ${
                    agentColors[agent.name] ?? "bg-gray-500"
                  } bg-opacity-10`}
                >
                  {agentIcons[agent.name] ?? "🤖"}
                </div>
                <div>
                  <p className="font-medium text-gray-800 text-theme-sm dark:text-white/90">
                    {agent.name}
                  </p>
                  <span className="text-gray-500 text-theme-xs dark:text-gray-400 line-clamp-1">
                    {agent.role}
                  </span>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  {agent.recent_decision_count > 0
                    ? `${agent.recent_decision_count} decisions`
                    : "Idle"}
                </p>
                {agent.reports_to && (
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    → {agent.reports_to}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
