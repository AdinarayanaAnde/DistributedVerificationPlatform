import { useRef, useEffect, useState } from "react";
import type { RunOut } from "../types";
import { formatDate, runLabel } from "../utils/format";

interface RunSelectorProps {
  run: RunOut;
  runHistory: RunOut[];
  onSetRun: (run: RunOut) => void;
  onRefreshLogsForRun: (runId: number) => void;
}

export function RunSelector({ run, runHistory, onSetRun, onRefreshLogsForRun }: RunSelectorProps) {
  const [showRunSelector, setShowRunSelector] = useState(false);
  const runSelectorRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (runSelectorRef.current && !runSelectorRef.current.contains(e.target as Node)) {
        setShowRunSelector(false);
      }
    };
    if (showRunSelector) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showRunSelector]);

  return (
    <div className="dvp-run-selector" ref={runSelectorRef}>
      <span
        className="dvp-run-selector__trigger"
        onMouseEnter={() => setShowRunSelector(true)}
        onClick={() => setShowRunSelector((v) => !v)}
      >
        {runLabel(run)} <span className="dvp-run-selector__caret">▾</span>
      </span>
      {showRunSelector && runHistory.length > 0 && (
        <div className="dvp-run-selector__dropdown">
          <div className="dvp-run-selector__list">
            {runHistory.map((r) => (
              <button
                key={r.id}
                className={`dvp-run-selector__item${r.id === run.id ? " dvp-run-selector__item--active" : ""}`}
                onClick={() => {
                  onSetRun(r);
                  onRefreshLogsForRun(r.id);
                  setShowRunSelector(false);
                }}
              >
                <span className="dvp-run-selector__item-id">{runLabel(r)}</span>
                <span className={`dvp-run-selector__item-status dvp-history-item__status--${r.status}`}>
                  {r.status}
                </span>
                <span className="dvp-run-selector__item-date">{formatDate(r.created_at)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
