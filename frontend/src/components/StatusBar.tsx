import type { ExplorerMode, RunOut } from "../types";

interface StatusBarProps {
  isRunning: boolean;
  statusMessage: string;
  testsCount: number;
  selectedCount: number;
  explorerMode: ExplorerMode;
  cliCommand: string;
  run: RunOut | null;
}

export default function StatusBar({
  isRunning,
  statusMessage,
  testsCount,
  selectedCount,
  explorerMode,
  cliCommand,
  run,
}: StatusBarProps) {
  return (
    <div className="dvp-statusbar">
      <span className="dvp-statusbar__item">
        {isRunning && (
          <span className="dvp-spinner" style={{ width: 10, height: 10, borderWidth: 1.5 }} />
        )}
        {statusMessage}
      </span>
      <span className="dvp-statusbar__spacer" />
      <span className="dvp-statusbar__item">Tests: {testsCount}</span>
      <span className="dvp-statusbar__item">Selected: {selectedCount}</span>
      {explorerMode === "cli" && cliCommand && (
        <span className="dvp-statusbar__item">CLI: {cliCommand.slice(0, 30)}</span>
      )}
      {run && <span className="dvp-statusbar__item">Run #{run.id}</span>}
    </div>
  );
}
