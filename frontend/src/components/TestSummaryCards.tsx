import DonutChart from "./DonutChart";

interface RunStatsType {
  total: number;
  passed: number;
  failed: number;
  errors: number;
  running: number;
  notStarted: number;
  cancelled: number;
}

interface TestSummaryCardsProps {
  runStats: RunStatsType;
  isRunning: boolean;
  runStatus: string;
}

export function TestSummaryCards({ runStats, isRunning, runStatus }: TestSummaryCardsProps) {
  if (runStats.total === 0) return null;

  return (
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
      {(runStatus === "completed" || runStatus === "failed" || runStatus === "cancelled") && (
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
  );
}
