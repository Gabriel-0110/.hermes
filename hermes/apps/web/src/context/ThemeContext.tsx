"use client";
import React, { createContext, useContext } from "react";

type ThemeContextType = { theme: "dark" };

const ThemeContext = createContext<ThemeContextType>({ theme: "dark" });

export const useTheme = () => useContext(ThemeContext);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  return (
    <ThemeContext.Provider value={{ theme: "dark" }}>
      {children}
    </ThemeContext.Provider>
  );
};
