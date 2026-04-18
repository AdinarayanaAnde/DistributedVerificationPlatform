import type { ExplorerMode } from "../types";

interface ExplorerTabsProps {
  explorerMode: ExplorerMode;
  onSetExplorerMode: (mode: ExplorerMode) => void;
  clientKey?: string;
}

const REQUIRES_AUTH: ExplorerMode[] = ["suites", "cli", "setup", "teardown", "upload"];

export function ExplorerTabs({ explorerMode, onSetExplorerMode, clientKey }: ExplorerTabsProps) {
  return (
    <div className="dvp-explorer-tabs">
      {(["tests", "suites", "cli", "setup", "teardown", "upload"] as const).map((mode) => {
        const locked = REQUIRES_AUTH.includes(mode) && !clientKey;
        return (
          <button
            key={mode}
            className={`dvp-explorer-tab ${explorerMode === mode ? "dvp-explorer-tab--active" : ""} ${locked ? "dvp-explorer-tab--disabled" : ""}`}
            onClick={() => !locked && onSetExplorerMode(mode)}
            title={locked ? "Register a client first" : mode.charAt(0).toUpperCase() + mode.slice(1)}
            style={locked ? { opacity: 0.45, cursor: "not-allowed" } : undefined}
          >
            {locked ? "🔒 " : ""}{mode.charAt(0).toUpperCase() + mode.slice(1)}
          </button>
        );
      })}
    </div>
  );
}
