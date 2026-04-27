"use client";
import React from "react";
import { api } from "@/lib/api";
import { usePolling } from "@/hooks/useApi";
import PageHeader from "@/components/ui/PageHeader";
import ModuleCard from "@/components/ui/ModuleCard";
import Badge from "@/components/ui/Badge";
import LoadingState from "@/components/ui/LoadingState";
import type { TradeCandidateScore } from "@/lib/api";

const strategies = [
  { name: "Momentum", description: "RSI, MA crossover, MACD, regime-aware directional signals", color: "#22c55e" },
  { name: "Mean Reversion", description: "RSI extremes, z-score, Bollinger Bands mean-revert setups", color: "#38bdf8" },
  { name: "Breakout", description: "ATR expansion, volume surge, BB squeeze breakout detection", color: "#a78bfa" },
  { name: "Delta-Neutral Carry", description: "Funding rate harvest, spot/perp basis capture", color: "#ffc86e" },
  { name: "Whale Follower", description: "On-chain whale accumulation tracking and mirroring", color: "#ff6b82" },
];

export default function StrategyPage() {
  const candidates = usePolling(api.risk.candidates, 30000);

  if (candidates.loading) return <LoadingState label="Loading strategy data" />;

  const scored = candidates.data ?? [];

  return (
    <>
      <PageHeader
        title="Strategy"
        code="/06"
        subtitle="Strategy library, scored candidates, and forecast projections"
      />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-6">
        {strategies.map((s) => {
          const matching = scored.filter(
            (c) =>
              c.strategy_name?.toLowerCase().includes(s.name.toLowerCase().split(" ")[0])
          );
          const topConfidence = matching.length > 0
            ? Math.max(...matching.map((c) => c.confidence))
            : 0;

          return (
            <div key={s.name} className="hermes-module">
              <div className="relative px-5 py-4 border-b border-gray-200 bg-surface-high/50">
                <div
                  className="absolute top-0 left-0 w-full h-[2px]"
                  style={{ background: `linear-gradient(90deg, ${s.color}, ${s.color}44)` }}
                />
                <h3 className="text-sm font-bold text-white">{s.name}</h3>
                <p className="text-xs text-gray-500 mt-1">{s.description}</p>
              </div>
              <div className="p-5">
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div>
                    <div className="font-mono text-[0.5rem] uppercase tracking-wider text-gray-600">
                      Candidates
                    </div>
                    <div className="font-mono text-lg font-bold text-white">
                      {matching.length}
                    </div>
                  </div>
                  <div>
                    <div className="font-mono text-[0.5rem] uppercase tracking-wider text-gray-600">
                      Top Confidence
                    </div>
                    <div className={`font-mono text-lg font-bold ${
                      topConfidence >= 0.7 ? "text-success-400" : topConfidence >= 0.5 ? "text-warning-400" : "text-gray-400"
                    }`}>
                      {topConfidence > 0 ? `${(topConfidence * 100).toFixed(0)}%` : "—"}
                    </div>
                  </div>
                </div>

                {matching.length > 0 && (
                  <div className="space-y-1.5 pt-3 border-t border-gray-200/30">
                    {matching.slice(0, 3).map((c, i) => (
                      <div
                        key={i}
                        className="flex items-center justify-between py-1"
                      >
                        <div className="flex items-center gap-2">
                          <Badge
                            color={
                              c.direction === "long"
                                ? "success"
                                : c.direction === "short"
                                  ? "error"
                                  : "gray"
                            }
                          >
                            {c.direction}
                          </Badge>
                          <span className="font-mono text-xs text-white">
                            {c.symbol}
                          </span>
                        </div>
                        <span className="font-mono text-[0.65rem] text-gray-400">
                          {(c.confidence * 100).toFixed(0)}%
                          {c.chronos_score != null && (
                            <span className="text-brand-400 ml-1">
                              C:{c.chronos_score.toFixed(1)}
                            </span>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <ModuleCard title="All Scored Candidates" subtitle="Cross-strategy trade evaluation">
        {scored.length === 0 ? (
          <div className="py-10 text-center">
            <p className="font-mono text-xs text-gray-500">
              No candidates currently scored. Strategy evaluator runs periodically.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto custom-scrollbar">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  {["Symbol", "Strategy", "Direction", "Confidence", "Chronos"].map(
                    (h) => (
                      <th
                        key={h}
                        className="py-2.5 px-3 font-mono text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-gray-500 text-left"
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {scored.map((c, i) => (
                  <tr
                    key={i}
                    className="border-b border-gray-200/50 hover:bg-brand-50/50 transition-colors"
                  >
                    <td className="py-2.5 px-3 font-mono text-xs text-white">
                      {c.symbol}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-xs text-gray-400">
                      {c.strategy_name}
                    </td>
                    <td className="py-2.5 px-3">
                      <Badge
                        color={
                          c.direction === "long"
                            ? "success"
                            : c.direction === "short"
                              ? "error"
                              : "gray"
                        }
                      >
                        {c.direction}
                      </Badge>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-xs">
                      <span
                        className={
                          c.confidence >= 0.7
                            ? "text-success-400"
                            : c.confidence >= 0.5
                              ? "text-warning-400"
                              : "text-gray-400"
                        }
                      >
                        {(c.confidence * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-xs text-gray-400">
                      {c.chronos_score != null
                        ? c.chronos_score.toFixed(2)
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ModuleCard>
    </>
  );
}
