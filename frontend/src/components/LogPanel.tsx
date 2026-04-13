import { useRef, useEffect } from "react";
import type { LogLine, RunOut } from "../types";
import { formatTime, levelClass } from "../utils/format";

interface LogPanelProps {
  lines: LogLine[];
  label: string;
  run: RunOut | null;
  isRunning: boolean;
  onRefreshLogs: () => void;
}

export default function LogPanel({ lines, label, run, isRunning, onRefreshLogs }: LogPanelProps) {
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  return (
    <div className="dvp-logs">
      <div className="dvp-logs__toolbar">
        <span className="dvp-logs__toolbar-label">{label}</span>
        {run && (
          <span className={`dvp-history-item__status dvp-history-item__status--${run.status}`}>
            {run.status}
          </span>
        )}
        <span className="dvp-logs__toolbar-spacer" />
        {run && (
          <button className="dvp-btn dvp-btn--ghost dvp-btn--sm" onClick={onRefreshLogs}>
            {"\u21BB"} Refresh
          </button>
        )}
      </div>
      <div className="dvp-logs__body">
        {lines.length === 0 ? (
          <div className="dvp-log-empty">
            <div className="dvp-log-empty__icon">{"\u{1F4DD}"}</div>
            <div className="dvp-log-empty__text">
              {run ? (isRunning ? "Waiting for output..." : "No logs available") : "No active run"}
            </div>
            <div className="dvp-log-empty__sub">
              {!run && "Select tests from the left panel and click Run"}
            </div>
          </div>
        ) : (
          lines.map((line, idx) => (
            <div key={idx} className="dvp-log-line dvp-slide-in">
              <span className="dvp-log-line__time">{formatTime(line.timestamp)}</span>
              <span className={`dvp-log-line__level dvp-log-line__level--${levelClass(line.level)}`}>
                {line.level}
              </span>
              <span className="dvp-log-line__msg">{line.message}</span>
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}
