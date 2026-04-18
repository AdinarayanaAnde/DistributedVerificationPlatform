import type { RunOut } from "../types";
import { runLabel } from "../utils/format";

interface RunControlsProps {
  isRunning: boolean;
  run: RunOut | null;
  canRun: boolean;
  runButtonLabel: string;
  onRun: () => void;
  onCancelRun: (runId: number) => void;
}

export function RunControls({
  isRunning,
  run,
  canRun,
  runButtonLabel,
  onRun,
  onCancelRun,
}: RunControlsProps) {
  return (
    <div className="dvp-sidebar__footer">
      {isRunning && run ? (
        <button
          className="dvp-btn dvp-btn--danger dvp-btn--block dvp-run-btn"
          onClick={() => onCancelRun(run.id)}
        >
          ■ Stop {runLabel(run)}
        </button>
      ) : (
        <button
          className={`dvp-btn dvp-btn--primary dvp-btn--block dvp-run-btn ${!canRun ? "dvp-btn--disabled" : ""}`}
          disabled={!canRun}
          onClick={onRun}
        >
          ▶ {runButtonLabel}
        </button>
      )}
    </div>
  );
}
