import { useEffect, useState, useCallback } from "react";
import { ShieldCheck, ShieldX, Clock3, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { ApprovalRecord } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

function prettyDate(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getPendingApprovals(50);
      setApprovals(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  const handleApprove = async (id: string) => {
    setActing(id);
    try {
      await api.approveExecution(id);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Approve failed");
    } finally {
      setActing(null);
    }
  };

  const handleReject = async (id: string) => {
    setActing(id);
    try {
      await api.rejectExecution(id, "Operator rejected via dashboard");
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setActing(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold tracking-wider uppercase">
          Execution Approvals
        </h1>
        <button
          type="button"
          onClick={refresh}
          className="inline-flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs font-display uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Clock3 className="h-5 w-5 text-muted-foreground" />
            <CardTitle className="text-base">Pending Approvals</CardTitle>
            <Badge variant="outline" className="ml-2">
              {approvals.length}
            </Badge>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : approvals.length === 0 ? (
            <p className="text-sm text-muted-foreground">No pending approvals.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted-foreground">
                    <th className="py-2 pr-4 text-left font-medium">Symbol</th>
                    <th className="py-2 pr-4 text-left font-medium">Side</th>
                    <th className="py-2 pr-4 text-left font-medium">Amount</th>
                    <th className="py-2 pr-4 text-left font-medium">Created</th>
                    <th className="py-2 pr-4 text-left font-medium">Correlation</th>
                    <th className="py-2 pr-4 text-left font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {approvals.map((a) => (
                    <tr key={a.id} className="border-b border-border/50">
                      <td className="py-2 pr-4 font-mono text-xs">{a.symbol || "—"}</td>
                      <td className="py-2 pr-4">
                        <Badge
                          variant={
                            (a.side || "").toLowerCase() === "buy" ? "success" : "destructive"
                          }
                        >
                          {a.side || "—"}
                        </Badge>
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs">{a.amount ?? "—"}</td>
                      <td className="py-2 pr-4 text-xs text-muted-foreground">
                        {prettyDate(a.created_at)}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-muted-foreground">
                        {a.correlation_id
                          ? a.correlation_id.slice(0, 8) + "..."
                          : "—"}
                      </td>
                      <td className="py-2 pr-4">
                        <div className="flex gap-2">
                          <button
                            type="button"
                            disabled={acting === a.id}
                            onClick={() => handleApprove(a.id)}
                            className="inline-flex items-center gap-1 rounded border border-green-600/40 bg-green-600/10 px-2.5 py-1 text-xs font-medium text-green-400 hover:bg-green-600/20 disabled:opacity-50 transition-colors"
                          >
                            <ShieldCheck className="h-3 w-3" />
                            Approve
                          </button>
                          <button
                            type="button"
                            disabled={acting === a.id}
                            onClick={() => handleReject(a.id)}
                            className="inline-flex items-center gap-1 rounded border border-red-600/40 bg-red-600/10 px-2.5 py-1 text-xs font-medium text-red-400 hover:bg-red-600/20 disabled:opacity-50 transition-colors"
                          >
                            <ShieldX className="h-3 w-3" />
                            Reject
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
