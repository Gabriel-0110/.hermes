"use client";

import { useState } from "react";
import { postHermesApi } from "../lib/hermes-api";

type KillSwitchState = {
  active: boolean;
  reason?: string | null;
  updated_at?: string | null;
};

type Props = {
  initialState: KillSwitchState;
  variant?: "default" | "mission";
};

export function KillSwitchPanel({ initialState, variant = "default" }: Props) {
  const [state, setState] = useState<KillSwitchState>(initialState);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setPending(true);
    setError(null);
    const endpoint = state.active
      ? "/risk/kill-switch/deactivate"
      : "/risk/kill-switch/activate";
    const result = await postHermesApi<{ kill_switch: KillSwitchState }>(
      endpoint,
      state.active
        ? { operator: "mission-control" }
        : {
            reason: "Operator activated via Mission Control",
            operator: "mission-control",
          },
    );
    setPending(false);
    if (result.ok && result.data) {
      setState(result.data.kill_switch);
    } else {
      setError(result.error);
    }
  }

  if (variant === "mission") {
    return (
      <div className="mission-control-panel">
        <p className={`mission-control-status ${state.active ? "tone-loss" : "tone-gain"}`}>
          {state.active ? "ACTIVE — approvals blocked" : "INACTIVE — normal operation"}
        </p>
        {state.reason ? <p className="muted mission-control-copy">{state.reason}</p> : null}
        {state.updated_at ? (
          <p className="muted mission-control-copy">
            Last changed: {" "}
            {new Intl.DateTimeFormat("en-US", {
              dateStyle: "medium",
              timeStyle: "short",
            }).format(new Date(state.updated_at))}
          </p>
        ) : null}
        {error ? <p className="mission-control-error">{error}</p> : null}
        <div className="mission-inline-actions">
          <button
            onClick={toggle}
            disabled={pending}
            className={`mission-action-button ${state.active ? "tone-gain" : "tone-loss"}`}
          >
            {pending
              ? "Working…"
              : state.active
                ? "Deactivate kill switch"
                : "Activate kill switch"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <article className="card">
      <h2>Kill switch</h2>
      <p
        className="status"
        style={{ color: state.active ? "#e53e3e" : "#38a169" }}
      >
        {state.active ? "ACTIVE — all approvals blocked" : "Inactive — normal operation"}
      </p>
      {state.reason && <p className="muted">{state.reason}</p>}
      {state.updated_at && (
        <p className="muted">
          Last changed:{" "}
          {new Intl.DateTimeFormat("en-US", {
            dateStyle: "medium",
            timeStyle: "short",
          }).format(new Date(state.updated_at))}
        </p>
      )}
      {error && <p style={{ color: "#e53e3e" }}>{error}</p>}
      <button
        onClick={toggle}
        disabled={pending}
        style={{
          marginTop: "0.75rem",
          padding: "0.4rem 1rem",
          background: state.active ? "#38a169" : "#e53e3e",
          color: "#fff",
          border: "none",
          borderRadius: "4px",
          cursor: pending ? "not-allowed" : "pointer",
          opacity: pending ? 0.6 : 1,
        }}
      >
        {pending
          ? "Working…"
          : state.active
            ? "Deactivate kill switch"
            : "Activate kill switch"}
      </button>
    </article>
  );
}
