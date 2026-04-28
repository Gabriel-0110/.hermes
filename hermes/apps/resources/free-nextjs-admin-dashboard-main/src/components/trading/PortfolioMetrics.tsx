"use client";
import React from "react";
import Badge from "../ui/badge/Badge";
import { ArrowUpIcon, ArrowDownIcon } from "@/icons";
import { useHermesData } from "@/hooks/useHermesData";

interface PortfolioData {
  status: string;
  portfolio: {
    data: {
      total_equity_usd: number;
      cash_usd: number;
      positions: Array<{
        symbol: string;
        side: string;
        size: number;
        entry_price: number;
        mark_price: number;
        unrealized_pnl: number;
        notional_usd: number;
      }>;
      snapshot_metadata?: {
        exchange: string;
        account_type: string;
        as_of: string;
        positions_count: number;
      };
    };
  };
}

interface RiskData {
  status: string;
  risk: {
    kill_switch: {
      active: boolean;
      reason: string | null;
    };
    execution_safety: {
      execution_mode: string;
      live_allowed: boolean;
      blockers: string[];
    };
    position_monitor: {
      risk_summary: {
        total_positions: number;
        cash_buffer_pct: number;
        gross_exposure_pct: number | null;
        warnings: string[];
      };
    };
  };
}

export default function PortfolioMetrics() {
  const { data: portfolio, loading: pLoading } =
    useHermesData<PortfolioData>("/api/portfolio");
  const { data: risk, loading: rLoading } =
    useHermesData<RiskData>("/api/risk");

  const equity = portfolio?.portfolio?.data?.total_equity_usd ?? 0;
  const cash = portfolio?.portfolio?.data?.cash_usd ?? 0;
  const posCount =
    portfolio?.portfolio?.data?.positions?.length ??
    portfolio?.portfolio?.data?.snapshot_metadata?.positions_count ??
    0;
  const mode = portfolio?.status ?? "unknown";
  const killSwitch = risk?.risk?.kill_switch?.active ?? false;
  const liveAllowed = risk?.risk?.execution_safety?.live_allowed ?? false;
  const exposurePct = risk?.risk?.position_monitor?.risk_summary?.gross_exposure_pct;
  const cashBuffer = risk?.risk?.position_monitor?.risk_summary?.cash_buffer_pct ?? 0;

  const isLoading = pLoading || rLoading;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 md:gap-6">
      {/* Total Equity */}
      <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03] md:p-6">
        <div className="flex items-center justify-center w-12 h-12 bg-brand-50 rounded-xl dark:bg-brand-500/10">
          <svg className="w-6 h-6 text-brand-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <div className="flex items-end justify-between mt-5">
          <div>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              Total Equity
            </span>
            <h4 className="mt-2 font-bold text-gray-800 text-title-sm dark:text-white/90">
              {isLoading ? "..." : `$${equity.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </h4>
          </div>
          <Badge color={mode === "live" ? "success" : "warning"}>
            {mode === "live" ? "LIVE" : mode.toUpperCase()}
          </Badge>
        </div>
      </div>

      {/* Available Cash */}
      <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03] md:p-6">
        <div className="flex items-center justify-center w-12 h-12 bg-success-50 rounded-xl dark:bg-success-500/10">
          <svg className="w-6 h-6 text-success-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 9V7a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2m2 4h10a2 2 0 002-2v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6a2 2 0 002 2zm7-5a2 2 0 11-4 0 2 2 0 014 0z" />
          </svg>
        </div>
        <div className="flex items-end justify-between mt-5">
          <div>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              Available Cash
            </span>
            <h4 className="mt-2 font-bold text-gray-800 text-title-sm dark:text-white/90">
              {isLoading ? "..." : `$${cash.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
            </h4>
          </div>
          <Badge color="info">
            {isLoading ? "..." : `${(cashBuffer * 100).toFixed(0)}% buffer`}
          </Badge>
        </div>
      </div>

      {/* Open Positions */}
      <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03] md:p-6">
        <div className="flex items-center justify-center w-12 h-12 bg-warning-50 rounded-xl dark:bg-warning-500/10">
          <svg className="w-6 h-6 text-warning-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        </div>
        <div className="flex items-end justify-between mt-5">
          <div>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              Open Positions
            </span>
            <h4 className="mt-2 font-bold text-gray-800 text-title-sm dark:text-white/90">
              {isLoading ? "..." : posCount}
            </h4>
          </div>
          {exposurePct !== null && exposurePct !== undefined && (
            <Badge color={exposurePct > 0.8 ? "error" : exposurePct > 0.5 ? "warning" : "success"}>
              {(exposurePct * 100).toFixed(0)}% exposed
            </Badge>
          )}
        </div>
      </div>

      {/* System Status */}
      <div className="rounded-2xl border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-white/[0.03] md:p-6">
        <div className={`flex items-center justify-center w-12 h-12 rounded-xl ${killSwitch ? "bg-error-50 dark:bg-error-500/10" : "bg-success-50 dark:bg-success-500/10"}`}>
          {killSwitch ? (
            <svg className="w-6 h-6 text-error-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          ) : (
            <svg className="w-6 h-6 text-success-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          )}
        </div>
        <div className="flex items-end justify-between mt-5">
          <div>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              System Status
            </span>
            <h4 className="mt-2 font-bold text-gray-800 text-title-sm dark:text-white/90">
              {isLoading ? "..." : killSwitch ? "HALTED" : liveAllowed ? "ACTIVE" : "BLOCKED"}
            </h4>
          </div>
          <Badge color={killSwitch ? "error" : liveAllowed ? "success" : "warning"}>
            {killSwitch ? "Kill Switch ON" : liveAllowed ? "Trading OK" : "Restricted"}
          </Badge>
        </div>
      </div>
    </div>
  );
}
