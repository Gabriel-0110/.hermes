"use client";
import React from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/hooks/useApi";
import PageHeader from "@/components/ui/PageHeader";
import ModuleCard from "@/components/ui/ModuleCard";
import MetricCard from "@/components/ui/MetricCard";
import DataTable, { Column } from "@/components/ui/DataTable";
import Badge from "@/components/ui/Badge";
import LoadingState from "@/components/ui/LoadingState";
import type { SignalEvent, MovementEntry, Approval } from "@/lib/api";

export default function ExecutionPage() {
  const surface = usePolling(api.execution.surface, 15000);
  const movements = usePolling(api.execution.movements, 30000);
  const approvals = usePolling(api.execution.pendingApprovals, 15000);

  if (surface.loading) return <LoadingState label="Loading execution data" />;

  const pending = surface.data?.pending_signals ?? [];
  const events = surface.data?.recent_events ?? [];
  const safetyStatus = surface.data?.safety ?? {};

  const signalCols: Column<SignalEvent>[] = [
    {
      key: "symbol",
      label: "Symbol",
      mono: true,
      render: (r) => <span className="text-white font-semibold">{r.symbol}</span>,
    },
    {
      key: "direction",
      label: "Direction",
      render: (r) => (
        <Badge color={r.direction === "long" ? "success" : "error"}>
          {r.direction}
        </Badge>
      ),
    },
    { key: "signal", label: "Signal", mono: true },
    {
      key: "price",
      label: "Price",
      align: "right",
      mono: true,
      render: (r) => r.price?.toFixed(2) ?? "—",
    },
    {
      key: "processing_status",
      label: "Status",
      render: (r) => (
        <Badge color={r.processing_status === "pending" ? "warning" : "success"}>
          {r.processing_status}
        </Badge>
      ),
    },
    {
      key: "event_time",
      label: "Time",
      mono: true,
      render: (r) => formatTime(r.event_time),
    },
  ];

  const movementCols: Column<MovementEntry>[] = [
    { key: "symbol", label: "Symbol", mono: true, render: (r) => <span className="text-white">{r.symbol}</span> },
    {
      key: "side",
      label: "Side",
      render: (r) => (
        <Badge color={r.side === "buy" ? "success" : "error"}>{r.side}</Badge>
      ),
    },
    { key: "quantity", label: "Qty", align: "right", mono: true, render: (r) => r.quantity?.toFixed(4) ?? "—" },
    { key: "price", label: "Price", align: "right", mono: true, render: (r) => r.price?.toFixed(2) ?? "—" },
    {
      key: "execution_mode",
      label: "Mode",
      render: (r) => (
        <Badge color={r.execution_mode === "live" ? "error" : "warning"}>
          {r.execution_mode}
        </Badge>
      ),
    },
    { key: "movement_time", label: "Time", mono: true, render: (r) => formatTime(r.movement_time) },
  ];

  const approvalCols: Column<Approval>[] = [
    { key: "symbol", label: "Symbol", mono: true, render: (r) => <span className="text-white">{r.symbol}</span> },
    {
      key: "side",
      label: "Side",
      render: (r) => (
        <Badge color={r.side === "buy" ? "success" : "error"}>{r.side}</Badge>
      ),
    },
    { key: "amount", label: "Amount", align: "right", mono: true, render: (r) => r.amount?.toFixed(4) ?? "—" },
    {
      key: "status",
      label: "Status",
      render: (r) => <Badge color="warning">{r.status}</Badge>,
    },
    { key: "created_at", label: "Created", mono: true, render: (r) => formatTime(r.created_at) },
  ];

  return (
    <>
      <PageHeader
        title="Execution"
        code="/01"
        subtitle="Signal processing, order lifecycle, and movement journal"
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <MetricCard
          label="Pending Signals"
          value={String(pending.length)}
        />
        <MetricCard
          label="Recent Events"
          value={String(events.length)}
        />
        <MetricCard
          label="Pending Approvals"
          value={String(approvals.data?.length ?? 0)}
          trend={
            (approvals.data?.length ?? 0) > 0 ? "down" : "neutral"
          }
        />
      </div>

      <div className="space-y-6">
        <ModuleCard title="Pending Signals" subtitle={`${pending.length} awaiting processing`}>
          <DataTable columns={signalCols} data={pending} emptyMessage="No pending signals" />
        </ModuleCard>

        <ModuleCard title="Operator Approvals" subtitle="Trades awaiting human review">
          <DataTable columns={approvalCols} data={approvals.data ?? []} emptyMessage="No pending approvals" />
        </ModuleCard>

        <ModuleCard title="Movement Journal" subtitle="Recent execution movements">
          <DataTable columns={movementCols} data={movements.data ?? []} emptyMessage="No movements recorded" />
        </ModuleCard>
      </div>
    </>
  );
}

function formatTime(ts?: string): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}
