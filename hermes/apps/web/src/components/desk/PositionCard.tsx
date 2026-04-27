"use client";
import React from "react";
import Badge from "@/components/ui/Badge";
import Sparkline from "@/components/ui/Sparkline";
import type { PositionSnapshot } from "@/lib/api";

function generateSparkData(seed: number, len = 20): number[] {
  const data: number[] = [seed];
  for (let i = 1; i < len; i++) {
    data.push(data[i - 1] + (Math.sin(seed * i * 0.3) * 2 + (Math.random() - 0.5)));
  }
  return data;
}

const sideColors: Record<string, { accent: string; badge: "success" | "error" | "brand" }> = {
  long: { accent: "#22c55e", badge: "success" },
  short: { accent: "#f43f5e", badge: "error" },
  grid: { accent: "#38bdf8", badge: "brand" },
};

export default function PositionCard({ pos }: { pos: PositionSnapshot }) {
  const side = (pos.side ?? "long").toLowerCase();
  const colors = sideColors[side] ?? sideColors.long;
  const pnl = pos.unrealized_pnl ?? 0;
  const pnlPct = pos.unrealized_pnl_pct ?? 0;
  const isProfit = pnl >= 0;
  const sparkData = generateSparkData(pnl * 100 + (pos.entry_price ?? 1));

  return (
    <div className="relative rounded-xl border border-gray-200 bg-desk-surface overflow-hidden">
      <div
        className="h-[3px]"
        style={{
          background: `linear-gradient(90deg, ${colors.accent}, ${colors.accent}88)`,
        }}
      />
      <div className="p-4">
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="text-base font-bold text-white">
              {pos.symbol?.replace("/USDT:USDT", "") ?? "—"}
            </div>
            <div className="font-mono text-[0.6rem] uppercase text-gray-500 mt-0.5">
              {pos.leverage ?? 1}x · {pos.symbol ?? ""}
            </div>
          </div>
          <Badge color={colors.badge}>
            {side.toUpperCase()}
          </Badge>
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-2 mb-3">
          <StatCell label="Entry" value={formatPrice(pos.entry_price)} />
          <StatCell label="Mark" value={formatPrice(pos.mark_price)} />
          <StatCell label="Size" value={pos.size?.toFixed(4) ?? "—"} />
          <StatCell label="Leverage" value={`${pos.leverage ?? 1}x`} />
        </div>

        <div className="mb-3">
          <Sparkline
            data={sparkData}
            color={isProfit ? "#22c55e" : "#f43f5e"}
            width={200}
            height={28}
          />
        </div>

        <div className="h-[5px] rounded-full bg-gray-800 overflow-hidden mb-2">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${Math.min(Math.abs(pnlPct) * 10, 100)}%`,
              background: isProfit
                ? "linear-gradient(90deg, #22c55e, #16a34a)"
                : "linear-gradient(90deg, #f43f5e, #dc2626)",
            }}
          />
        </div>

        <div className="flex items-center justify-between">
          <span className="font-mono text-[0.55rem] uppercase text-gray-500">
            Unrealized PnL
          </span>
          <span
            className={`font-mono text-sm font-bold ${
              isProfit ? "text-success-400" : "text-error-400"
            }`}
          >
            {isProfit ? "+" : ""}
            {pnl.toFixed(2)} USD ({pnlPct.toFixed(2)}%)
          </span>
        </div>
      </div>
    </div>
  );
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-[0.5rem] uppercase tracking-wider text-gray-600">
        {label}
      </div>
      <div className="font-mono text-xs text-white">{value}</div>
    </div>
  );
}

function formatPrice(price?: number): string {
  if (price == null) return "—";
  return price >= 1000
    ? price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : price.toFixed(4);
}
