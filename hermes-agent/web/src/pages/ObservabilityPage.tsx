import { useEffect, useState } from "react";
import { Activity, AlertTriangle, ArrowRightLeft, Bell, Bot, Clock3, Search, Wrench } from "lucide-react";
import { api } from "@/lib/api";
import type {
  AgentDecisionRecord,
  EventTimelineItem,
  ExecutionEventRecord,
  MovementRecord,
  NotificationAuditRecord,
  ObservabilityDashboardResponse,
  SystemErrorRecord,
  ToolCallRecord,
  WorkflowRunDetail,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

function prettyDate(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function truncate(value?: string | null, size = 140): string {
  if (!value) return "—";
  return value.length > size ? `${value.slice(0, size)}...` : value;
}

function formatNumber(value?: number | null, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);
}

function formatUsd(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function timelineSummary(item: EventTimelineItem): string {
  if (item.kind === "movement") {
    const movement = item as EventTimelineItem & {
      movement_type?: string;
      symbol?: string;
      quantity?: number;
      cash_delta_usd?: number;
      notional_delta_usd?: number;
      execution_mode?: string;
    };
    return [
      movement.movement_type,
      movement.symbol,
      movement.quantity !== undefined ? `qty=${formatNumber(movement.quantity)}` : null,
      movement.cash_delta_usd !== undefined ? `cash=${formatUsd(movement.cash_delta_usd)}` : null,
      movement.execution_mode ? `mode=${movement.execution_mode}` : null,
    ].filter(Boolean).join(" • ");
  }

  if (item.kind === "execution_event") {
    const execution = item as EventTimelineItem & { event_type?: string; symbol?: string };
    return [execution.event_type, execution.symbol].filter(Boolean).join(" • ");
  }

  if (item.kind === "workflow_step") {
    const step = item as EventTimelineItem & { workflow_step?: string; agent_name?: string };
    return [step.workflow_step, step.agent_name].filter(Boolean).join(" • ");
  }

  if (item.kind === "agent_decision") {
    const decision = item as EventTimelineItem & { agent_name?: string; decision?: string };
    return [decision.agent_name, decision.decision].filter(Boolean).join(" • ");
  }

  return truncate(JSON.stringify(item), 220);
}

function StatusBadge({ value }: { value: string }) {
  const normalized = value.toLowerCase();
  const variant =
    normalized.includes("fail") || normalized.includes("reject") || normalized.includes("error")
      ? "destructive"
      : normalized.includes("run") || normalized.includes("progress") || normalized.includes("start")
        ? "warning"
        : normalized.includes("complete") || normalized.includes("approved") || normalized.includes("deliver")
          ? "success"
          : "outline";
  return <Badge variant={variant}>{value}</Badge>;
}

function SectionTable({
  title,
  icon: Icon,
  rows,
  columns,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  rows: Array<any>;
  columns: Array<{ key: string; label: string; render?: (row: any) => React.ReactNode }>;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Icon className="h-5 w-5 text-muted-foreground" />
          <CardTitle className="text-base">{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                {columns.map((column) => (
                  <th key={column.key} className="py-2 pr-4 text-left font-medium">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={columns.length} className="py-4 text-muted-foreground">
                    No records yet.
                  </td>
                </tr>
              )}
              {rows.map((row, index) => (
                <tr key={`${String(row.id ?? index)}`} className="border-b border-border/40 align-top">
                  {columns.map((column) => (
                    <td key={column.key} className="py-3 pr-4">
                      {column.render ? column.render(row) : String(row[column.key] ?? "—")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ObservabilityPage() {
  const [dashboard, setDashboard] = useState<ObservabilityDashboardResponse | null>(null);
  const [workflowDetail, setWorkflowDetail] = useState<WorkflowRunDetail | null>(null);
  const [toolCalls, setToolCalls] = useState<ToolCallRecord[]>([]);
  const [decisions, setDecisions] = useState<AgentDecisionRecord[]>([]);
  const [executionEvents, setExecutionEvents] = useState<ExecutionEventRecord[]>([]);
  const [movements, setMovements] = useState<MovementRecord[]>([]);
  const [systemErrors, setSystemErrors] = useState<SystemErrorRecord[]>([]);
  const [notifications, setNotifications] = useState<NotificationAuditRecord[]>([]);
  const [timeline, setTimeline] = useState<EventTimelineItem[]>([]);
  const [correlationId, setCorrelationId] = useState("");

  useEffect(() => {
    const load = async () => {
      const snapshot = await api.getObservabilityDashboard(12);
      setDashboard(snapshot);

      const firstRun = snapshot.recent_workflow_runs[0];
      if (firstRun?.id) {
        const [detail, nextToolCalls, nextDecisions, nextExecutionEvents, nextMovements, nextSystemErrors, nextNotifications] =
          await Promise.all([
            api.getWorkflowRun(firstRun.id),
            api.getToolCalls({ workflow_run_id: firstRun.id, limit: 10 }),
            api.getAgentDecisions({ workflow_run_id: firstRun.id, limit: 10 }),
            api.getExecutionEvents({ workflow_run_id: firstRun.id, limit: 10 }),
            api.getMovements({ workflow_run_id: firstRun.id, limit: 10 }),
            api.getSystemErrors({ workflow_run_id: firstRun.id, limit: 10 }),
            api.getNotifications(10),
          ]);
        setWorkflowDetail(detail);
        setToolCalls(nextToolCalls);
        setDecisions(nextDecisions);
        setExecutionEvents(nextExecutionEvents);
        setMovements(nextMovements);
        setSystemErrors(nextSystemErrors);
        setNotifications(nextNotifications);
        if (firstRun.correlation_id) {
          setCorrelationId(firstRun.correlation_id);
          setTimeline(await api.getEventTimeline(firstRun.correlation_id));
        }
      } else {
        setMovements(snapshot.recent_movements);
      }
    };

    load().catch(() => {});
  }, []);

  async function loadCorrelationDrilldown(rawCorrelationId: string) {
    const normalized = rawCorrelationId.trim();
    if (!normalized) return;
    const [nextTimeline, nextMovements, nextExecutionEvents, nextDecisions, nextToolCalls, nextSystemErrors] = await Promise.all([
      api.getEventTimeline(normalized),
      api.getMovements({ correlation_id: normalized, limit: 25 }),
      api.getExecutionEvents({ correlation_id: normalized, limit: 25 }),
      api.getAgentDecisions({ correlation_id: normalized, limit: 25 }),
      api.getToolCalls({ correlation_id: normalized, limit: 25 }),
      api.getSystemErrors({ correlation_id: normalized, limit: 25 }),
    ]);
    setTimeline(nextTimeline);
    setMovements(nextMovements);
    setExecutionEvents(nextExecutionEvents);
    setDecisions(nextDecisions);
    setToolCalls(nextToolCalls);
    setSystemErrors(nextSystemErrors);
  }

  async function loadTimeline() {
    await loadCorrelationDrilldown(correlationId);
  }

  if (!dashboard) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  const workflowRuns = dashboard.recent_workflow_runs;
  const pending = dashboard.pending_or_in_progress;
  const failures = dashboard.recent_failures;
  const movementRows = movements.length > 0 ? movements : dashboard.recent_movements;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Recent Workflow Runs</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-display">{workflowRuns.length}</div></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Pending / In Progress</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-display">{pending.length}</div></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Recent Failures</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-display">{failures.length}</div></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Recent Movements</CardTitle></CardHeader>
          <CardContent><div className="text-3xl font-display">{dashboard.recent_movements.length}</div></CardContent>
        </Card>
      </div>

      <SectionTable
        title="Live Workflows"
        icon={Activity}
        rows={workflowRuns}
        columns={[
          { key: "id", label: "Run" },
          {
            key: "correlation_id",
            label: "Correlation",
            render: (row) => row.correlation_id ? (
              <button
                type="button"
                className="font-mono-ui text-xs text-foreground underline-offset-4 hover:underline"
                onClick={() => {
                  const nextCorrelationId = String(row.correlation_id);
                  setCorrelationId(nextCorrelationId);
                  void loadCorrelationDrilldown(nextCorrelationId);
                }}
              >
                {String(row.correlation_id)}
              </button>
            ) : "—",
          },
          { key: "status", label: "Status", render: (row) => <StatusBadge value={String(row.status ?? "unknown")} /> },
          { key: "created_at", label: "Started", render: (row) => prettyDate(String(row.created_at ?? "")) },
          { key: "summarized_output", label: "Output", render: (row) => <span className="text-muted-foreground">{truncate(String(row.summarized_output ?? ""))}</span> },
        ]}
      />

      {workflowDetail && (
        <SectionTable
          title={`Workflow Detail: ${workflowDetail.id}`}
          icon={Clock3}
          rows={workflowDetail.steps}
          columns={[
            { key: "workflow_step", label: "Step" },
            { key: "agent_name", label: "Agent" },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={String(row.status ?? "unknown")} /> },
            { key: "created_at", label: "Updated", render: (row) => prettyDate(String(row.created_at ?? "")) },
            { key: "summarized_output", label: "Summary", render: (row) => <span className="text-muted-foreground">{truncate(String(row.summarized_output ?? row.error_message ?? ""))}</span> },
          ]}
        />
      )}

      <SectionTable
        title="Failures / Errors"
        icon={AlertTriangle}
        rows={failures}
        columns={[
          { key: "created_at", label: "Time", render: (row) => prettyDate(String(row.created_at ?? "")) },
          { key: "status", label: "Status", render: (row) => <StatusBadge value={String(row.status ?? "unknown")} /> },
          { key: "error_type", label: "Type" },
          { key: "error_message", label: "Message", render: (row) => <span className="text-muted-foreground">{truncate(String(row.error_message ?? ""))}</span> },
        ]}
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <SectionTable
          title="Execution Events"
          icon={Activity}
          rows={executionEvents}
          columns={[
            { key: "event_type", label: "Event" },
            { key: "symbol", label: "Symbol" },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={String(row.status ?? "unknown")} /> },
            { key: "created_at", label: "Time", render: (row) => prettyDate(String(row.created_at ?? "")) },
            { key: "summarized_output", label: "Summary", render: (row) => truncate(String(row.summarized_output ?? "")) },
          ]}
        />
        <SectionTable
          title="Movement Journal"
          icon={ArrowRightLeft}
          rows={movementRows}
          columns={[
            { key: "movement_type", label: "Movement" },
            { key: "symbol", label: "Symbol" },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={String(row.status ?? "unknown")} /> },
            { key: "quantity", label: "Qty", render: (row) => formatNumber(row.quantity as number | null | undefined) },
            { key: "cash_delta_usd", label: "Cash Δ", render: (row) => formatUsd(row.cash_delta_usd as number | null | undefined) },
            { key: "movement_time", label: "Time", render: (row) => prettyDate(String(row.movement_time ?? "")) },
          ]}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SectionTable
          title="Risk Rejections"
          icon={AlertTriangle}
          rows={dashboard.recent_risk_rejections}
          columns={[
            { key: "agent_name", label: "Agent" },
            { key: "decision", label: "Decision", render: (row) => <StatusBadge value={String(row.decision ?? row.status ?? "unknown")} /> },
            { key: "created_at", label: "Time", render: (row) => prettyDate(String(row.created_at ?? "")) },
            { key: "summarized_output", label: "Summary", render: (row) => truncate(String(row.summarized_output ?? "")) },
          ]}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <SectionTable
          title="Tool Call History"
          icon={Wrench}
          rows={toolCalls}
          columns={[
            { key: "tool_name", label: "Tool" },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={String(row.status ?? "unknown")} /> },
            { key: "created_at", label: "Time", render: (row) => prettyDate(String(row.created_at ?? "")) },
            { key: "summarized_output", label: "Summary", render: (row) => truncate(String(row.summarized_output ?? row.error_message ?? "")) },
          ]}
        />
        <SectionTable
          title="Agent Decisions"
          icon={Bot}
          rows={decisions}
          columns={[
            { key: "agent_name", label: "Agent" },
            { key: "decision", label: "Decision", render: (row) => <StatusBadge value={String(row.decision ?? row.status ?? "unknown")} /> },
            { key: "created_at", label: "Time", render: (row) => prettyDate(String(row.created_at ?? "")) },
            { key: "summarized_output", label: "Summary", render: (row) => truncate(String(row.summarized_output ?? "")) },
          ]}
        />
      </div>

      <SectionTable
        title="Recent Notifications"
        icon={Bell}
        rows={notifications}
        columns={[
          { key: "channel", label: "Channel" },
          { key: "delivered", label: "Delivered", render: (row) => <StatusBadge value={Boolean(row.delivered) ? "delivered" : "skipped"} /> },
          { key: "sent_time", label: "Time", render: (row) => prettyDate(String(row.sent_time ?? "")) },
          { key: "detail", label: "Detail", render: (row) => truncate(String(row.detail ?? "")) },
        ]}
      />

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Search className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-base">Event Timeline by Correlation ID</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex gap-3">
            <Input
              value={correlationId}
              onChange={(event) => setCorrelationId(event.target.value)}
              className="font-mono-ui"
              placeholder="corr_... or alert/workflow correlation id"
            />
            <Button
              type="button"
              onClick={() => { void loadTimeline(); }}
              variant="outline"
            >
              Load
            </Button>
          </div>
          <div className="grid gap-3">
            {timeline.length === 0 && <div className="text-sm text-muted-foreground">No timeline loaded.</div>}
            {timeline.map((item, index) => (
              <div key={`${item.kind}-${index}`} className="border border-border p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{item.kind}</Badge>
                    {"status" in item && typeof item.status === "string" ? <StatusBadge value={item.status} /> : null}
                  </div>
                  <span className="text-xs text-muted-foreground">{prettyDate(String(item.timestamp ?? ""))}</span>
                </div>
                <div className="mt-2 text-sm text-muted-foreground">{timelineSummary(item)}</div>
                <div className="mt-2 text-xs text-muted-foreground/80">{truncate(JSON.stringify(item), 320)}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {systemErrors.length > 0 && (
        <SectionTable
          title="System Errors (Current Run)"
          icon={AlertTriangle}
          rows={systemErrors}
          columns={[
            { key: "error_type", label: "Type" },
            { key: "status", label: "Status", render: (row) => <StatusBadge value={String(row.status ?? "unknown")} /> },
            { key: "created_at", label: "Time", render: (row) => prettyDate(String(row.created_at ?? "")) },
            { key: "error_message", label: "Message", render: (row) => truncate(String(row.error_message ?? "")) },
          ]}
        />
      )}
    </div>
  );
}
