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
import type { WorkflowRun, FailureEvent } from "@/lib/api";

export default function ObservabilityPage() {
  const obs = usePolling(api.observability.dashboard, 30000);
  const workflows = usePolling(api.observability.workflows, 30000);
  const failures = usePolling(api.observability.failures, 30000);

  if (obs.loading) return <LoadingState label="Loading observability data" />;

  const recentWorkflows = workflows.data ?? obs.data?.recent_workflows ?? [];
  const recentFailures = failures.data ?? obs.data?.recent_failures ?? [];

  const statusColor = (s: string): "success" | "error" | "warning" | "gray" => {
    if (s === "completed" || s === "success") return "success";
    if (s === "failed" || s === "error") return "error";
    if (s === "running" || s === "pending") return "warning";
    return "gray";
  };

  const workflowCols: Column<WorkflowRun>[] = [
    {
      key: "workflow_name",
      label: "Workflow",
      mono: true,
      render: (r) => <span className="text-white">{r.workflow_name}</span>,
    },
    {
      key: "status",
      label: "Status",
      render: (r) => <Badge color={statusColor(r.status)}>{r.status}</Badge>,
    },
    {
      key: "correlation_id",
      label: "Correlation ID",
      mono: true,
      render: (r) => (
        <span className="text-gray-400 text-[0.6rem]">
          {r.correlation_id?.slice(0, 12)}...
        </span>
      ),
    },
    {
      key: "created_at",
      label: "Started",
      mono: true,
      render: (r) => formatTime(r.created_at),
    },
  ];

  const failureCols: Column<FailureEvent>[] = [
    {
      key: "error_type",
      label: "Type",
      mono: true,
      render: (r) => <span className="text-error-400">{r.error_type}</span>,
    },
    {
      key: "message",
      label: "Message",
      render: (r) => (
        <span className="text-xs text-gray-400 truncate block max-w-xs">
          {r.message}
        </span>
      ),
    },
    {
      key: "created_at",
      label: "Time",
      mono: true,
      render: (r) => formatTime(r.created_at),
    },
  ];

  return (
    <>
      <PageHeader
        title="Observability"
        code="/05"
        subtitle="Workflow runs, tool calls, failure tracking, and audit trails"
      />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <MetricCard
          label="Workflow Runs"
          value={String(recentWorkflows.length)}
        />
        <MetricCard
          label="Completed"
          value={String(
            recentWorkflows.filter(
              (w) => w.status === "completed" || w.status === "success"
            ).length
          )}
          trend="up"
        />
        <MetricCard
          label="Failures"
          value={String(recentFailures.length)}
          trend={recentFailures.length > 0 ? "down" : "neutral"}
        />
      </div>

      <div className="space-y-6">
        <ModuleCard title="Workflow Runs" subtitle="Recent pipeline executions">
          <DataTable columns={workflowCols} data={recentWorkflows} emptyMessage="No workflow runs recorded" />
        </ModuleCard>

        <ModuleCard title="Failures" subtitle="Recent errors and exceptions">
          <DataTable columns={failureCols} data={recentFailures} emptyMessage="No failures — system healthy" />
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
