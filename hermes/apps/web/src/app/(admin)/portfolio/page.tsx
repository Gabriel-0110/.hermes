"use client";
import React from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/hooks/useApi";
import PageHeader from "@/components/ui/PageHeader";
import ModuleCard from "@/components/ui/ModuleCard";
import MetricCard from "@/components/ui/MetricCard";
import PositionCard from "@/components/desk/PositionCard";
import LoadingState from "@/components/ui/LoadingState";
import { RefreshIcon } from "@/icons";

export default function PortfolioPage() {
  const portfolio = usePolling(api.portfolio.state, 15000);

  if (portfolio.loading) return <LoadingState label="Loading portfolio" />;

  const state = portfolio.data;
  const positions = state?.positions ?? [];
  const totalEquity = state?.total_equity_usd ?? 0;
  const available = state?.available_balance_usd ?? 0;
  const totalPnl = positions.reduce(
    (sum, p) => sum + (p.unrealized_pnl ?? 0),
    0
  );
  const usedMargin = totalEquity - available;

  const handleSync = async () => {
    try {
      await api.portfolio.sync();
      portfolio.refetch();
    } catch {
      // silent
    }
  };

  return (
    <>
      <PageHeader
        title="Portfolio"
        code="/03"
        subtitle="Balances, positions, allocation, and reconciliation"
        action={
          <button
            onClick={handleSync}
            className="inline-flex items-center gap-2 font-mono text-[0.65rem] uppercase tracking-[0.14em] text-brand-400 border border-brand-300 rounded px-4 py-1.5 hover:bg-brand-50 transition-all hover:-translate-y-px"
          >
            <RefreshIcon className="w-3.5 h-3.5" />
            Sync Now
          </button>
        }
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <MetricCard label="Total Equity" value={`$${totalEquity.toFixed(2)}`} />
        <MetricCard label="Available Balance" value={`$${available.toFixed(2)}`} />
        <MetricCard
          label="Used Margin"
          value={`$${usedMargin.toFixed(2)}`}
        />
        <MetricCard
          label="Unrealized PnL"
          value={`${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(2)}`}
          trend={totalPnl >= 0 ? "up" : "down"}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_340px] gap-6">
        <ModuleCard title="Positions" subtitle={`${positions.length} active`}>
          {positions.length === 0 ? (
            <div className="py-10 text-center rounded-xl border border-dashed border-gray-200 mx-auto">
              <p className="text-sm font-bold text-white mb-1">No Open Positions</p>
              <p className="text-xs text-gray-500">Execute a trade to see positions here.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {positions.map((pos, i) => (
                <PositionCard key={pos.symbol ?? i} pos={pos} />
              ))}
            </div>
          )}
        </ModuleCard>

        <div className="flex flex-col gap-6">
          <ModuleCard title="Allocation">
            <div className="space-y-3">
              {positions.length === 0 ? (
                <p className="text-xs text-gray-500 py-4 text-center">No positions to display</p>
              ) : (
                positions.map((pos, i) => {
                  const exposure = Math.abs(
                    (pos.mark_price ?? 0) * (pos.size ?? 0)
                  );
                  const pct = totalEquity > 0 ? (exposure / totalEquity) * 100 : 0;
                  return (
                    <div key={pos.symbol ?? i}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-mono text-xs text-white">
                          {pos.symbol?.replace("/USDT:USDT", "")}
                        </span>
                        <span className="font-mono text-[0.6rem] text-gray-400">
                          {pct.toFixed(1)}%
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-gray-800 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-brand-400"
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </ModuleCard>

          <ModuleCard title="Sync Info">
            <div className="space-y-2">
              <InfoRow label="Last Sync" value={state?.last_sync ? new Date(state.last_sync).toLocaleString() : "Never"} />
              <InfoRow label="Exchange" value="BitMart" />
              <InfoRow label="Account" value="Swap / Cross" />
            </div>
          </ModuleCard>
        </div>
      </div>
    </>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-gray-200/30 last:border-0">
      <span className="font-mono text-[0.6rem] uppercase tracking-wider text-gray-500">{label}</span>
      <span className="font-mono text-xs text-white">{value}</span>
    </div>
  );
}
