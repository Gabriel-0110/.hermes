import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Hermes Mission Control",
  description: "Mission Control starter interface for Hermes Cryptocurrency AI Trader.",
};

const navItems = [
  { href: "/", label: "Dashboard", code: "00" },
  { href: "/positions", label: "Positions", code: "01" },
  { href: "/mission-control", label: "Mission Control", code: "02" },
  { href: "/observability", label: "Observability", code: "03" },
  { href: "/agents", label: "Agents", code: "04" },
];

const hudItems = [
  { label: "Exchange", value: "BITMART" },
  { label: "Mode", value: "LIVE" },
  { label: "Surface", value: "Trading Desk" },
  { label: "Window", value: "UTC" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="app-body">
        <div className="app-shell">
          <header className="topbar mission-topbar">
            <div className="brand brand-ops">
              <div className="brand-sigil" aria-hidden="true">
                <span className="brand-sigil-core" />
              </div>
              <div className="brand-copy">
                <span className="brand-mark">Hermes · Mission Ops</span>
                <span className="brand-title">Command surface for trading oversight</span>
              </div>
            </div>

            <div className="topbar-matrix" aria-label="Mission HUD">
              {hudItems.map((item) => (
                <div key={item.label} className="topbar-cell">
                  <span className="topbar-cell-label">{item.label}</span>
                  <span className="topbar-cell-value">{item.value}</span>
                </div>
              ))}
            </div>

            <div className="topbar-actions">
              <nav className="nav" aria-label="Primary">
                {navItems.map((item) => (
                  <Link key={item.href} href={item.href} className="nav-link">
                    <span className="nav-link-code">/{item.code}</span>
                    <span>{item.label}</span>
                  </Link>
                ))}
              </nav>

              <Link href="/mission-control" className="mission-cta">
                ◈ Mission Deck
              </Link>
            </div>
          </header>

          <main className="app-main">{children}</main>
        </div>
      </body>
    </html>
  );
}
