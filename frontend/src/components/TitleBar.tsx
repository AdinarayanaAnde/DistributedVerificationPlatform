import type { Theme } from "../types";

interface TitleBarProps {
  theme: Theme;
  onToggleTheme: () => void;
  clientKey: string;
}

export default function TitleBar({ theme, onToggleTheme, clientKey }: TitleBarProps) {
  return (
    <div className="dvp-titlebar">
      <div className="dvp-titlebar__brand">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
        </svg>
        DVP — Distributed Verification Platform
      </div>
      <div className="dvp-titlebar__actions">
        <button
          className="dvp-btn dvp-btn--ghost dvp-btn--sm dvp-theme-toggle"
          onClick={onToggleTheme}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        >
          {theme === "dark" ? "\u2600\uFE0F Light" : "\u{1F319} Dark"}
        </button>
        <span className="dvp-titlebar__status">
          <span className={`dot ${clientKey ? "" : "dot--disconnected"}`} />
          {clientKey ? "Connected" : "Not registered"}
        </span>
      </div>
    </div>
  );
}
