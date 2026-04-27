import React from "react";

type IconProps = React.SVGProps<SVGSVGElement>;

export const DashboardIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M3 3h6v8H3V3zm8 0h6v4h-6V3zm0 6h6v8h-6V9zM3 13h6v4H3v-4z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

export const ExecutionIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M13 2L3 14h7l-1 6 10-12h-7l1-6z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

export const RiskIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M10 2L2 18h16L10 2z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 8v4m0 2v.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

export const PortfolioIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M10 2a8 8 0 100 16 8 8 0 000-16z" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M10 2v8l5.66 5.66" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

export const AgentsIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <circle cx="7" cy="7" r="3" stroke="currentColor" strokeWidth="1.5"/>
    <circle cx="14" cy="9" r="3" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M2 17c0-2.5 2-4 5-4s5 1.5 5 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M13 13c2 0 4 1 4 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

export const ObservabilityIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M2 10h3l2-6 3 12 2-8 2 4h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

export const StrategyIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M3 17V7l4-4 4 6 4-2 2 4v6H3z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

export const MarketIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M2 16l4-4 3 2 4-5 5-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="16" cy="5" r="2" stroke="currentColor" strokeWidth="1.5"/>
  </svg>
);

export const ChevronDownIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M5 8l5 5 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

export const MenuIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

export const CloseIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

export const DotsIcon = (props: IconProps) => (
  <svg width="20" height="4" viewBox="0 0 20 4" fill="currentColor" xmlns="http://www.w3.org/2000/svg" {...props}>
    <circle cx="2" cy="2" r="2"/><circle cx="10" cy="2" r="2"/><circle cx="18" cy="2" r="2"/>
  </svg>
);

export const SearchIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <circle cx="9" cy="9" r="6" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M13.5 13.5L17 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

export const KillSwitchIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M10 3v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
  </svg>
);

export const RefreshIcon = (props: IconProps) => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}>
    <path d="M17 10a7 7 0 01-12.9 3.8M3 10a7 7 0 0112.9-3.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M17 4v4h-4M3 16v-4h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);
