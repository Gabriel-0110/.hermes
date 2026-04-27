"use client";
import React from "react";
import PageHeader from "@/components/ui/PageHeader";
import ModuleCard from "@/components/ui/ModuleCard";
import Badge from "@/components/ui/Badge";
import Pill from "@/components/ui/Pill";

const watchlist = [
  { symbol: "BTC", name: "Bitcoin", price: 67420.50, change24h: 2.34, volume24h: 28500000000 },
  { symbol: "ETH", name: "Ethereum", price: 3245.80, change24h: 1.12, volume24h: 14200000000 },
  { symbol: "SOL", name: "Solana", price: 142.65, change24h: -0.87, volume24h: 3100000000 },
  { symbol: "RENDER", name: "Render", price: 7.82, change24h: 5.43, volume24h: 450000000 },
  { symbol: "XRP", name: "Ripple", price: 0.5234, change24h: -1.23, volume24h: 1800000000 },
  { symbol: "AVAX", name: "Avalanche", price: 34.56, change24h: 0.45, volume24h: 890000000 },
];

const dataFeeds = [
  { name: "Market Price Feed", status: "live", source: "CoinGecko + BitMart" },
  { name: "Order Book / Depth", status: "live", source: "BitMart API" },
  { name: "Trades / Tape Feed", status: "live", source: "BitMart WebSocket" },
  { name: "Technical Indicators", status: "live", source: "TwelveData + Computed" },
  { name: "Derivatives & Funding", status: "live", source: "BitMart + Binance + Bybit" },
  { name: "News / Sentiment", status: "partial", source: "CryptoPanic + NewsAPI" },
  { name: "On-Chain Intelligence", status: "partial", source: "Etherscan + Nansen" },
  { name: "DeFi Data", status: "live", source: "DeFiLlama" },
  { name: "Macro Data", status: "live", source: "FRED" },
  { name: "Social Sentiment", status: "scaffolded", source: "LunarCrush" },
  { name: "Chronos Forecasting", status: "live", source: "Amazon Chronos-2" },
  { name: "TradingView MCP", status: "live", source: "MCP Server" },
];

export default function MarketPage() {
  return (
    <>
      <PageHeader
        title="Market"
        code="/07"
        subtitle="Live market data, intelligence feeds, and watchlist"
      />

      <ModuleCard title="Watchlist" subtitle="Active monitoring targets" className="mb-6">
        <div className="overflow-x-auto custom-scrollbar">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200">
                {["Asset", "Price", "24h Change", "Volume 24h"].map((h) => (
                  <th
                    key={h}
                    className="py-2.5 px-3 font-mono text-[0.6rem] font-semibold uppercase tracking-[0.14em] text-gray-500 text-left"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {watchlist.map((asset) => (
                <tr
                  key={asset.symbol}
                  className="border-b border-gray-200/50 hover:bg-brand-50/50 transition-colors"
                >
                  <td className="py-3 px-3">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-brand-50 flex items-center justify-center">
                        <span className="font-mono text-[0.6rem] font-bold text-brand-400">
                          {asset.symbol.slice(0, 2)}
                        </span>
                      </div>
                      <div>
                        <span className="text-sm font-bold text-white block">
                          {asset.symbol}
                        </span>
                        <span className="font-mono text-[0.55rem] text-gray-500">
                          {asset.name}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="py-3 px-3 font-mono text-sm text-white">
                    ${asset.price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </td>
                  <td className="py-3 px-3">
                    <Badge color={asset.change24h >= 0 ? "success" : "error"}>
                      {asset.change24h >= 0 ? "+" : ""}
                      {asset.change24h.toFixed(2)}%
                    </Badge>
                  </td>
                  <td className="py-3 px-3 font-mono text-xs text-gray-400">
                    ${(asset.volume24h / 1e9).toFixed(2)}B
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ModuleCard>

      <ModuleCard title="Intelligence Feeds" subtitle="Shared Intelligence Layer status">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {dataFeeds.map((feed) => (
            <div
              key={feed.name}
              className="flex items-start justify-between p-3 rounded-lg border border-gray-200/50 bg-surface-high/30"
            >
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold text-white mb-1 truncate">
                  {feed.name}
                </div>
                <div className="font-mono text-[0.55rem] text-gray-500 truncate">
                  {feed.source}
                </div>
              </div>
              <Pill
                variant={
                  feed.status === "live"
                    ? "live"
                    : feed.status === "partial"
                      ? "partial"
                      : "scaffolded"
                }
                dot
                className="ml-2 flex-shrink-0"
              >
                {feed.status}
              </Pill>
            </div>
          ))}
        </div>
      </ModuleCard>
    </>
  );
}
