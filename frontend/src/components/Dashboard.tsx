import { useState, useRef, useEffect } from "react";
import type { RunOut, TestStatus, ReportAvailability, LogLine } from "../types";
import { formatDate, formatDuration } from "../utils/format";
import DonutChart from "./DonutChart";
import TestResultsTable from "./TestResultsTable";

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
  onOpenReport,
  onOpenLogTab,
  onLoadSummaryData,
  onSetRun,
  onRefreshLogsForRun,
  onCancelRun,
}: DashboardProps) {
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
    <div className="dvp-summary">
      {/* Current Run Detail */}
      {run && (
        <div className="dvp-run-detail dvp-slide-in">
          <div className="dvp-run-detail__title">
            {"\u{1F680}"} Run
            <div className="dvp-run-selector" ref={runSelectorRef}>
              <span
                className="dvp-run-selector__trigger"
                onMouseEnter={() => setShowRunSelector(true)}
                onClick={() => setShowRunSelector((v) => !v)}
              >
                #{run.id} <span className="dvp-run-selector__caret">{"\u25BE"}</span>
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
                        <span className="dvp-run-selector__item-id">#{r.id}</span>
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
            <span className={`dvp-summary__status-badge dvp-summary__status-badge--${run.status}`}>
              {run.status}
            </span>
            {(run.status === "running" || run.status === "queued" || run.status === "pending") && (
              <button
                className="dvp-btn dvp-btn--danger dvp-btn--sm"
                style={{ marginLeft: 8, padding: "2px 8px", fontSize: 11 }}
                onClick={() => onCancelRun(run.id)}
                title={`Cancel run #${run.id}`}
              >
                {"\u2715"} Cancel
              </button>
            )}
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
          </div>

          {/* Test Summary Cards */}
          {runStats.total > 0 && (
            <div style={{ marginTop: 20 }}>
              <div className="dvp-test-summary">
                <div className="dvp-test-summary__card dvp-test-summary__card--total">
                  <span className="dvp-test-summary__card-number">{runStats.total}</span>
                  <span className="dvp-test-summary__card-label">Total</span>
                </div>
                <div className="dvp-test-summary__card dvp-test-summary__card--pass">
                  <span className="dvp-test-summary__card-number">{runStats.passed}</span>
                  <span className="dvp-test-summary__card-label">Passed</span>
                  <span className="dvp-test-summary__card-pct">
                    {runStats.total > 0 ? Math.round((runStats.passed / runStats.total) * 100) : 0}%
                  </span>
                </div>
                <div className="dvp-test-summary__card dvp-test-summary__card--fail">
                  <span className="dvp-test-summary__card-number">{runStats.failed}</span>
                  <span className="dvp-test-summary__card-label">Failed</span>
                  <span className="dvp-test-summary__card-pct">
                    {runStats.total > 0 ? Math.round((runStats.failed / runStats.total) * 100) : 0}%
                  </span>
                </div>
                <div className="dvp-test-summary__card dvp-test-summary__card--error">
                  <span className="dvp-test-summary__card-number">{runStats.errors}</span>
                  <span className="dvp-test-summary__card-label">Errors</span>
                  <span className="dvp-test-summary__card-pct">
                    {runStats.total > 0 ? Math.round((runStats.errors / runStats.total) * 100) : 0}%
                  </span>
                </div>
                <div className="dvp-test-summary__card dvp-test-summary__card--running">
                  <span className="dvp-test-summary__card-number">
                    {runStats.running + runStats.notStarted}
                  </span>
                  <span className="dvp-test-summary__card-label">
                    {isRunning ? "In Progress" : "Pending"}
                  </span>
                </div>
                {runStats.cancelled > 0 && (
                  <div className="dvp-test-summary__card dvp-test-summary__card--cancelled">
                    <span className="dvp-test-summary__card-number">{runStats.cancelled}</span>
                    <span className="dvp-test-summary__card-label">Cancelled</span>
                    <span className="dvp-test-summary__card-pct">
                      {runStats.total > 0 ? Math.round((runStats.cancelled / runStats.total) * 100) : 0}%
                    </span>
                  </div>
                )}
              </div>

              {/* Donut chart */}
              {(run.status === "completed" || run.status === "failed" || run.status === "cancelled") && (
                <DonutChart {...runStats} />
              )}

              {/* Progress bar */}
              <div className="dvp-progress">
                {runStats.passed > 0 && (
                  <div
                    className="dvp-progress__bar dvp-progress__bar--pass"
                    style={{ width: `${(runStats.passed / runStats.total) * 100}%` }}
                  />
                )}
                {runStats.failed > 0 && (
                  <div
                    className="dvp-progress__bar dvp-progress__bar--fail"
                    style={{ width: `${(runStats.failed / runStats.total) * 100}%` }}
                  />
                )}
                {runStats.errors > 0 && (
                  <div
                    className="dvp-progress__bar dvp-progress__bar--error"
                    style={{ width: `${(runStats.errors / runStats.total) * 100}%` }}
                  />
                )}
                {runStats.cancelled > 0 && (
                  <div
                    className="dvp-progress__bar dvp-progress__bar--cancelled"
                    style={{ width: `${(runStats.cancelled / runStats.total) * 100}%` }}
                  />
                )}
              </div>
            </div>
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
            />
          )}

          {/* Reports section */}
          {(run.status === "completed" || run.status === "failed" || run.status === "cancelled") &&
            Object.keys(reportAvail).length > 0 && (
              <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span
                  style={{
                    fontSize: 11,
                    color: "var(--text-muted)",
                    alignSelf: "center",
                    marginRight: 4,
                  }}
                >
                  Reports:
                </span>
                {reportAvail.html && (
                  <button
                    className="dvp-btn dvp-btn--sm dvp-btn--ghost"
                    onClick={() => onOpenReport("html")}
                  >
                    {"\u{1F310}"} HTML
                  </button>
                )}
                {reportAvail.junit_xml && (
                  <button
                    className="dvp-btn dvp-btn--sm dvp-btn--ghost"
                    onClick={() => onOpenReport("junit_xml")}
                  >
                    {"\u{1F4C4}"} JUnit XML
                  </button>
                )}
                {reportAvail.json && (
                  <button
                    className="dvp-btn dvp-btn--sm dvp-btn--ghost"
                    onClick={() => onOpenReport("json")}
                  >
                    {"\u{1F4CA}"} JSON
                  </button>
                )}
                {reportAvail.coverage && (
                  <button
                    className="dvp-btn dvp-btn--sm dvp-btn--ghost"
                    onClick={() => onOpenReport("coverage")}
                  >
                    {"\u{1F4C8}"} Coverage
                  </button>
                )}
                {reportAvail.allure && (
                  <button
                    className="dvp-btn dvp-btn--sm dvp-btn--ghost"
                    onClick={() => onOpenReport("allure")}
                  >
                    {"\u{1F3AF}"} Allure
                  </button>
                )}
              </div>
            )}
        </div>
      )}

      {/* Metrics */}
      {metrics && (
        <>
          <div className="dvp-summary__section-title">{"\u{1F4C8}"} Metrics Overview</div>
          <div className="dvp-metrics-grid">
            <div className="dvp-metric-card">
              <div className="dvp-metric-card__icon">{"\u{1F3AF}"}</div>
              <div className="dvp-metric-card__value dvp-metric-card__value--accent">
                {metrics.total_runs}
              </div>
              <div className="dvp-metric-card__label">Total Runs</div>
            </div>
            <div className="dvp-metric-card">
              <div className="dvp-metric-card__icon">{"\u2705"}</div>
              <div
                className={`dvp-metric-card__value ${
                  metrics.success_rate >= 80
                    ? "dvp-metric-card__value--green"
                    : "dvp-metric-card__value--red"
                }`}
              >
                {metrics.success_rate}%
              </div>
              <div className="dvp-metric-card__label">Success Rate</div>
            </div>
            <div className="dvp-metric-card">
              <div className="dvp-metric-card__icon">{"\u{1F504}"}</div>
              <div className="dvp-metric-card__value dvp-metric-card__value--blue">
                {metrics.running_runs}
              </div>
              <div className="dvp-metric-card__label">Running</div>
            </div>
            <div className="dvp-metric-card">
              <div className="dvp-metric-card__icon">{"\u{23F3}"}</div>
              <div className="dvp-metric-card__value dvp-metric-card__value--yellow">
                {metrics.pending_runs}
              </div>
              <div className="dvp-metric-card__label">Pending</div>
            </div>
            <div className="dvp-metric-card">
              <div className="dvp-metric-card__icon">{"\u{1F4C5}"}</div>
              <div className="dvp-metric-card__value">{metrics.recent_runs}</div>
              <div className="dvp-metric-card__label">Recent 24h</div>
            </div>
          </div>

          {metrics.client_stats?.length > 0 && (
            <>
              <div className="dvp-summary__section-title">{"\u{1F465}"} Client Activity</div>
              <div className="dvp-metrics-grid" style={{ marginBottom: 24 }}>
                {metrics.client_stats.map((stat: any) => (
                  <div className="dvp-metric-card" key={stat.name}>
                    <div className="dvp-metric-card__icon">{"\u{1F464}"}</div>
                    <div className="dvp-metric-card__value">{stat.runs}</div>
                    <div className="dvp-metric-card__label">{stat.name}</div>
                  </div>
                ))}
              </div>
            </>
          )}

          {metrics.resource_stats?.length > 0 && (
            <>
              <div className="dvp-summary__section-title">
                {"\u{1F5A5}\uFE0F"} Resource Utilization
              </div>
              <div className="dvp-metrics-grid" style={{ marginBottom: 24 }}>
                {metrics.resource_stats.map((stat: any) => (
                  <div className="dvp-metric-card" key={stat.name}>
                    <div className="dvp-metric-card__icon">{"\u{1F527}"}</div>
                    <div className="dvp-metric-card__value">{stat.runs}</div>
                    <div className="dvp-metric-card__label">{stat.name}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}

      {!metrics && !run && runHistory.length === 0 && (
        <div className="dvp-summary-empty">
          <div className="dvp-summary-empty__icon">{"\u{1F4CA}"}</div>
          <div>No data yet. Run some tests to see the dashboard here.</div>
        </div>
      )}
    </div>
  );
}
