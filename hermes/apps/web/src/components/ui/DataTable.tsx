"use client";
import React from "react";

export interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
  align?: "left" | "right" | "center";
  mono?: boolean;
}

export default function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  emptyMessage = "No data available",
}: {
  columns: Column<T>[];
  data: T[];
  emptyMessage?: string;
}) {
  if (data.length === 0) {
    return (
      <div className="py-12 text-center">
        <p className="font-mono text-xs text-gray-600">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto custom-scrollbar">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-200">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`py-2.5 px-3 font-mono text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-gray-500 text-${col.align ?? "left"}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={i}
              className="border-b border-gray-200/50 hover:bg-brand-50/50 transition-colors"
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`py-2.5 px-3 text-sm ${
                    col.mono ? "font-mono text-xs" : ""
                  } text-${col.align ?? "left"}`}
                >
                  {col.render
                    ? col.render(row)
                    : String(row[col.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
