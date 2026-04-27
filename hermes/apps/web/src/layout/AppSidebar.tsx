"use client";
import React, { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSidebar } from "@/context/SidebarContext";
import {
  DashboardIcon,
  ExecutionIcon,
  RiskIcon,
  PortfolioIcon,
  AgentsIcon,
  ObservabilityIcon,
  StrategyIcon,
  MarketIcon,
  ChevronDownIcon,
  DotsIcon,
} from "@/icons";

type NavItem = {
  name: string;
  code: string;
  icon: React.ReactNode;
  path?: string;
  subItems?: { name: string; path: string }[];
};

const navItems: NavItem[] = [
  {
    icon: <DashboardIcon />,
    name: "Trading Desk",
    code: "/00",
    path: "/",
  },
  {
    icon: <ExecutionIcon />,
    name: "Execution",
    code: "/01",
    path: "/execution",
  },
  {
    icon: <RiskIcon />,
    name: "Risk",
    code: "/02",
    path: "/risk",
  },
  {
    icon: <PortfolioIcon />,
    name: "Portfolio",
    code: "/03",
    path: "/portfolio",
  },
  {
    icon: <AgentsIcon />,
    name: "Agents",
    code: "/04",
    path: "/agents",
  },
];

const secondaryItems: NavItem[] = [
  {
    icon: <ObservabilityIcon />,
    name: "Observability",
    code: "/05",
    path: "/observability",
  },
  {
    icon: <StrategyIcon />,
    name: "Strategy",
    code: "/06",
    path: "/strategy",
  },
  {
    icon: <MarketIcon />,
    name: "Market",
    code: "/07",
    path: "/market",
  },
];

export default function AppSidebar() {
  const { isExpanded, isMobileOpen, isHovered, setIsHovered } = useSidebar();
  const pathname = usePathname();
  const showFull = isExpanded || isHovered || isMobileOpen;

  const isActive = useCallback(
    (path: string) => {
      if (path === "/") return pathname === "/";
      return pathname.startsWith(path);
    },
    [pathname]
  );

  const renderItems = (items: NavItem[]) => (
    <ul className="flex flex-col gap-1">
      {items.map((nav) => (
        <li key={nav.code}>
          {nav.path && (
            <Link
              href={nav.path}
              className={`menu-item group ${
                isActive(nav.path) ? "menu-item-active" : "menu-item-inactive"
              } ${!showFull ? "lg:justify-center" : ""}`}
            >
              <span
                className={
                  isActive(nav.path!)
                    ? "menu-item-icon-active"
                    : "menu-item-icon-inactive"
                }
              >
                {nav.icon}
              </span>
              {showFull && (
                <>
                  <span className="flex-1">{nav.name}</span>
                  <span className="font-mono text-[0.6rem] tracking-widest text-gray-600">
                    {nav.code}
                  </span>
                </>
              )}
            </Link>
          )}
        </li>
      ))}
    </ul>
  );

  return (
    <aside
      className={`fixed mt-16 flex flex-col lg:mt-0 top-0 px-4 left-0 bg-surface-base border-r border-gray-200 text-white h-screen transition-all duration-300 ease-in-out z-50
        ${showFull ? "w-[260px]" : "w-[72px]"}
        ${isMobileOpen ? "translate-x-0" : "-translate-x-full"}
        lg:translate-x-0`}
      onMouseEnter={() => !isExpanded && setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div
        className={`py-6 flex ${
          !showFull ? "lg:justify-center" : "justify-start"
        }`}
      >
        <Link href="/" className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-brand-100 flex items-center justify-center">
            <span className="font-display text-brand-400 text-sm font-bold">
              H
            </span>
          </div>
          {showFull && (
            <div>
              <span className="font-display text-sm font-bold tracking-[0.22em] uppercase text-white">
                Hermes
              </span>
              <span className="block font-mono text-[0.5rem] tracking-[0.16em] uppercase text-gray-500">
                Trading Desk
              </span>
            </div>
          )}
        </Link>
      </div>

      <div className="flex flex-col flex-1 overflow-y-auto no-scrollbar">
        <nav className="flex flex-col gap-6 flex-1">
          <div>
            <h2
              className={`mb-3 font-mono text-[0.6rem] uppercase tracking-[0.16em] text-gray-600 flex ${
                !showFull ? "lg:justify-center" : "justify-start px-3"
              }`}
            >
              {showFull ? "Operations" : <DotsIcon />}
            </h2>
            {renderItems(navItems)}
          </div>

          <div>
            <h2
              className={`mb-3 font-mono text-[0.6rem] uppercase tracking-[0.16em] text-gray-600 flex ${
                !showFull ? "lg:justify-center" : "justify-start px-3"
              }`}
            >
              {showFull ? "Intelligence" : <DotsIcon />}
            </h2>
            {renderItems(secondaryItems)}
          </div>
        </nav>

        {showFull && (
          <div className="p-3 mb-4 rounded-xl border border-gray-200 bg-surface-high/50">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full bg-success-400 pulse-green" />
              <span className="font-mono text-[0.6rem] uppercase tracking-widest text-gray-400">
                System Online
              </span>
            </div>
            <span className="font-mono text-[0.55rem] text-gray-600">
              BitMart · Live Guarded
            </span>
          </div>
        )}
      </div>
    </aside>
  );
}
