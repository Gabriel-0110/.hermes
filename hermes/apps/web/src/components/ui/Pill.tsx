import React from "react";

type PillVariant = "live" | "partial" | "scaffolded" | "missing" | "paper" | "disabled";

const variantMap: Record<PillVariant, string> = {
  live: "bg-success-50 text-success-400 border-success-300",
  partial: "bg-brand-100 text-brand-400 border-brand-300",
  scaffolded: "bg-warning-50 text-warning-400 border-warning-300",
  missing: "bg-error-50 text-error-400 border-error-300",
  paper: "bg-warning-50 text-warning-400 border-warning-300",
  disabled: "bg-gray-100 text-gray-500 border-gray-300",
};

export default function Pill({
  variant = "live",
  children,
  dot = false,
  className = "",
}: {
  variant?: PillVariant;
  children: React.ReactNode;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 h-6 rounded-full border px-2.5 font-mono text-[0.6rem] font-semibold uppercase tracking-[0.14em] ${variantMap[variant]} ${className}`}
    >
      {dot && (
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            variant === "live"
              ? "bg-success-400 pulse-green"
              : variant === "missing"
                ? "bg-error-400"
                : "bg-current"
          }`}
        />
      )}
      {children}
    </span>
  );
}
