import { runLabel } from "../utils/format";

interface ReportTabProps {
  data: any;
}

export default function ReportTab({ data }: ReportTabProps) {
  if (!data)
    return (
      <div style={{ padding: 24, color: "var(--text-muted)" }}>No report data</div>
    );

  const summary = data.summary || data.result || data;
  const tests: any[] = data.tests || [];

  return (
    <div className="dvp-summary" style={{ padding: 20 }}>
      <div className="dvp-run-detail dvp-slide-in">
        <div className="dvp-run-detail__title">
          {"\u{1F4CB}"} {data.file || data.nodeid || data.file_key || "Report"}
          {data.run_id && (
            <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 8 }}>
              {runLabel({ id: data.run_id, run_name: data.run_name })}
            </span>
          )}
        </div>
        {summary && (
          <div className="dvp-run-detail__grid">
            {summary.total != null && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Total</span>
                <span className="dvp-run-detail__field-value">{summary.total}</span>
              </div>
            )}
            {summary.passed != null && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Passed</span>
                <span className="dvp-run-detail__field-value" style={{ color: "var(--status-pass)" }}>
                  {summary.passed}
                </span>
              </div>
            )}
            {summary.failed != null && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Failed</span>
                <span className="dvp-run-detail__field-value" style={{ color: "var(--status-fail)" }}>
                  {summary.failed}
                </span>
              </div>
            )}
            {summary.errors != null && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Errors</span>
                <span className="dvp-run-detail__field-value" style={{ color: "var(--status-fail)" }}>
                  {summary.errors}
                </span>
              </div>
            )}
            {summary.skipped != null && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Skipped</span>
                <span className="dvp-run-detail__field-value">{summary.skipped}</span>
              </div>
            )}
            {summary.total_time != null && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Duration</span>
                <span className="dvp-run-detail__field-value">{summary.total_time}s</span>
              </div>
            )}
            {summary.pass_rate != null && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Pass Rate</span>
                <span className="dvp-run-detail__field-value">{summary.pass_rate}%</span>
              </div>
            )}
            {/* Single test result fields */}
            {summary.status && !summary.total && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Status</span>
                <span
                  className="dvp-run-detail__field-value"
                  style={{
                    color:
                      summary.status === "passed"
                        ? "var(--status-pass)"
                        : summary.status === "failed"
                          ? "var(--status-fail)"
                          : "var(--text-primary)",
                  }}
                >
                  {summary.status}
                </span>
              </div>
            )}
            {summary.time != null && !summary.total_time && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Duration</span>
                <span className="dvp-run-detail__field-value">{summary.time}s</span>
              </div>
            )}
            {summary.nodeid && (
              <div className="dvp-run-detail__field">
                <span className="dvp-run-detail__field-label">Test ID</span>
                <span className="dvp-run-detail__field-value" style={{ fontSize: 11 }}>
                  {summary.nodeid}
                </span>
              </div>
            )}
          </div>
        )}
        {tests.length > 0 && (
          <table className="dvp-summary-table" style={{ marginTop: 16, width: "100%" }}>
            <thead>
              <tr>
                <th>Test</th>
                <th>Status</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {tests.map((t: any, i: number) => (
                <tr key={i}>
                  <td style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                    {t.nodeid || t.name || `Test ${i + 1}`}
                  </td>
                  <td>
                    <span
                      className={`dvp-summary__status-badge dvp-summary__status-badge--${
                        t.status === "passed" ? "completed" : "failed"
                      }`}
                    >
                      {t.status}
                    </span>
                  </td>
                  <td>{t.time != null ? `${t.time}s` : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
