"use client";
import React from "react";
import { useHermesData } from "@/hooks/useHermesData";
import Badge from "../ui/badge/Badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "../ui/table";

interface ExecutionData {
  status: string;
  execution: {
    exchange: string;
    trading_mode: string;
    live_trading_enabled: boolean;
    recent_execution_events: Array<{
      id: string;
      event_type: string;
      status: string;
      created_at: string;
      error_message: string | null;
      summarized_output: string;
      tool_name: string | null;
    }>;
  };
  events: Array<{
    id: string;
    event_type: string;
    status: string;
    created_at: string;
    error_message: string | null;
    summarized_output: string;
    tool_name: string | null;
    metadata?: Record<string, string>;
  }>;
  movements: Array<{
    id: string;
    symbol: string;
    side: string;
    amount: number;
    price: number;
    status: string;
    created_at: string;
  }>;
}

function formatTimeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${diffDay}d ago`;
}

function parseEventType(type: string): string {
  return type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusColor(status: string): "success" | "warning" | "error" | "info" {
  switch (status) {
    case "delivered":
    case "completed":
    case "filled":
      return "success";
    case "pending":
    case "in_progress":
      return "warning";
    case "failed":
    case "error":
    case "rejected":
      return "error";
    default:
      return "info";
  }
}

export default function RecentExecutions() {
  const { data, loading } = useHermesData<ExecutionData>("/api/execution", 15000);

  const events = [
    ...(data?.events ?? []),
    ...(data?.execution?.recent_execution_events ?? []),
  ];

  // Deduplicate by id
  const seen = new Set<string>();
  const uniqueEvents = events.filter((e) => {
    if (seen.has(e.id)) return false;
    seen.add(e.id);
    return true;
  });

  // Sort by created_at desc
  uniqueEvents.sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  const displayEvents = uniqueEvents.slice(0, 10);

  return (
    <div className="overflow-hidden rounded-2xl border border-gray-200 bg-white px-4 pb-3 pt-4 dark:border-gray-800 dark:bg-white/[0.03] sm:px-6">
      <div className="flex flex-col gap-2 mb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-800 dark:text-white/90">
            Recent Executions
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {data?.execution?.exchange ?? "..."} &middot;{" "}
            {data?.execution?.trading_mode ?? "..."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge
            color={data?.execution?.live_trading_enabled ? "success" : "warning"}
          >
            {data?.execution?.live_trading_enabled ? "Live" : "Paper"}
          </Badge>
        </div>
      </div>
      <div className="max-w-full overflow-x-auto">
        <Table>
          <TableHeader className="border-gray-100 dark:border-gray-800 border-y">
            <TableRow>
              <TableCell
                isHeader
                className="py-3 font-medium text-gray-500 text-start text-theme-xs dark:text-gray-400"
              >
                Event
              </TableCell>
              <TableCell
                isHeader
                className="py-3 font-medium text-gray-500 text-start text-theme-xs dark:text-gray-400"
              >
                Status
              </TableCell>
              <TableCell
                isHeader
                className="py-3 font-medium text-gray-500 text-start text-theme-xs dark:text-gray-400"
              >
                Tool
              </TableCell>
              <TableCell
                isHeader
                className="py-3 font-medium text-gray-500 text-start text-theme-xs dark:text-gray-400"
              >
                Time
              </TableCell>
            </TableRow>
          </TableHeader>
          <TableBody className="divide-y divide-gray-100 dark:divide-gray-800">
            {loading ? (
              <TableRow>
                <TableCell className="py-6 text-center text-gray-400" colSpan={4}>
                  Loading...
                </TableCell>
              </TableRow>
            ) : displayEvents.length === 0 ? (
              <TableRow>
                <TableCell className="py-6 text-center text-gray-400" colSpan={4}>
                  No recent execution events
                </TableCell>
              </TableRow>
            ) : (
              displayEvents.map((event) => (
                <TableRow key={event.id}>
                  <TableCell className="py-3">
                    <p className="font-medium text-gray-800 text-theme-sm dark:text-white/90">
                      {parseEventType(event.event_type)}
                    </p>
                    {event.error_message && (
                      <span className="text-error-500 text-theme-xs">
                        {event.error_message}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="py-3">
                    <Badge size="sm" color={statusColor(event.status)}>
                      {event.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-3 text-gray-500 text-theme-sm dark:text-gray-400">
                    {event.tool_name ?? "-"}
                  </TableCell>
                  <TableCell className="py-3 text-gray-500 text-theme-sm dark:text-gray-400">
                    {formatTimeAgo(event.created_at)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
