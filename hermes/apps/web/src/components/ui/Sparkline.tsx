"use client";
import React from "react";

export default function Sparkline({
  data,
  color = "#8af2c5",
  width = 120,
  height = 32,
}: {
  data: number[];
  color?: string;
  width?: number;
  height?: number;
}) {
  if (data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const padding = 2;

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - padding - ((v - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(" ");

  const fillPoints = `0,${height} ${points} ${width},${height}`;

  return (
    <svg width={width} height={height} className="block">
      <defs>
        <linearGradient id={`spark-${color}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={fillPoints}
        fill={`url(#spark-${color})`}
      />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
