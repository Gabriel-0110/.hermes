"use client";

import { useState } from "react";
import { postHermesApi } from "../lib/hermes-api";

type SyncState = {
  syncing: boolean;
  lastResult: string | null;
  error: string | null;
};

export function PortfolioSyncButton() {
  const [state, setState] = useState<SyncState>({
    syncing: false,
    lastResult: null,
    error: null,
  });

  async function sync() {
    setState({ syncing: true, lastResult: null, error: null });
    const result = await postHermesApi<{ sync: { data: { total_equity_usd: number | null } } }>(
      "/portfolio/sync",
    );
    if (result.ok && result.data) {
      const equity = result.data.sync?.data?.total_equity_usd;
      setState({
        syncing: false,
        lastResult: equity != null ? `Equity: $${equity.toFixed(2)}` : "Synced (equity unknown)",
        error: null,
      });
    } else {
      setState({ syncing: false, lastResult: null, error: result.error });
    }
  }

  return (
    <div style={{ marginTop: "0.5rem" }}>
      <button
        onClick={sync}
        disabled={state.syncing}
        style={{
          padding: "0.4rem 1rem",
          background: "#3182ce",
          color: "#fff",
          border: "none",
          borderRadius: "4px",
          cursor: state.syncing ? "not-allowed" : "pointer",
          opacity: state.syncing ? 0.6 : 1,
        }}
      >
        {state.syncing ? "Syncing…" : "Sync live balances"}
      </button>
      {state.lastResult && (
        <p style={{ marginTop: "0.25rem", color: "#38a169" }}>{state.lastResult}</p>
      )}
      {state.error && (
        <p style={{ marginTop: "0.25rem", color: "#e53e3e" }}>{state.error}</p>
      )}
    </div>
  );
}
