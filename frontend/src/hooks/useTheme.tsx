import { useState, useEffect } from "react";
import type { Theme } from "../types";

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(
    () => (localStorage.getItem("dvp-theme") as Theme) || "dark"
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("dvp-theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setThemeState((t) => (t === "dark" ? "light" : "dark"));
  };

  return {
    value: theme,
    setValue: setThemeState,
    toggle: toggleTheme,
  };
}
