import React from "react";

export default function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <span className="font-mono text-xs uppercase tracking-widest text-error-400">
        Connection Error
      </span>
      <p className="text-sm text-gray-500 max-w-md text-center">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="font-mono text-[0.65rem] uppercase tracking-[0.14em] text-brand-400 border border-brand-300 rounded px-4 py-1.5 hover:bg-brand-50 transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}
