import { API_BASE } from "../constants";
import type { ReportAvailability } from "../types";

interface ReportButtonsProps {
  reportAvail: ReportAvailability;
  onOpenReport: (type: string) => void;
  runId?: number;
  clientKey?: string;
}

export function ReportButtons({ reportAvail, onOpenReport, runId, clientKey }: ReportButtonsProps) {
  if (Object.keys(reportAvail).length === 0) return null;

  const downloadReport = (type: string) => {
    if (!runId) return;
    window.open(`${API_BASE}/runs/${runId}/reports/${type}/download?client_key=${encodeURIComponent(clientKey || "")}`, "_blank");
  };

  const downloadAll = () => {
    if (!runId) return;
    window.open(`${API_BASE}/runs/${runId}/reports/download-all?client_key=${encodeURIComponent(clientKey || "")}`, "_blank");
  };

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
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
          <button className="dvp-btn dvp-btn--sm dvp-btn--ghost" onClick={() => onOpenReport("html")}>
            🌐 HTML
          </button>
        )}
        {reportAvail.junit_xml && (
          <button
            className="dvp-btn dvp-btn--sm dvp-btn--ghost"
            onClick={() => onOpenReport("junit_xml")}
          >
            📄 JUnit XML
          </button>
        )}
        {reportAvail.json && (
          <button className="dvp-btn dvp-btn--sm dvp-btn--ghost" onClick={() => onOpenReport("json")}>
            📊 JSON
          </button>
        )}
        {reportAvail.coverage && (
          <button
            className="dvp-btn dvp-btn--sm dvp-btn--ghost"
            onClick={() => onOpenReport("coverage")}
          >
            📈 Coverage
          </button>
        )}
        {reportAvail.allure && (
          <button className="dvp-btn dvp-btn--sm dvp-btn--ghost" onClick={() => onOpenReport("allure")}>
            🎯 Allure
          </button>
        )}
      </div>
      {runId && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginTop: 6 }}>
          <span
            style={{
              fontSize: 11,
              color: "var(--text-muted)",
              alignSelf: "center",
              marginRight: 4,
            }}
          >
            Download:
          </span>
          {reportAvail.html && (
            <button className="dvp-btn dvp-btn--sm dvp-btn--ghost" onClick={() => downloadReport("html")} title="Download HTML report">
              ⬇ HTML
            </button>
          )}
          {reportAvail.junit_xml && (
            <button className="dvp-btn dvp-btn--sm dvp-btn--ghost" onClick={() => downloadReport("junit_xml")} title="Download JUnit XML">
              ⬇ XML
            </button>
          )}
          {reportAvail.json && (
            <button className="dvp-btn dvp-btn--sm dvp-btn--ghost" onClick={() => downloadReport("json")} title="Download JSON report">
              ⬇ JSON
            </button>
          )}
          {reportAvail.coverage && (
            <button className="dvp-btn dvp-btn--sm dvp-btn--ghost" onClick={() => downloadReport("coverage")} title="Download coverage report">
              ⬇ Coverage
            </button>
          )}
          <button className="dvp-btn dvp-btn--sm dvp-btn--primary" onClick={downloadAll} title="Download all reports as ZIP">
            📦 Download All
          </button>
        </div>
      )}
    </div>
  );
}
