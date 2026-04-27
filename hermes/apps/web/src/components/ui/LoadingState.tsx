import React from "react";

export default function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="flex items-center gap-3">
        <div className="w-2 h-2 rounded-full bg-brand-400 pulse-green" />
        <span className="font-mono text-xs uppercase tracking-widest text-gray-500">
          {label}
        </span>
      </div>
    </div>
  );
}
