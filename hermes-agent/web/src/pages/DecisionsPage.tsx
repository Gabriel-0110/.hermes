import { useEffect, useState, useCallback } from "react";
import { FileText, RefreshCw, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface PolicyTrace {
  id: string;
  proposal_id: string;
  status: string;
  execution_mode: string;
  approved: boolean;
  symbol?: string | null;
  trace: string[];
  rejection_reasons: string[];
  created_at?: string | null;
}

function prettyDate(value?: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function statusBadge(status: string, approved: boolean) {
  if (status === "approved")
    return <Badge className="bg-green-600 text-white">Approved</Badge>;
  if (status === "manual_review")
    return <Badge className="bg-yellow-600 text-white">Manual Review</Badge>;
  if (status === "rejected")
    return <Badge className="bg-red-600 text-white">Rejected</Badge>;
  return <Badge variant="outline">{status}</Badge>;
}

function statusIcon(status: string) {
  if (status === "approved") return <CheckCircle2 className="h-4 w-4 text-green-500" />;
  if (status === "rejected") return <XCircle className="h-4 w-4 text-red-500" />;
  return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
}

export default function DecisionsPage() {
  const [traces, setTraces] = useState<PolicyTrace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/policy/traces?limit=50");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: PolicyTrace[] = await res.json();
      setTraces(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load decisions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 10000);
    return () => clearInterval(interval);
  }, [refresh]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <FileText className="h-6 w-6" />
          Policy Decisions
        </h1>
        <button
          onClick={refresh}
          disabled={loading}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-sm border rounded-md hover:bg-muted"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error && (
        <Card className="border-red-300 bg-red-50">
          <CardContent className="pt-4 text-red-700 text-sm">{error}</CardContent>
        </Card>
      )}

      {!loading && traces.length === 0 && !error && (
        <Card>
          <CardContent className="pt-6 text-center text-muted-foreground">
            No policy decisions recorded yet.
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {traces.map((t) => (
          <Card key={t.id}>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  {statusIcon(t.status)}
                  <span className="font-mono">{t.symbol || "?"}</span>
                  {statusBadge(t.status, t.approved)}
                  <Badge variant="outline">{t.execution_mode}</Badge>
                </CardTitle>
                <span className="text-xs text-muted-foreground">
                  {prettyDate(t.created_at)}
                </span>
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              <div className="text-xs text-muted-foreground mb-1">
                Proposal: <span className="font-mono">{t.proposal_id}</span>
              </div>
              <div className="flex flex-wrap gap-1 mt-1">
                {t.trace.map((entry, i) => (
                  <Badge key={i} variant="secondary" className="text-xs font-mono">
                    {entry}
                  </Badge>
                ))}
              </div>
              {t.rejection_reasons.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {t.rejection_reasons.map((r, i) => (
                    <Badge key={i} className="bg-red-100 text-red-800 text-xs">
                      {r}
                    </Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
