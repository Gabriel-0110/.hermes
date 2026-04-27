import React from "react";

type BadgeColor = "brand" | "success" | "error" | "warning" | "gray";

const colorMap: Record<BadgeColor, string> = {
  brand:
    "bg-brand-100 text-brand-400 border-brand-300",
  success:
    "bg-success-50 text-success-400 border-success-300",
  error:
    "bg-error-50 text-error-400 border-error-300",
  warning:
    "bg-warning-50 text-warning-400 border-warning-300",
  gray:
    "bg-gray-100 text-gray-400 border-gray-300",
};

export default function Badge({
  color = "brand",
  children,
  className = "",
}: {
  color?: BadgeColor;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-mono text-[0.6rem] font-semibold uppercase tracking-[0.14em] ${colorMap[color]} ${className}`}
    >
      {children}
    </span>
  );
}
