"use client";
import React from "react";

export default function KillSwitchIndicator({
  active,
  reason,
  className = "",
}: {
  active: boolean;
  reason?: string;
  className?: string;
}) {
  return (
    <div
      className={`inline-flex items-center gap-2.5 h-7 rounded-full border px-3 ${
        active
          ? "bg-error-50 border-error-300 text-error-400"
          : "bg-success-50 border-success-300 text-success-400"
      } ${className}`}
    >
      <span
        className={`w-[7px] h-[7px] rounded-full ${
          active
            ? "bg-error-400"
            : "bg-success-400 pulse-green"
        }`}
        style={active ? { animation: "pulse-red 1.5s ease-in-out infinite" } : undefined}
      />
      <span className="font-mono text-[0.65rem] font-semibold uppercase tracking-[0.14em]">
        {active ? "Kill Switch Active" : "Kill Switch Off"}
      </span>
      {active && reason && (
        <span className="font-mono text-[0.55rem] text-error-400/70 ml-1">
          [{reason}]
        </span>
      )}
    </div>
  );
}
