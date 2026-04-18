import { useState, useMemo, useRef, useEffect } from "react";
import type { TestStatus, ReportAvailability, LogLine } from "../types";
import { STATUS_LABELS, API_BASE } from "../constants";

/** Parse a test nodeid into file path and test function name.
 *  Handles class-based nodeids like `tests/foo.py::TestClass::test_method`.
 *  Gracefully handles non-nodeid strings (e.g. CLI commands). */
function parseNodeId(testId: string): { filePart: string; funcPart: string; fileName: string } {
  const parts = testId.split("::");
  if (parts.length >= 2) {
    const filePart = parts[0];
    const funcPart = parts[parts.length - 1];
    const fileName = filePart.split("/").pop() || filePart;
    return { filePart, funcPart, fileName };
  }
  // No "::" separator — likely a CLI command or non-standard entry.
  // Try to extract a meaningful file from the string.
  const pyMatch = testId.match(/([\w./\\-]+\.py)/);
  if (pyMatch) {
    const filePart = pyMatch[1];
    const fileName = filePart.split("/").pop()?.split("\\").pop() || filePart;
    return { filePart, funcPart: testId, fileName };
  }
  return { filePart: testId, funcPart: testId, fileName: testId };
}

/** Extract a meaningful failure detail for a test from log lines.
 *  Prioritises assertion messages ("E  AssertionError: ...") and FAIL-level lines
 *  attributed to this test. Falls back to the last matching log line. */
function getTestDetail(testId: string, funcPart: string, logLines: LogLine[]): string {
  // Collect all log lines attributed to this test (by source match)
  const testLogs = logLines.filter(
    (l) => l.source === testId
  );

  // Among those, find assertion/error lines (pytest "E " prefix lines are FAIL-level)
  const failLines = testLogs.filter(
    (l) => l.level === "FAIL" || l.level === "ERROR"
  );

  // Prioritise the first "E " assertion line — this is the actual failure reason
  const assertionLine = failLines.find(
    (l) => l.message.trimStart().startsWith("E ")
  );
  if (assertionLine) {
    // Collect consecutive "E " lines for a complete assertion message
    const startIdx = testLogs.indexOf(assertionLine);
    const eLines: string[] = [];
    for (let i = startIdx; i < testLogs.length; i++) {
      const msg = testLogs[i].message.trimStart();
      if (msg.startsWith("E ")) {
        eLines.push(msg.replace(/^E\s+/, ""));
      } else if (eLines.length > 0) {
        break;
      }
    }
    return eLines.join(" | ");
  }

  // Fallback: show the first FAIL/ERROR line's message
  if (failLines.length > 0) {
    return failLines[0].message;
  }

  // Last resort: last log line mentioning the test
  const lastLog = testLogs.length > 0
    ? testLogs[testLogs.length - 1]
    : [...logLines].reverse().find(
        (l) => l.message.includes(funcPart || "")
      );
  return lastLog ? lastLog.message : "";
}

interface TestResultsTableProps {
  runId: number;
  runStatus: string;
  testStatuses: Record<string, TestStatus>;
  logLines: LogLine[];
  reportAvail: ReportAvailability;
  onOpenLogTab: (nodeId: string, label: string, filterKey: string) => void;
  clientKey?: string;
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

/* ── Combo filter: text input + multi-select dropdown ── */
function ComboFilter({
  selected,
  onChange,
  options,
  placeholder,
}: {
  selected: string[];
  onChange: (v: string[]) => void;
  options: string[];
  placeholder: string;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  /* Close only on clicks truly outside the component */
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = search
    ? options.filter((o) => o.toLowerCase().includes(search.toLowerCase()))
    : options;

  const toggle = (opt: string) => {
    onChange(
      selected.includes(opt)
        ? selected.filter((s) => s !== opt)
        : [...selected, opt]
    );
  };

  const displayText = selected.length === 0
    ? ""
    : selected.length === 1
      ? selected[0]
      : `${selected.length} selected`;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <div style={{ display: "flex", alignItems: "center" }}>
        <input
          type="text"
          className="dvp-filter-input"
          placeholder={selected.length === 0 ? placeholder : displayText}
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          style={{
            flex: 1,
            paddingRight: 18,
            ...(selected.length > 0 && !search ? { color: "transparent" } : {}),
          }}
        />
        {selected.length > 0 && !search && (
          <span className="dvp-combo-display">{displayText}</span>
        )}
        <span
          className="dvp-combo-caret"
          onMouseDown={(e) => { e.preventDefault(); e.stopPropagation(); }}
          onClick={() => {
            if (selected.length > 0) { onChange([]); setSearch(""); }
            else setOpen((v) => !v);
          }}
        >
          {selected.length > 0 ? (
            <span className="dvp-combo-clear" title="Clear selection">✕</span>
          ) : "▾"}
        </span>
      </div>
      {open && (
        <div
          className="dvp-combo-dropdown"
          onMouseDown={(e) => e.preventDefault()}
        >
          {selected.length > 0 && (
            <div
              className="dvp-combo-option dvp-combo-option--clear"
              onClick={() => { onChange([]); setSearch(""); }}
            >
              Clear all ({selected.length})
            </div>
          )}
          {filtered.length === 0 && (
            <div className="dvp-combo-option dvp-combo-option--empty">No matches</div>
          )}
          {filtered.map((opt) => (
            <div
              key={opt}
              className={`dvp-combo-option ${selected.includes(opt) ? "dvp-combo-option--active" : ""}`}
              onClick={() => toggle(opt)}
            >
              <span className="dvp-combo-check">{selected.includes(opt) ? "☑" : "☐"}</span>
              {opt}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function TestResultsTable({
  runId,
  runStatus,
  testStatuses,
  logLines,
  reportAvail,
  onOpenLogTab,
  clientKey,
}: TestResultsTableProps) {
  const [filterTest, setFilterTest] = useState<string[]>([]);
  const [filterFile, setFilterFile] = useState<string[]>([]);
  const [filterStatus, setFilterStatus] = useState<string[]>([]);
  const [filterDetails, setFilterDetails] = useState("");

  const showReports =
    (runStatus === "completed" || runStatus === "failed" || runStatus === "cancelled") && reportAvail.per_test;

  // Collect unique test function names and file names for combo dropdowns
  // Cascading: each column's options come from rows matching OTHER columns' filters
  const allEntries = useMemo(() => Object.entries(testStatuses), [testStatuses]);

  const entriesForTestOptions = useMemo(() => {
    return allEntries.filter(([testId, st]) => {
      const { fileName } = parseNodeId(testId);
      if (filterFile.length > 0 && !filterFile.some(f => fileName.toLowerCase().includes(f.toLowerCase()))) return false;
      if (filterStatus.length > 0 && !filterStatus.includes(st)) return false;
      return true;
    });
  }, [allEntries, filterFile, filterStatus]);

  const entriesForFileOptions = useMemo(() => {
    return allEntries.filter(([testId, st]) => {
      const { funcPart } = parseNodeId(testId);
      if (filterTest.length > 0 && !filterTest.some(f => (funcPart || testId).toLowerCase().includes(f.toLowerCase()))) return false;
      if (filterStatus.length > 0 && !filterStatus.includes(st)) return false;
      return true;
    });
  }, [allEntries, filterTest, filterStatus]);

  const entriesForStatusOptions = useMemo(() => {
    return allEntries.filter(([testId]) => {
      const { funcPart, fileName } = parseNodeId(testId);
      if (filterTest.length > 0 && !filterTest.some(f => (funcPart || testId).toLowerCase().includes(f.toLowerCase()))) return false;
      if (filterFile.length > 0 && !filterFile.some(f => fileName.toLowerCase().includes(f.toLowerCase()))) return false;
      return true;
    });
  }, [allEntries, filterTest, filterFile]);

  const uniqueTestNames = useMemo(
    () => [...new Set(entriesForTestOptions.map(([id]) => parseNodeId(id).funcPart))].sort(),
    [entriesForTestOptions]
  );
  const uniqueFileNames = useMemo(
    () => [...new Set(entriesForFileOptions.map(([id]) => parseNodeId(id).fileName))].sort(),
    [entriesForFileOptions]
  );
  const uniqueStatuses = useMemo(
    () => [...new Set(entriesForStatusOptions.map(([, st]) => st))].sort(),
    [entriesForStatusOptions]
  );

  const filteredEntries = useMemo(() => {
    return Object.entries(testStatuses).filter(([testId, status]) => {
      const { funcPart, fileName } = parseNodeId(testId);
      const details = getTestDetail(testId, funcPart, logLines);

      if (filterTest.length > 0 && !filterTest.some(f => (funcPart || testId).toLowerCase().includes(f.toLowerCase())))
        return false;
      if (filterFile.length > 0 && !filterFile.some(f => fileName.toLowerCase().includes(f.toLowerCase())))
        return false;
      if (filterStatus.length > 0 && !filterStatus.includes(status)) return false;
      if (filterDetails && !details.toLowerCase().includes(filterDetails.toLowerCase()))
        return false;
      return true;
    });
  }, [testStatuses, logLines, filterTest, filterFile, filterStatus, filterDetails]);

  const activeFilterCount = [
    filterTest.length > 0,
    filterFile.length > 0,
    filterStatus.length > 0,
    filterDetails !== "",
  ].filter(Boolean).length;

  const clearFilters = () => {
    setFilterTest([]);
    setFilterFile([]);
    setFilterStatus([]);
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
                <ComboFilter
                  selected={filterTest}
                  onChange={setFilterTest}
                  options={uniqueTestNames}
                  placeholder="Filter test..."
                />
              </th>
              <th>
                <ComboFilter
                  selected={filterFile}
                  onChange={setFilterFile}
                  options={uniqueFileNames}
                  placeholder="Filter file..."
                />
              </th>
              <th>
                <ComboFilter
                  selected={filterStatus}
                  onChange={setFilterStatus}
                  options={uniqueStatuses}
                  placeholder="Filter status..."
                />
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
                const { filePart, funcPart, fileName } = parseNodeId(testId);
                const detail = getTestDetail(testId, funcPart, logLines);
                return (
                  <tr key={testId}>
                    <td
                      className="dvp-clickable-cell"
                      onClick={() => onOpenLogTab(testId, funcPart || testId, testId)}
                      title={`View logs for ${funcPart || testId}`}
                    >
                      {funcPart || testId}
                    </td>
                    <td
                      className="dvp-clickable-cell"
                      style={{ color: "var(--text-muted)", fontSize: 11 }}
                      onClick={() => onOpenLogTab(filePart, fileName, filePart)}
                      title={`View logs for ${fileName}`}
                    >
                      {fileName}
                    </td>
                    <td>
                      <span className={STATUS_CLASS[status] || ""}>
                        {STATUS_ICON[status] || "\u2014"} {STATUS_LABELS[status]}
                      </span>
                    </td>
                    <td
                      className="dvp-clickable-cell"
                      style={{
                        color: status === "fail" || status === "error" ? "var(--red)" : "var(--text-secondary)",
                        fontSize: 11,
                        maxWidth: 300,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      onClick={() => onOpenLogTab(testId, funcPart || testId, testId)}
                      title={detail || "\u2014"}
                    >
                      {detail || "\u2014"}
                    </td>
                    {showReports && (
                      <td>
                        <div style={{ display: "flex", gap: 4 }}>
                          <button
                            className="dvp-btn dvp-btn--ghost dvp-btn--xs"
                            title="JSON Report"
                            onClick={() =>
                              window.open(
                                `${API_BASE}/runs/${runId}/reports/test/${encodeURIComponent(testId)}?client_key=${encodeURIComponent(clientKey || "")}`,
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
                                `${API_BASE}/runs/${runId}/reports/file/${encodeURIComponent(filePart)}?client_key=${encodeURIComponent(clientKey || "")}`,
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
