"use client";
import { useSidebar } from "@/context/SidebarContext";
import { SearchIcon, MenuIcon, CloseIcon } from "@/icons";
import React, { useState, useEffect, useRef } from "react";

export default function AppHeader() {
  const { isMobileOpen, toggleSidebar, toggleMobileSidebar } = useSidebar();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleToggle = () => {
    if (window.innerWidth >= 1024) toggleSidebar();
    else toggleMobileSidebar();
  };

  return (
    <header className="sticky top-0 z-99999 w-full">
      <div className="relative border-b border-gray-200 bg-surface-base/80 backdrop-blur-xl">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[200px] h-px bg-gradient-to-r from-transparent via-brand-400/60 to-transparent" />

        <div className="flex items-center justify-between px-4 py-3 lg:px-6">
          <div className="flex items-center gap-4">
            <button
              onClick={handleToggle}
              className="flex items-center justify-center w-9 h-9 rounded-lg border border-gray-200 text-gray-400 hover:text-white hover:bg-brand-50 transition-colors"
              aria-label="Toggle Sidebar"
            >
              {isMobileOpen ? <CloseIcon /> : <MenuIcon />}
            </button>

            <div className="hidden lg:block">
              <div className="relative">
                <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 w-4 h-4" />
                <input
                  ref={inputRef}
                  type="text"
                  placeholder="Search or type command..."
                  className="h-9 w-[320px] rounded-lg border border-gray-200 bg-transparent py-2 pl-10 pr-14 font-mono text-xs text-white placeholder:text-gray-600 focus:border-brand-300 focus:outline-none focus:ring-1 focus:ring-brand-400/20"
                />
                <kbd className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center gap-0.5 rounded border border-gray-200 bg-surface-high px-1.5 py-0.5 font-mono text-[0.6rem] text-gray-500">
                  <span>⌘</span>
                  <span>K</span>
                </kbd>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <HudCell label="Exchange" value="BITMART" />
            <HudCell label="Mode" value="LIVE" className="text-error-400" />
            <HudCell label="Surface" value="DESK" />

            <div className="flex items-center gap-2 ml-2 pl-3 border-l border-gray-200">
              <div className="w-7 h-7 rounded-full bg-brand-100 flex items-center justify-center">
                <span className="font-mono text-[0.6rem] font-bold text-brand-400">
                  G
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

function HudCell({
  label,
  value,
  className = "text-white",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className="hidden sm:block text-right">
      <div className="font-mono text-[0.5rem] uppercase tracking-[0.16em] text-gray-600">
        {label}
      </div>
      <div className={`font-mono text-[0.65rem] font-semibold tracking-wider ${className}`}>
        {value}
      </div>
    </div>
  );
}
