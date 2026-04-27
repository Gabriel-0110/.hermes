"use client";
import React from "react";

export default function MetricCard({
  label,
  value,
  subValue,
  trend,
  icon,
}: {
  label: string;
  value: string;
  subValue?: string;
  trend?: "up" | "down" | "neutral";
  icon?: React.ReactNode;
}) {
  const trendColor =
    trend === "up"
      ? "text-success-400"
      : trend === "down"
        ? "text-error-400"
        : "text-gray-400";

  return (
    <div className="hermes-card hermes-card-hairline p-5">
      {icon && (
        <div className="w-10 h-10 rounded-xl bg-brand-50 flex items-center justify-center mb-4 text-brand-400">
          {icon}
        </div>
      )}
      <div className="label-uppercase mb-2">{label}</div>
      <div className={`stat-value ${trendColor}`}>{value}</div>
      {subValue && (
        <div className="font-mono text-xs text-gray-500 mt-1">{subValue}</div>
      )}
    </div>
  );
}
