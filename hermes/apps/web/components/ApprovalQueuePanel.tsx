"use client";

import { useState } from "react";
import { postHermesApi } from "../lib/hermes-api";

export type PendingApproval = {
  approval_id: string;
  status: string;
  symbol: string | null;
  side: string | null;
  amount: string | null;
  correlation_id: string | null;
  created_at: string | null;
};

type Props = {
  initialApprovals: PendingApproval[];
};

export function ApprovalQueuePanel({ initialApprovals }: Props) {
  const [approvals, setApprovals] = useState<PendingApproval[]>(initialApprovals);
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function handleAction(
    approvalId: string,
    action: "approve" | "reject",
    reason?: string,
  ) {
    setPending((p) => ({ ...p, [approvalId]: true }));
    setErrors((e) => ({ ...e, [approvalId]: "" }));

    const endpoint = `/execution/approvals/${approvalId}/${action}`;
    const body: Record<string, unknown> = { operator: "mission-control" };
    if (action === "reject" && reason) body.reason = reason;

    const result = await postHermesApi<{ approval: PendingApproval }>(endpoint, body);
    setPending((p) => ({ ...p, [approvalId]: false }));

    if (result.ok) {
      // Remove from the list — it's no longer pending
      setApprovals((prev) => prev.filter((a) => a.approval_id !== approvalId));
    } else {
      setErrors((e) => ({ ...e, [approvalId]: result.error ?? "Unknown error" }));
    }
  }

  if (approvals.length === 0) {
    return (
      <article className="card">
        <h2>Pending approvals</h2>
        <p className="muted">No execution requests awaiting approval.</p>
      </article>
    );
  }

  return (
    <article className="card">
      <h2>Pending approvals</h2>
      <p className="muted" style={{ marginBottom: "0.75rem" }}>
        {approvals.length} execution request{approvals.length !== 1 ? "s" : ""} awaiting operator
        review.
      </p>
      <ul className="list" style={{ gap: "0.75rem" }}>
        {approvals.map((approval) => (
          <li key={approval.approval_id} style={{ borderBottom: "1px solid #eee", paddingBottom: "0.75rem" }}>
            <strong>{approval.symbol ?? "Unknown"}</strong>{" "}
            <span className="muted">
              {approval.side ? approval.side.toUpperCase() : "—"}{" "}
              {approval.amount ? `${approval.amount}` : ""}
            </span>
            <div className="muted" style={{ fontSize: "0.8rem", marginTop: "0.2rem" }}>
              ID: {approval.approval_id.slice(0, 8)}…
              {approval.created_at
                ? ` · ${new Intl.DateTimeFormat("en-US", { dateStyle: "short", timeStyle: "short" }).format(new Date(approval.created_at))}`
                : ""}
            </div>
            {errors[approval.approval_id] && (
              <p style={{ color: "#e53e3e", fontSize: "0.8rem", margin: "0.25rem 0" }}>
                {errors[approval.approval_id]}
              </p>
            )}
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
              <button
                onClick={() => handleAction(approval.approval_id, "approve")}
                disabled={pending[approval.approval_id]}
                style={{
                  padding: "0.3rem 0.8rem",
                  background: "#38a169",
                  color: "#fff",
                  border: "none",
                  borderRadius: "4px",
                  cursor: pending[approval.approval_id] ? "not-allowed" : "pointer",
                  opacity: pending[approval.approval_id] ? 0.6 : 1,
                  fontSize: "0.85rem",
                }}
              >
                {pending[approval.approval_id] ? "…" : "Approve"}
              </button>
              <button
                onClick={() =>
                  handleAction(approval.approval_id, "reject", "Operator rejected via Mission Control")
                }
                disabled={pending[approval.approval_id]}
                style={{
                  padding: "0.3rem 0.8rem",
                  background: "#e53e3e",
                  color: "#fff",
                  border: "none",
                  borderRadius: "4px",
                  cursor: pending[approval.approval_id] ? "not-allowed" : "pointer",
                  opacity: pending[approval.approval_id] ? 0.6 : 1,
                  fontSize: "0.85rem",
                }}
              >
                {pending[approval.approval_id] ? "…" : "Reject"}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </article>
  );
}
