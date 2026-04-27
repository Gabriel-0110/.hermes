import React from "react";

export default function ModuleCard({
  title,
  subtitle,
  action,
  children,
  className = "",
}: {
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`hermes-module ${className}`}>
      <div className="relative flex items-center justify-between px-5 py-3.5 border-b border-gray-200 bg-surface-high/50">
        <div className="absolute top-0 left-0 w-[7px] h-px bg-brand-300" />
        <div className="absolute top-0 left-0 w-px h-[7px] bg-brand-300" />
        <div className="absolute top-0 right-0 w-[7px] h-px bg-brand-300" />
        <div className="absolute top-0 right-0 w-px h-[7px] bg-brand-300" />
        <div className="absolute bottom-0 left-0 w-[7px] h-px bg-brand-300" />
        <div className="absolute bottom-0 left-0 w-px h-[7px] bg-brand-300" />
        <div className="absolute bottom-0 right-0 w-[7px] h-px bg-brand-300" />
        <div className="absolute bottom-0 right-0 w-px h-[7px] bg-brand-300" />

        <div>
          <h3 className="font-mono text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-white">
            {title}
          </h3>
          {subtitle && (
            <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
          )}
        </div>
        {action && <div>{action}</div>}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}
