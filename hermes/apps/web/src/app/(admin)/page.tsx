"use client";
import React from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/hooks/useApi";
import PageHeader from "@/components/ui/PageHeader";
import MetricCard from "@/components/ui/MetricCard";
import ModuleCard from "@/components/ui/ModuleCard";
import KillSwitchIndicator from "@/components/ui/KillSwitchIndicator";
import PositionCard from "@/components/desk/PositionCard";
import Badge from "@/components/ui/Badge";
import LoadingState from "@/components/ui/LoadingState";
import ErrorState from "@/components/ui/ErrorState";

export default function TradingDeskPage() {
  const portfolio = usePolling(api.portfolio.state, 15000);
  const risk = usePolling(api.risk.dashboard, 15000);
  const execution = usePolling(api.execution.surface, 30000);
  const rejections = usePolling(api.risk.rejections, 30000);

  const loading = portfolio.loading && risk.loading;
  const error = portfolio.error && risk.error;

  if (loading) return <LoadingState label="Connecting to Hermes" />;

  const pState = portfolio.data;
  const rState = risk.data;
  const positions = pState?.positions ?? rState?.positions ?? [];
  const killSwitch = rState?.kill_switch ?? { active: false };
  const totalEquity = pState?.total_equity_usd ?? 0;
  const availableBalance = pState?.available_balance_usd ?? 0;
  const totalPnl = positions.reduce(
    (sum, p) => sum + (p.unrealized_pnl ?? 0),
    0
  );
  const pendingSignals = execution.data?.pending_signals ?? [];

  return (
    <>
      <PageHeader
        title="Trading Desk"
        code="/00"
        subtitle="Operator command surface — portfolio, positions, and system status"
        action={
          <KillSwitchIndicator
            active={killSwitch.active}
            reason={killSwitch.reason}
          />
        }
      />

      {error && !pState && (
        <ErrorState
          message={error}
          onRetry={() => {
            portfolio.refetch();
            risk.refetch();
          }}
        />
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <MetricCard
          label="Total Equity"
          value={`$${totalEquity.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
        />
        <MetricCard
          label="Available Balance"
          value={`$${availableBalance.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
        />
        <MetricCard
          label="Unrealized PnL"
          value={`${totalPnl >= 0 ? "+" : ""}$${totalPnl.toFixed(2)}`}
          trend={totalPnl >= 0 ? "up" : "down"}
        />
        <MetricCard
          label="Open Positions"
          value={String(positions.length)}
          subValue={`${pendingSignals.length} pending signals`}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-6">
        <ModuleCard
          title="Positions"
          subtitle={`${positions.length} active`}
        >
          {positions.length === 0 ? (
            <div className="py-10 text-center">
              <div className="rounded-xl border border-dashed border-gray-200 p-8">
                <p className="text-sm font-bold text-white mb-1">
                  No Open Positions
                </p>
                <p className="text-xs text-gray-500">
                  Positions will appear here when trades are executed.
                </p>
              </div>
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
          <ModuleCard title="System Status">
            <div className="space-y-3">
              <StatusRow label="Trading Mode" value="PAPER" color="text-warning-400" />
              <StatusRow label="Exchange" value="BITMART" />
              <StatusRow label="Kill Switch" value={killSwitch.active ? "ACTIVE" : "INACTIVE"} color={killSwitch.active ? "text-error-400" : "text-success-400"} />
              <StatusRow label="Last Sync" value={pState?.last_sync ? new Date(pState.last_sync).toLocaleTimeString() : "—"} />
            </div>
          </ModuleCard>

          <ModuleCard title="Pending Signals">
            {pendingSignals.length === 0 ? (
              <p className="text-xs text-gray-500 py-4 text-center">
                No pending signals
              </p>
            ) : (
              <div className="space-y-2">
                {pendingSignals.slice(0, 5).map((sig, i) => (
                  <div
                    key={sig.id ?? i}
                    className="flex items-center justify-between py-2 border-b border-gray-200/50 last:border-0"
                  >
                    <div className="flex items-center gap-2">
                      <Badge
                        color={
                          sig.direction === "long" ? "success" : "error"
                        }
                      >
                        {sig.direction}
                      </Badge>
                      <span className="font-mono text-xs text-white">
                        {sig.symbol}
                      </span>
                    </div>
                    <span className="font-mono text-xs text-gray-400">
                      {sig.signal}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </ModuleCard>

          <ModuleCard title="Recent Activity">
            {(rejections.data ?? []).length === 0 ? (
              <p className="text-xs text-gray-500 py-4 text-center">
                No recent activity
              </p>
            ) : (
              <div className="space-y-2">
                {(rejections.data ?? []).slice(0, 5).map((rej, i) => (
                  <div
                    key={rej.id ?? i}
                    className="flex items-center gap-2 py-1.5 border-b border-gray-200/50 last:border-0"
                  >
                    <span className="w-0.5 h-4 rounded bg-error-400/40" />
                    <div className="flex-1 min-w-0">
                      <span className="font-mono text-xs text-error-400 truncate block">
                        {rej.symbol} — {rej.reason}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </ModuleCard>
        </div>
      </div>
    </>
  );
}

function StatusRow({
  label,
  value,
  color = "text-white",
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-gray-200/30 last:border-0">
      <span className="font-mono text-[0.6rem] uppercase tracking-wider text-gray-500">
        {label}
      </span>
      <span className={`font-mono text-xs font-semibold ${color}`}>
        {value}
      </span>
    </div>
  );
}
