import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "Hermes Mission Control",
  description: "Mission Control starter interface for Hermes Cryptocurrency AI Trader.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <header className="topbar">
            <div className="brand">
              <span className="brand-mark">Hermes</span>
              <span className="brand-title">Cryptocurrency AI Trader</span>
            </div>
            <nav className="nav" aria-label="Primary">
              <Link href="/">Dashboard</Link>
              <Link href="/mission-control">Mission Control</Link>
              <Link href="/observability">Observability</Link>
              <Link href="/alerts">Alerts</Link>
              <Link href="/agents">Agents</Link>
            </nav>
          </header>
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
