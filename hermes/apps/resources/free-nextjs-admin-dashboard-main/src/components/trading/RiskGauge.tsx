"use client";
import React from "react";
import dynamic from "next/dynamic";
import { ApexOptions } from "apexcharts";
import { useHermesData } from "@/hooks/useHermesData";
import Badge from "../ui/badge/Badge";

const ReactApexChart = dynamic(() => import("react-apexcharts"), {
  ssr: false,
});

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
    recent_risk_rejections: Array<{
      id: string;
      error_message: string;
      created_at: string;
    }>;
  };
}

export default function RiskGauge() {
  const { data, loading } = useHermesData<RiskData>("/api/risk", 15000);

  const cashBuffer = data?.risk?.position_monitor?.risk_summary?.cash_buffer_pct ?? 1;
  const exposurePct = data?.risk?.position_monitor?.risk_summary?.gross_exposure_pct ?? 0;
  const totalPositions = data?.risk?.position_monitor?.risk_summary?.total_positions ?? 0;
  const warnings = data?.risk?.position_monitor?.risk_summary?.warnings ?? [];
  const rejections = data?.risk?.recent_risk_rejections ?? [];
  const killSwitch = data?.risk?.kill_switch?.active ?? false;
  const mode = data?.risk?.execution_safety?.execution_mode ?? "unknown";

  // Risk score: 0-100 where 100 = maximum safe
  const riskScore = killSwitch ? 0 : Math.round(cashBuffer * 100);

  const series = [riskScore];
  const options: ApexOptions = {
    colors: [killSwitch ? "#D92D20" : riskScore > 70 ? "#039855" : riskScore > 40 ? "#F79009" : "#D92D20"],
    chart: {
      fontFamily: "Outfit, sans-serif",
      type: "radialBar",
      height: 330,
      sparkline: { enabled: true },
    },
    plotOptions: {
      radialBar: {
        startAngle: -85,
        endAngle: 85,
        hollow: { size: "80%" },
        track: {
          background: "#E4E7EC",
          strokeWidth: "100%",
          margin: 5,
        },
        dataLabels: {
          name: { show: false },
          value: {
            fontSize: "36px",
            fontWeight: "600",
            offsetY: -40,
            color: "#1D2939",
            formatter: (val) => val + "%",
          },
        },
      },
    },
    fill: {
      type: "solid",
      colors: [killSwitch ? "#D92D20" : riskScore > 70 ? "#039855" : riskScore > 40 ? "#F79009" : "#D92D20"],
    },
    stroke: { lineCap: "round" },
    labels: ["Risk Score"],
  };

  return (
    <div className="rounded-2xl border border-gray-200 bg-gray-100 dark:border-gray-800 dark:bg-white/[0.03]">
      <div className="px-5 pt-5 bg-white shadow-default rounded-2xl pb-11 dark:bg-gray-900 sm:px-6 sm:pt-6">
        <div className="flex justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white/90">
              Risk Status
            </h3>
            <p className="mt-1 font-normal text-gray-500 text-theme-sm dark:text-gray-400">
              Capital safety & exposure gauge
            </p>
          </div>
          <Badge color={killSwitch ? "error" : "success"}>
            {killSwitch ? "⚠ HALTED" : mode.toUpperCase()}
          </Badge>
        </div>
        <div className="relative">
          <div className="max-h-[330px]">
            {loading ? (
              <div className="flex items-center justify-center h-[330px] text-gray-400">
                Loading...
              </div>
            ) : (
              <ReactApexChart
                options={options}
                series={series}
                type="radialBar"
                height={330}
              />
            )}
          </div>
          <span
            className={`absolute left-1/2 top-full -translate-x-1/2 -translate-y-[95%] rounded-full px-3 py-1 text-xs font-medium ${
              killSwitch
                ? "bg-error-50 text-error-600 dark:bg-error-500/15 dark:text-error-500"
                : riskScore > 70
                ? "bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-500"
                : "bg-warning-50 text-warning-600 dark:bg-warning-500/15 dark:text-warning-500"
            }`}
          >
            {killSwitch ? "Kill Switch Active" : riskScore > 70 ? "Healthy" : "Elevated Risk"}
          </span>
        </div>
        {warnings.length > 0 && (
          <div className="mt-8 space-y-2">
            {warnings.map((w, i) => (
              <p key={i} className="text-sm text-warning-500">⚠ {w}</p>
            ))}
          </div>
        )}
        {warnings.length === 0 && rejections.length === 0 && (
          <p className="mx-auto mt-10 w-full max-w-[380px] text-center text-sm text-gray-500 sm:text-base">
            {killSwitch
              ? "Trading is halted. Kill switch is active."
              : `Capital buffer at ${(cashBuffer * 100).toFixed(0)}%. ${totalPositions} open position${totalPositions !== 1 ? "s" : ""}.`}
          </p>
        )}
      </div>

      <div className="flex items-center justify-center gap-5 px-6 py-3.5 sm:gap-8 sm:py-5">
        <div className="text-center">
          <p className="mb-1 text-gray-500 text-theme-xs dark:text-gray-400 sm:text-sm">
            Positions
          </p>
          <p className="text-base font-semibold text-gray-800 dark:text-white/90 sm:text-lg">
            {totalPositions}
          </p>
        </div>

        <div className="w-px bg-gray-200 h-7 dark:bg-gray-800"></div>

        <div className="text-center">
          <p className="mb-1 text-gray-500 text-theme-xs dark:text-gray-400 sm:text-sm">
            Exposure
          </p>
          <p className="text-base font-semibold text-gray-800 dark:text-white/90 sm:text-lg">
            {exposurePct !== null ? `${(exposurePct * 100).toFixed(0)}%` : "0%"}
          </p>
        </div>

        <div className="w-px bg-gray-200 h-7 dark:bg-gray-800"></div>

        <div className="text-center">
          <p className="mb-1 text-gray-500 text-theme-xs dark:text-gray-400 sm:text-sm">
            Rejections
          </p>
          <p className="text-base font-semibold text-gray-800 dark:text-white/90 sm:text-lg">
            {rejections.length}
          </p>
        </div>
      </div>
    </div>
  );
}
