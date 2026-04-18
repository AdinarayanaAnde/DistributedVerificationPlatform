import { useState } from "react";
import type { ViewTab, LogLine } from "../types";

export function useTabManagement() {
  const [tabs, setTabs] = useState<ViewTab[]>([
    { id: "summary", label: "Overview", type: "summary", closable: false },
  ]);
  const [activeTabId, setActiveTabId] = useState("summary");
  const [nodeReportData, setNodeReportData] = useState<Record<string, any>>({});

  const openLogTab = (nodeId: string, label: string, filterKey: string) => {
    const tabId = `log-${nodeId}`;
    if (!tabs.find((t) => t.id === tabId)) {
      setTabs((prev) => [
        ...prev,
        { id: tabId, label, type: "test-log", filterKey, closable: true },
      ]);
    }
    setActiveTabId(tabId);
  };

  const closeTab = (tabId: string) => {
    setTabs((prev) => prev.filter((t) => t.id !== tabId));
    setActiveTabId((prev) => (prev === tabId ? "summary" : prev));
    // Also clean up report data
    setNodeReportData((prev) => {
      const next = { ...prev };
      delete next[tabId];
      return next;
    });
  };

  const closeOtherTabs = (keepTabId: string) => {
    setTabs((prev) => prev.filter((t) => !t.closable || t.id === keepTabId));
    setActiveTabId((prev) => {
      const surviving = tabs.find((t) => t.id === prev && (!t.closable || t.id === keepTabId));
      return surviving ? prev : keepTabId;
    });
    setNodeReportData((prev) => {
      const next: Record<string, any> = {};
      if (prev[keepTabId]) next[keepTabId] = prev[keepTabId];
      return next;
    });
  };

  const closeAllTabs = () => {
    setTabs((prev) => prev.filter((t) => !t.closable));
    setActiveTabId("summary");
    setNodeReportData({});
  };

  const openReportTab = (
    reportTabId: string,
    label: string,
    filterKey: string,
    reportData: any
  ) => {
    if (tabs.find((t) => t.id === reportTabId)) {
      setActiveTabId(reportTabId);
      return;
    }
    setTabs((prev) => [
      ...prev,
      {
        id: reportTabId,
        label,
        type: "report",
        filterKey,
        closable: true,
      },
    ]);
    setNodeReportData((prev) => ({ ...prev, [reportTabId]: reportData }));
    setActiveTabId(reportTabId);
  };

  const getFilteredLogs = (filterKey: string, logLines: LogLine[]): LogLine[] => {
    if (!filterKey) return logLines;
    // Full unfiltered log
    if (filterKey === "__all__") return logLines;
    // Exact source match for special keys like "setup" and "teardown"
    if (filterKey === "setup") {
      return logLines.filter((line) => line.source === "setup");
    }
    if (filterKey === "teardown") {
      return logLines.filter((line) => line.source === "teardown");
    }
    // Exact match for test nodeids (contain "::")
    if (filterKey.includes("::")) {
      return logLines.filter((line) => line.source === filterKey);
    }
    // File-path prefix match (contains .py)
    if (filterKey.endsWith(".py") || filterKey.includes(".py/") || filterKey.includes(".py\\")) {
      return logLines.filter((line) => line.source.startsWith(filterKey));
    }
    // Fallback: CLI commands or other non-nodeid keys — show all logs
    return logLines;
  };

  return {
    tabs,
    activeTabId,
    setActiveTabId,
    nodeReportData,
    setNodeReportData,
    openLogTab,
    closeTab,
    closeOtherTabs,
    closeAllTabs,
    openReportTab,
    getFilteredLogs,
  };
}
