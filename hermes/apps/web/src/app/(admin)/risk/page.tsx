"use client";
import React, { useState } from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/hooks/useApi";
import PageHeader from "@/components/ui/PageHeader";
import ModuleCard from "@/components/ui/ModuleCard";
import MetricCard from "@/components/ui/MetricCard";
import DataTable, { Column } from "@/components/ui/DataTable";
import KillSwitchIndicator from "@/components/ui/KillSwitchIndicator";
import Badge from "@/components/ui/Badge";
import LoadingState from "@/components/ui/LoadingState";
import type { RiskRejection, TradeCandidateScore, PositionSnapshot } from "@/lib/api";

export default function RiskPage() {
  const dashboard = usePolling(api.risk.dashboard, 10000);
  const candidates = usePolling(api.risk.candidates, 30000);
  const rejectionsApi = usePolling(api.risk.rejections, 30000);
  const [actionLoading, setActionLoading] = useState(false);

  if (dashboard.loading) return <LoadingState label="Loading risk data" />;

  const ks = dashboard.data?.kill_switch ?? { active: false };
  const positions = dashboard.data?.positions ?? [];
  const rejections = rejectionsApi.data ?? [];
  const totalExposure = positions.reduce(
    (sum, p) => sum + Math.abs((p.mark_price ?? 0) * (p.size ?? 0)),
    0
  );

  const handleKillSwitch = async () => {
    setActionLoading(true);
    try {
      if (ks.active) {
        await api.risk.deactivateKillSwitch();
      } else {
        await api.risk.activateKillSwitch("Manual activation from dashboard");
      }
      dashboard.refetch();
    } finally {
      setActionLoading(false);
    }
  };

  const rejectionCols: Column<RiskRejection>[] = [
    { key: "symbol", label: "Symbol", mono: true, render: (r) => <span className="text-white">{r.symbol}</span> },
    { key: "reason", label: "Reason", render: (r) => <span className="text-error-400 text-xs">{r.reason}</span> },
    {
      key: "created_at",
      label: "Time",
      mono: true,
      render: (r) =>
        r.created_at
          ? new Date(r.created_at).toLocaleTimeString()
          : "—",
    },
  ];

  const candidateCols: Column<TradeCandidateScore>[] = [
    { key: "symbol", label: "Symbol", mono: true, render: (r) => <span className="text-white">{r.symbol}</span> },
    { key: "strategy_name", label: "Strategy", mono: true },
    {
      key: "direction",
      label: "Direction",
      render: (r) => (
        <Badge color={r.direction === "long" ? "success" : r.direction === "short" ? "error" : "gray"}>
          {r.direction}
        </Badge>
      ),
    },
    {
      key: "confidence",
      label: "Confidence",
      align: "right",
      mono: true,
      render: (r) => (
        <span className={r.confidence >= 0.7 ? "text-success-400" : r.confidence >= 0.5 ? "text-warning-400" : "text-gray-400"}>
          {(r.confidence * 100).toFixed(0)}%
        </span>
      ),
    },
    {
      key: "chronos_score",
      label: "Chronos",
      align: "right",
      mono: true,
      render: (r) => r.chronos_score != null ? r.chronos_score.toFixed(2) : "—",
    },
  ];

  const positionCols: Column<PositionSnapshot>[] = [
    { key: "symbol", label: "Symbol", mono: true, render: (r) => <span className="text-white">{r.symbol}</span> },
    {
      key: "side",
      label: "Side",
      render: (r) => <Badge color={r.side === "long" ? "success" : "error"}>{r.side}</Badge>,
    },
    {
      key: "size",
      label: "Size",
      align: "right",
      mono: true,
      render: (r) => r.size?.toFixed(4) ?? "—",
    },
    {
      key: "unrealized_pnl",
      label: "PnL",
      align: "right",
      mono: true,
      render: (r) => (
        <span className={(r.unrealized_pnl ?? 0) >= 0 ? "text-success-400" : "text-error-400"}>
          {(r.unrealized_pnl ?? 0) >= 0 ? "+" : ""}
          {(r.unrealized_pnl ?? 0).toFixed(2)}
        </span>
      ),
    },
    {
      key: "leverage",
      label: "Leverage",
      align: "right",
      mono: true,
      render: (r) => `${r.leverage ?? 1}x`,
    },
  ];

  return (
    <>
      <PageHeader
        title="Risk"
        code="/02"
        subtitle="Kill switch, exposure monitoring, policy enforcement"
        action={
          <button
            onClick={handleKillSwitch}
            disabled={actionLoading}
            className={`font-mono text-[0.65rem] uppercase tracking-[0.14em] border rounded px-4 py-1.5 transition-all hover:-translate-y-px ${
              ks.active
                ? "text-success-400 border-success-300 hover:bg-success-50"
                : "text-error-400 border-error-300 hover:bg-error-50"
            } disabled:opacity-50`}
          >
            {ks.active ? "Deactivate Kill Switch" : "Activate Kill Switch"}
          </button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="hermes-card p-5 flex items-center gap-4">
          <KillSwitchIndicator active={ks.active} reason={ks.reason} />
        </div>
        <MetricCard
          label="Total Exposure"
          value={`$${totalExposure.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
        />
        <MetricCard
          label="Open Positions"
          value={String(positions.length)}
        />
        <MetricCard
          label="Recent Rejections"
          value={String(rejections.length)}
          trend={rejections.length > 0 ? "down" : "neutral"}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6">
        <ModuleCard title="Position Exposure">
          <DataTable columns={positionCols} data={positions} emptyMessage="No open positions" />
        </ModuleCard>

        <ModuleCard title="Trade Candidates" subtitle="Scored by strategy engine">
          <DataTable columns={candidateCols} data={candidates.data ?? []} emptyMessage="No candidates scored" />
        </ModuleCard>
      </div>

      <ModuleCard title="Recent Rejections" subtitle="Policy engine denials">
        <DataTable columns={rejectionCols} data={rejections} emptyMessage="No recent rejections" />
      </ModuleCard>
    </>
  );
}
