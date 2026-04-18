import type { RunOut, TestStatus, ReportAvailability, LogLine } from "../types";
import { formatDate, formatDuration, runLabel } from "../utils/format";
import TestResultsTable from "./TestResultsTable";
import { RunSelector } from "./RunSelector";
import { TestSummaryCards } from "./TestSummaryCards";
import { MetricsPanel } from "./MetricsPanel";
import { ReportButtons } from "./ReportButtons";

interface DashboardProps {
  run: RunOut | null;
  isRunning: boolean;
  testStatuses: Record<string, TestStatus>;
  runStats: {
    total: number;
    passed: number;
    failed: number;
    errors: number;
    running: number;
    notStarted: number;
    cancelled: number;
  };
  logLines: LogLine[];
  reportAvail: ReportAvailability;
  metrics: any;
  runHistory: RunOut[];
  clientKey: string;
  onOpenReport: (type: string) => void;
  onOpenLogTab: (nodeId: string, label: string, filterKey: string) => void;
  onLoadSummaryData: () => void;
  onSetRun: (run: RunOut) => void;
  onRefreshLogsForRun: (runId: number) => void;
  onCancelRun: (runId: number) => void;
}

export default function Dashboard({
  run,
  isRunning,
  testStatuses,
  runStats,
  logLines,
  reportAvail,
  metrics,
  runHistory,
  clientKey,
  onOpenReport,
  onOpenLogTab,
  onLoadSummaryData,
  onSetRun,
  onRefreshLogsForRun,
  onCancelRun,
}: DashboardProps) {
  return (
    <div className="dvp-summary">
      {/* Current Run Detail */}
      {clientKey && run && (
        <div className="dvp-run-detail dvp-slide-in">
          <div className="dvp-run-detail__title">
            🚀 Run
            <RunSelector
              run={run}
              runHistory={runHistory}
              onSetRun={onSetRun}
              onRefreshLogsForRun={onRefreshLogsForRun}
            />
            <span className={`dvp-summary__status-badge dvp-summary__status-badge--${run.status}`}>
              {run.status}
            </span>
            {(run.status === "running" || run.status === "queued" || run.status === "pending") && (
              <button
                className="dvp-btn dvp-btn--danger dvp-btn--sm"
                style={{ marginLeft: 8, padding: "2px 8px", fontSize: 11 }}
                onClick={() => onCancelRun(run.id)}
                title={`Cancel ${runLabel(run)}`}
              >
                ✕ Cancel
              </button>
            )}
            <button
              className="dvp-btn dvp-btn--ghost dvp-btn--sm"
              style={{ marginLeft: 8, padding: "2px 8px", fontSize: 11 }}
              onClick={() => onOpenLogTab("__all__", `📜 Full Log — ${runLabel(run)}`, "__all__")}
              title="View complete unfiltered log for this run"
            >
              📜 Full Log
            </button>
            {run.note && run.note.startsWith("CLI:") && (
              <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 400 }}>
                {run.note}
              </span>
            )}
          </div>
          <div className="dvp-run-detail__grid">
            <div className="dvp-run-detail__field">
              <span className="dvp-run-detail__field-label">Duration</span>
              <span className="dvp-run-detail__field-value">
                {formatDuration(run.started_at, run.finished_at)}
              </span>
            </div>
            <div className="dvp-run-detail__field">
              <span className="dvp-run-detail__field-label">Files</span>
              <span className="dvp-run-detail__field-value">
                {new Set(run.selected_tests.map((t) => t.split("::")[0])).size} (parallel)
              </span>
            </div>
            <div className="dvp-run-detail__field">
              <span className="dvp-run-detail__field-label">Tests</span>
              <span className="dvp-run-detail__field-value">{run.selected_tests.length}</span>
            </div>
            <div className="dvp-run-detail__field">
              <span className="dvp-run-detail__field-label">Started</span>
              <span className="dvp-run-detail__field-value">{formatDate(run.started_at)}</span>
            </div>
            <div className="dvp-run-detail__field">
              <span className="dvp-run-detail__field-label">Finished</span>
              <span className="dvp-run-detail__field-value">{formatDate(run.finished_at)}</span>
            </div>
            {run.setup_config_id && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Setup</span>
                <span className="dvp-run-detail__field-value">
                  <span
                    className={`dvp-summary__status-badge dvp-summary__status-badge--${
                      run.setup_status === "passed" ? "completed"
                      : run.setup_status === "failed" ? "failed"
                      : run.setup_status === "running" ? "running"
                      : "pending"
                    }`}
                    style={{ cursor: "pointer" }}
                    title="Click to view setup logs"
                    onClick={() => onOpenLogTab("setup", "⚙ Setup Logs", "setup")}
                  >
                    {run.setup_status === "passed" ? "✓ passed"
                     : run.setup_status === "failed" ? "✗ failed"
                     : run.setup_status === "running" ? "⏳ running"
                     : run.setup_status || "pending"}
                  </span>
                </span>
              </div>
            )}
            {run.teardown_config_id && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Teardown</span>
                <span className="dvp-run-detail__field-value">
                  <span
                    className={`dvp-summary__status-badge dvp-summary__status-badge--${
                      run.teardown_status === "passed" ? "completed"
                      : run.teardown_status === "failed" ? "failed"
                      : run.teardown_status === "running" ? "running"
                      : "pending"
                    }`}
                    style={{ cursor: "pointer" }}
                    title="Click to view teardown logs"
                    onClick={() => onOpenLogTab("teardown", "🧹 Teardown Logs", "teardown")}
                  >
                    {run.teardown_status === "passed" ? "✓ passed"
                     : run.teardown_status === "failed" ? "✗ failed"
                     : run.teardown_status === "running" ? "⏳ running"
                     : run.teardown_status || "pending"}
                  </span>
                </span>
              </div>
            )}
          </div>
          <TestSummaryCards
            runStats={runStats}
            isRunning={isRunning}
            runStatus={run.status}
          />

          {/* Reports section — shown prominently after summary for quick access */}
          {(run.status === "completed" || run.status === "failed" || run.status === "cancelled") && (
            <ReportButtons reportAvail={reportAvail} onOpenReport={onOpenReport} runId={run.id} clientKey={clientKey} />
          )}

          {/* Test results table */}
          {Object.keys(testStatuses).length > 0 && (
            <TestResultsTable
              runId={run.id}
              runStatus={run.status}
              testStatuses={testStatuses}
              logLines={logLines}
              reportAvail={reportAvail}
              onOpenLogTab={onOpenLogTab}
              clientKey={clientKey}
            />
          )}
        </div>
      )}

      {/* Metrics */}
      {clientKey && <MetricsPanel metrics={metrics} />}

      {!clientKey && (
        <div className="dvp-summary-empty">
          <div className="dvp-summary-empty__icon">👋</div>
          <div className="dvp-summary-empty__title">Welcome to DVP</div>
          <div className="dvp-summary-empty__sub">Register a client in the sidebar to get started with test execution.</div>
        </div>
      )}

      {clientKey && !run && runHistory.length === 0 && (
        <div className="dvp-summary-empty">
          <div className="dvp-summary-empty__icon">🧪</div>
          <div className="dvp-summary-empty__title">Ready to run</div>
          <div className="dvp-summary-empty__sub">Select tests from the explorer and click Run to see results here.</div>
        </div>
      )}
    </div>
  );
}
