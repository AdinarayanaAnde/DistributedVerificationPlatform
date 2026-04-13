import { useState, useMemo } from "react";
import type { TestStatus, ReportAvailability, LogLine } from "../types";
import { STATUS_LABELS, API_BASE } from "../constants";

interface TestResultsTableProps {
  runId: number;
  runStatus: string;
  testStatuses: Record<string, TestStatus>;
  logLines: LogLine[];
  reportAvail: ReportAvailability;
  onOpenLogTab: (nodeId: string, label: string, filterKey: string) => void;
}

const STATUS_ICON: Record<string, string> = {
  done: "\u2713",
  fail: "\u2717",
  error: "\u26A0",
  running: "\u25CB",
  "not-started": "\u2014",
  cancelled: "\u2298",
};

const STATUS_CLASS: Record<string, string> = {
  done: "status-pass",
  fail: "status-fail",
  error: "status-error",
  running: "status-running",
  "not-started": "status-not-started",
  cancelled: "status-cancelled",
};

export default function TestResultsTable({
  runId,
  runStatus,
  testStatuses,
  logLines,
  reportAvail,
  onOpenLogTab,
}: TestResultsTableProps) {
  const [filterTest, setFilterTest] = useState("");
  const [filterFile, setFilterFile] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterDetails, setFilterDetails] = useState("");

  const showReports =
    (runStatus === "completed" || runStatus === "failed" || runStatus === "cancelled") && reportAvail.per_test;

  const filteredEntries = useMemo(() => {
    return Object.entries(testStatuses).filter(([testId, status]) => {
      const [filePart, funcPart] = testId.split("::");
      const fileName = filePart.split("/").pop() || filePart;
      const lastLog = [...logLines]
        .reverse()
        .find((l) => l.source === testId || l.message.includes(funcPart || ""));
      const details = lastLog ? lastLog.message : "";

      if (filterTest && !(funcPart || testId).toLowerCase().includes(filterTest.toLowerCase()))
        return false;
      if (filterFile && !fileName.toLowerCase().includes(filterFile.toLowerCase())) return false;
      if (filterStatus !== "all" && status !== filterStatus) return false;
      if (filterDetails && !details.toLowerCase().includes(filterDetails.toLowerCase()))
        return false;
      return true;
    });
  }, [testStatuses, logLines, filterTest, filterFile, filterStatus, filterDetails]);

  const activeFilterCount = [
    filterTest,
    filterFile,
    filterStatus !== "all" ? filterStatus : "",
    filterDetails,
  ].filter(Boolean).length;

  const clearFilters = () => {
    setFilterTest("");
    setFilterFile("");
    setFilterStatus("all");
    setFilterDetails("");
  };

  return (
    <div style={{ marginTop: 12 }}>
      <div className="dvp-results-header">
        <span className="dvp-results-header__title">
          Test Results
          <span className="dvp-results-header__count">
            {filteredEntries.length} of {Object.keys(testStatuses).length}
          </span>
        </span>
        {activeFilterCount > 0 && (
          <button
            className="dvp-btn dvp-btn--ghost dvp-btn--xs dvp-filter-clear"
            onClick={clearFilters}
          >
            Clear filters ({activeFilterCount})
          </button>
        )}
      </div>

      <div className="dvp-results-wrapper">
        {/* Fixed header table */}
        <table className="dvp-results-table dvp-results-table--head">
          <colgroup>
            <col style={{ width: "22%" }} />
            <col style={{ width: "16%" }} />
            <col style={{ width: "12%" }} />
            <col style={{ width: showReports ? "36%" : "50%" }} />
            {showReports && <col style={{ width: "14%" }} />}
          </colgroup>
          <thead>
            <tr>
              <th>Test</th>
              <th>File</th>
              <th>Status</th>
              <th>Details</th>
              {showReports && <th>Reports</th>}
            </tr>
            <tr className="dvp-filter-row">
              <th>
                <input
                  type="text"
                  className="dvp-filter-input"
                  placeholder="Filter test..."
                  value={filterTest}
                  onChange={(e) => setFilterTest(e.target.value)}
                />
              </th>
              <th>
                <input
                  type="text"
                  className="dvp-filter-input"
                  placeholder="Filter file..."
                  value={filterFile}
                  onChange={(e) => setFilterFile(e.target.value)}
                />
              </th>
              <th>
                <select
                  className="dvp-filter-select"
                  value={filterStatus}
                  onChange={(e) => setFilterStatus(e.target.value)}
                >
                  <option value="all">All</option>
                  <option value="done">Done</option>
                  <option value="fail">Fail</option>
                  <option value="error">Error</option>
                  <option value="running">Running</option>
                  <option value="not-started">Not started</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </th>
              <th>
                <input
                  type="text"
                  className="dvp-filter-input"
                  placeholder="Filter details..."
                  value={filterDetails}
                  onChange={(e) => setFilterDetails(e.target.value)}
                />
              </th>
              {showReports && <th />}
            </tr>
          </thead>
        </table>

        {/* Scrollable body table */}
        <div className="dvp-results-scroll">
          <table className="dvp-results-table dvp-results-table--body">
            <colgroup>
              <col style={{ width: "22%" }} />
              <col style={{ width: "16%" }} />
              <col style={{ width: "12%" }} />
              <col style={{ width: showReports ? "36%" : "50%" }} />
              {showReports && <col style={{ width: "14%" }} />}
            </colgroup>
            <tbody>
              {filteredEntries.map(([testId, status]) => {
                const [filePart, funcPart] = testId.split("::");
                const fileName = filePart.split("/").pop() || filePart;
                const lastLog = [...logLines]
                  .reverse()
                  .find(
                    (l) => l.source === testId || l.message.includes(funcPart || "")
                  );
                return (
                  <tr key={testId}>
                    <td
                      style={{ cursor: "pointer" }}
                      onClick={() => onOpenLogTab(testId, funcPart || testId, testId)}
                    >
                      {funcPart || testId}
                    </td>
                    <td style={{ color: "var(--text-muted)", fontSize: 11 }}>
                      {fileName}
                    </td>
                    <td>
                      <span className={STATUS_CLASS[status] || ""}>
                        {STATUS_ICON[status] || "\u2014"} {STATUS_LABELS[status]}
                      </span>
                    </td>
                    <td
                      style={{
                        color: "var(--text-secondary)",
                        fontSize: 11,
                        maxWidth: 300,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {lastLog ? lastLog.message.slice(0, 80) : "\u2014"}
                    </td>
                    {showReports && (
                      <td>
                        <div style={{ display: "flex", gap: 4 }}>
                          <button
                            className="dvp-btn dvp-btn--ghost dvp-btn--xs"
                            title="JSON Report"
                            onClick={() =>
                              window.open(
                                `${API_BASE}/runs/${runId}/reports/test/${encodeURIComponent(testId)}`,
                                "_blank"
                              )
                            }
                          >
                            JSON
                          </button>
                          <button
                            className="dvp-btn dvp-btn--ghost dvp-btn--xs"
                            title="File-level Aggregate"
                            onClick={() =>
                              window.open(
                                `${API_BASE}/runs/${runId}/reports/file/${encodeURIComponent(filePart)}`,
                                "_blank"
                              )
                            }
                          >
                            File
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {filteredEntries.length === 0 && Object.keys(testStatuses).length > 0 && (
        <div className="dvp-results-empty">No tests match the current filters.</div>
      )}
    </div>
  );
}
