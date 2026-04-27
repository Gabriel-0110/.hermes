import React from "react";

export default function PageHeader({
  title,
  code,
  subtitle,
  action,
}: {
  title: string;
  code: string;
  subtitle?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between mb-6">
      <div>
        <div className="flex items-center gap-3 mb-1">
          <h1 className="text-xl font-bold text-white">{title}</h1>
          <span className="font-mono text-[0.6rem] tracking-widest text-gray-600">
            {code}
          </span>
        </div>
        {subtitle && <p className="text-sm text-gray-500">{subtitle}</p>}
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}
