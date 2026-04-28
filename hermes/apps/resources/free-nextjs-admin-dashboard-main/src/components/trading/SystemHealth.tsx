"use client";
import React from "react";
import { useHermesData } from "@/hooks/useHermesData";
import Badge from "../ui/badge/Badge";

interface ObservabilityData {
  status: string;
  dashboard: {
    recent_workflow_runs: Array<{
      id: string;
      workflow_name: string;
      status: string;
      created_at: string;
    }>;
    recent_failures: Array<{
      id: string;
      error_message: string;
      error_type: string;
      tool_name: string | null;
      status: string;
      created_at: string;
      updated_at: string;
    }>;
  };
}

function formatTimeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);

  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
}

export default function SystemHealth() {
  const { data, loading } = useHermesData<ObservabilityData>(
    "/api/observability",
    30000
  );

  const failures = data?.dashboard?.recent_failures ?? [];
  const workflows = data?.dashboard?.recent_workflow_runs ?? [];

  // Group failures by error type
  const failureGroups = failures.reduce<Record<string, number>>((acc, f) => {
    const key = f.tool_name ?? f.error_type ?? "unknown";
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03] sm:p-6">
      <div className="flex justify-between mb-6">
        <div>
          <h3 className="text-lg font-semibold text-gray-800 dark:text-white/90">
            System Health
          </h3>
          <p className="mt-1 text-gray-500 text-theme-sm dark:text-gray-400">
            Recent failures & workflows
          </p>
        </div>
        <Badge color={failures.length === 0 ? "success" : "warning"}>
          {failures.length === 0 ? "All Clear" : `${failures.length} issues`}
        </Badge>
      </div>

      {loading ? (
        <div className="text-center py-8 text-gray-400">Loading...</div>
      ) : (
        <>
          {/* Failure summary */}
          {Object.keys(failureGroups).length > 0 && (
            <div className="mb-6">
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                Recent Errors
              </h4>
              <div className="space-y-2">
                {Object.entries(failureGroups).map(([tool, count]) => (
                  <div
                    key={tool}
                    className="flex items-center justify-between p-3 rounded-xl bg-error-50/50 dark:bg-error-500/5"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-error-500 text-sm">●</span>
                      <span className="text-sm text-gray-700 dark:text-gray-300 font-medium">
                        {tool}
                      </span>
                    </div>
                    <Badge size="sm" color="error">
                      {count}x
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Latest failure details */}
          {failures.length > 0 && (
            <div className="mb-6">
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                Latest Failures
              </h4>
              <div className="space-y-2 max-h-[200px] overflow-y-auto">
                {failures.slice(0, 5).map((f) => (
                  <div
                    key={f.id}
                    className="p-3 rounded-xl bg-gray-50 dark:bg-gray-800/50"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                        {f.tool_name ?? f.error_type}
                      </span>
                      <span className="text-xs text-gray-400">
                        {formatTimeAgo(f.created_at)}
                      </span>
                    </div>
                    <p className="text-sm text-error-500 line-clamp-2">
                      {f.error_message}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Workflow runs */}
          {workflows.length > 0 ? (
            <div>
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                Recent Workflows
              </h4>
              <div className="space-y-2">
                {workflows.slice(0, 5).map((w) => (
                  <div
                    key={w.id}
                    className="flex items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-gray-800/50"
                  >
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      {w.workflow_name}
                    </span>
                    <div className="flex items-center gap-2">
                      <Badge
                        size="sm"
                        color={
                          w.status === "completed"
                            ? "success"
                            : w.status === "failed"
                            ? "error"
                            : "warning"
                        }
                      >
                        {w.status}
                      </Badge>
                      <span className="text-xs text-gray-400">
                        {formatTimeAgo(w.created_at)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            failures.length === 0 && (
              <div className="text-center py-8">
                <p className="text-gray-400 text-sm">
                  No recent activity to display
                </p>
              </div>
            )
          )}
        </>
      )}
    </div>
  );
}
