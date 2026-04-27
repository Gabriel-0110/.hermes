"use client";
import React from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/hooks/useApi";
import PageHeader from "@/components/ui/PageHeader";
import ModuleCard from "@/components/ui/ModuleCard";
import Badge from "@/components/ui/Badge";
import Pill from "@/components/ui/Pill";
import LoadingState from "@/components/ui/LoadingState";

const agentProfiles = [
  { id: "orchestrator", name: "Orchestrator", model: "Claude Opus 4.6", role: "Primary decision maker", color: "#67c8ff" },
  { id: "market-researcher", name: "Market Researcher", model: "Claude Sonnet 4.6", role: "Market intelligence", color: "#8af2c5" },
  { id: "strategy-agent", name: "Strategy Agent", model: "Claude Sonnet 4.6", role: "Setup scanner", color: "#a78bfa" },
  { id: "risk-manager", name: "Risk Manager", model: "Claude Sonnet 4.6", role: "Risk gatekeeper", color: "#ff6b82" },
  { id: "portfolio-monitor", name: "Portfolio Monitor", model: "Claude Sonnet 4.6", role: "Ledger & tripwire", color: "#ffc86e" },
  { id: "execution-agent", name: "Execution Agent", model: "Qwen 3.5 9B", role: "Mechanical executor", color: "#38bdf8" },
];

export default function AgentsPage() {
  const agents = usePolling(api.agents.list, 30000);

  if (agents.loading) return <LoadingState label="Loading agents" />;

  const agentData = agents.data ?? [];

  return (
    <>
      <PageHeader
        title="Agents"
        code="/04"
        subtitle="Specialized agent profiles, status, and recent activity"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {agentProfiles.map((profile) => {
          const liveData = agentData.find(
            (a) =>
              a.profile === profile.id ||
              a.name?.toLowerCase().includes(profile.id.split("-")[0])
          );
          const role = liveData?.role ?? profile.role;
          const tools = liveData?.allowed_tools ?? [];
          const skills = liveData?.assigned_skills ?? [];
          const isRegistered = !!liveData;

          return (
            <div key={profile.id} className="hermes-module">
              <div className="relative px-5 py-4 border-b border-gray-200 bg-surface-high/50">
                <div
                  className="absolute top-0 left-0 w-full h-[2px]"
                  style={{
                    background: `linear-gradient(90deg, ${profile.color}, ${profile.color}44)`,
                  }}
                />
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-white">
                      {profile.name}
                    </h3>
                    <p className="font-mono text-[0.6rem] text-gray-500 mt-0.5">
                      {role}
                    </p>
                  </div>
                  <Pill
                    variant={isRegistered ? "live" : "scaffolded"}
                    dot
                  >
                    {isRegistered ? "registered" : "idle"}
                  </Pill>
                </div>
              </div>

              <div className="p-5 space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <StatCell label="Model" value={profile.model} />
                  <StatCell
                    label="Tools"
                    value={String(tools.length)}
                  />
                  <StatCell
                    label="Skills"
                    value={skills.length > 0 ? skills.join(", ") : "—"}
                  />
                  <StatCell
                    label="Toolset"
                    value={liveData?.allowed_toolsets?.[0] ?? "—"}
                  />
                </div>

                {profile.id === "execution-agent" && (
                  <div className="flex items-center gap-2 pt-2 border-t border-gray-200/30">
                    <Badge color="brand">Local Model</Badge>
                    <span className="font-mono text-[0.55rem] text-gray-500">
                      LM Studio · 32K ctx
                    </span>
                  </div>
                )}

                {profile.id === "orchestrator" && (
                  <div className="flex items-center gap-2 pt-2 border-t border-gray-200/30">
                    <Badge color="brand">Primary</Badge>
                    <span className="font-mono text-[0.55rem] text-gray-500">
                      Bedrock · 200K ctx
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-[0.5rem] uppercase tracking-wider text-gray-600">
        {label}
      </div>
      <div className="font-mono text-xs text-white truncate">{value}</div>
    </div>
  );
}

function timeAgo(ts: string): string {
  try {
    const diff = Date.now() - new Date(ts).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch {
    return "—";
  }
}
