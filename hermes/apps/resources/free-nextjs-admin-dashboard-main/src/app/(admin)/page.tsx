import type { Metadata } from "next";
import React from "react";
import PortfolioMetrics from "@/components/trading/PortfolioMetrics";
import RiskGauge from "@/components/trading/RiskGauge";
import RecentExecutions from "@/components/trading/RecentExecutions";
import AgentStatusCard from "@/components/trading/AgentStatusCard";
import SystemHealth from "@/components/trading/SystemHealth";

export const metadata: Metadata = {
  title: "Hermes Trading Desk",
  description: "Hermes AI Trading Desk — Live Dashboard",
};

export default function Dashboard() {
  return (
    <div className="grid grid-cols-12 gap-4 md:gap-6">
      <div className="col-span-12">
        <PortfolioMetrics />
      </div>

      <div className="col-span-12 xl:col-span-7">
        <RiskGauge />
      </div>

      <div className="col-span-12 xl:col-span-5">
        <AgentStatusCard />
      </div>

      <div className="col-span-12">
        <RecentExecutions />
      </div>

      <div className="col-span-12">
        <SystemHealth />
      </div>
    </div>
  );
}
