import { useEffect, useState, useRef, useCallback } from "react";
import { api } from "./services/api";
import type {
  RunOut,
  TestItem,
  ClientOut,
  Theme,
  ExplorerMode,
  LogLine,
  ViewTab,
  TreeNode,
  ReportAvailability,
  TestSuite,
} from "./types";
import { API_BASE } from "./constants";
import { getAllTestIds } from "./utils/tree";
import { useTestStatuses } from "./hooks/useTestStatuses";
import TitleBar from "./components/TitleBar";
import Sidebar from "./components/Sidebar";
import LogPanel from "./components/LogPanel";
import ReportTab from "./components/ReportTab";
import Dashboard from "./components/Dashboard";
import StatusBar from "./components/StatusBar";
import "./App.css";

function App() {
  /* ── State ── */
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("dvp-theme") as Theme) || "dark"
  );
  const [explorerMode, setExplorerMode] = useState<ExplorerMode>("tests");
  const [name, setName] = useState("");
  const [clientKey, setClientKey] = useState("");
  const [resourceName, setResourceName] = useState("default-resource");
  const [tests, setTests] = useState<TestItem[]>([]);
  const [selectedTests, setSelectedTests] = useState<string[]>([]);
  const [testFilter, setTestFilter] = useState("");
  const [run, setRun] = useState<RunOut | null>(null);
  const [logLines, setLogLines] = useState<LogLine[]>([]);
  const [statusMessage, setStatusMessage] = useState("Ready");
  const [isRunning, setIsRunning] = useState(false);
  const [, setWs] = useState<WebSocket | null>(null);
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [tabs, setTabs] = useState<ViewTab[]>([
    { id: "summary", label: "Dashboard", type: "summary", closable: false },
  ]);
  const [activeTabId, setActiveTabId] = useState("summary");
  const [runHistory, setRunHistory] = useState<RunOut[]>([]);
  const [, setClients] = useState<ClientOut[]>([]);
  const [metrics, setMetrics] = useState<any>(null);
  const [reportAvail, setReportAvail] = useState<ReportAvailability>({});
  const [openReportDropdown, setOpenReportDropdown] = useState<string | null>(null);
  const [nodeReportData, setNodeReportData] = useState<Record<string, any>>({});
  const [cliCommand, setCliCommand] = useState("");
  const [testSuites, setTestSuites] = useState<TestSuite[]>([]);
  const [selectedSuiteId, setSelectedSuiteId] = useState<string | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(340);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* ── Derived state ── */
  const { testStatuses, runStats } = useTestStatuses(selectedTests, run, logLines);

  /* ── Theme ── */
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("dvp-theme", theme);
  }, [theme]);

  /* ── Load tests ── */
  useEffect(() => {
    (async () => {
      try {
        const resp = await api.get<TestItem[]>("/tests/discover");
        setTests(resp.data);
        const paths = new Set<string>();
        resp.data.forEach((t) => {
          const parts = t.nodeid.split("/");
          if (parts.length > 0) paths.add(parts[0]);
          if (parts.length > 1) paths.add(parts.slice(0, 2).join("/"));
        });
        setExpandedNodes(paths);
      } catch (e) {
        console.error(e);
      }
    })();
  }, []);

  /* ── Load test suites ── */
  useEffect(() => {
    (async () => {
      try {
        const resp = await api.get<TestSuite[]>("/test-suites");
        setTestSuites(resp.data);
      } catch (e) {
        console.error("Failed to load test suites", e);
      }
    })();
  }, []);

  /* ── Cleanup ── */
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  /* ── Close dropdown on outside click ── */
  useEffect(() => {
    const handler = () => setOpenReportDropdown(null);
    if (openReportDropdown) {
      document.addEventListener("click", handler);
      return () => document.removeEventListener("click", handler);
    }
  }, [openReportDropdown]);

  /* ── Check report availability when run finishes ── */
  useEffect(() => {
    if (run && (run.status === "completed" || run.status === "failed" || run.status === "cancelled")) {
      api
        .get(`/runs/${run.id}/reports`)
        .then((r) => setReportAvail(r.data.available || {}))
        .catch(() => {});
    }
  }, [run?.id, run?.status]);

  /* ── Client registration ── */
  const registerClient = async () => {
    if (!name) {
      setStatusMessage("Enter a client name first");
      return;
    }
    try {
      const resp = await api.post("/clients/register", { name });
      setClientKey(resp.data.client_key);
      setStatusMessage("Client registered");
    } catch {
      setStatusMessage("Registration failed");
    }
  };

  /* ── Tree interactions ── */
  const toggleExpanded = (path: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const toggleNodeSelection = (node: TreeNode) => {
    const ids = getAllTestIds(node);
    const allSelected = ids.length > 0 && ids.every((id) => selectedTests.includes(id));
    if (allSelected) setSelectedTests((prev) => prev.filter((id) => !ids.includes(id)));
    else setSelectedTests((prev) => [...new Set([...prev, ...ids])]);
  };

  /* ── Suite selection ── */
  const selectSuite = (suite: TestSuite) => {
    if (selectedSuiteId === suite.id) {
      setSelectedSuiteId(null);
      setSelectedTests([]);
    } else {
      setSelectedSuiteId(suite.id);
      setSelectedTests(suite.tests);
    }
  };

  /* ── Log tabs ── */
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
    if (activeTabId === tabId) setActiveTabId("summary");
  };

  const getFilteredLogs = (filterKey: string): LogLine[] => {
    if (!filterKey) return logLines;
    return logLines.filter((line) => {
      const src = line.source;
      if (filterKey.includes("::")) return src === filterKey;
      return src.startsWith(filterKey);
    });
  };

  /* ── Run polling setup ── */
  const setupRunPolling = (runId: number) => {
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.hostname}:8000/api/runs/${runId}/logs/ws`;
    const newWs = new WebSocket(wsUrl);
    newWs.onmessage = (event) => {
      try {
        const newLogs: LogLine[] = JSON.parse(event.data);
        setLogLines((prev) => [...prev, ...newLogs]);
      } catch {}
    };
    newWs.onerror = () => console.error("WebSocket error");
    setWs(newWs);

    pollRef.current = setInterval(async () => {
      try {
        const r = await api.get<RunOut>(`/runs/${runId}`);
        setRun(r.data);
        try {
          const logsResp = await api.get<LogLine[]>(`/runs/${runId}/logs`);
          if (logsResp.data.length > 0) setLogLines(logsResp.data);
        } catch {}
        if (r.data.status === "completed" || r.data.status === "failed" || r.data.status === "cancelled") {
          setIsRunning(false);
          setStatusMessage(`Run #${runId} ${r.data.status}`);
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          newWs.close();
          try {
            const rpts = await api.get(`/runs/${runId}/reports`);
            setReportAvail(rpts.data.available || {});
          } catch {}
        } else if (r.data.status === "queued") {
          setStatusMessage(`Run #${runId} queued — waiting for resource...`);
        }
      } catch {}
    }, 2000);
  };

  /* ── Run tests ── */
  const createRun = async () => {
    if (!clientKey) {
      setStatusMessage("Register a client first");
      return;
    }
    if (selectedTests.length === 0) {
      setStatusMessage("Select at least one test");
      return;
    }
    setIsRunning(true);
    setLogLines([]);
    setReportAvail({});
    setStatusMessage("Starting run...");

    try {
      const resp = await api.post("/runs", {
        client_key: clientKey,
        selected_tests: selectedTests,
        resource_name: resourceName,
      });
      setRun(resp.data);
      const fileSet = new Set(selectedTests.map((t) => t.split("::")[0]));
      const fileCount = fileSet.size;
      setStatusMessage(
        `Run #${resp.data.id} — ${selectedTests.length} test(s) across ${fileCount} file(s)${fileCount > 1 ? " (parallel)" : ""}`
      );

      setupRunPolling(resp.data.id);
    } catch {
      setStatusMessage("Failed to create run");
      setIsRunning(false);
    }
  };

  /* ── CLI execution ── */
  const executeCli = async () => {
    if (!clientKey) {
      setStatusMessage("Register a client first");
      return;
    }
    if (!cliCommand.trim()) {
      setStatusMessage("Enter a command");
      return;
    }
    setIsRunning(true);
    setLogLines([]);
    setReportAvail({});
    setStatusMessage("Executing CLI command...");

    try {
      const resp = await api.post("/cli/execute", {
        client_key: clientKey,
        command: cliCommand.trim(),
        resource_name: resourceName,
      });
      setRun(resp.data);
      setStatusMessage(`CLI Run #${resp.data.id} — ${cliCommand.trim()}`);

      setupRunPolling(resp.data.id);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || "Failed to execute command";
      setStatusMessage(detail);
      setIsRunning(false);
    }
  };

  const refreshLogs = async () => {
    if (!run) return;
    try {
      const resp = await api.get<LogLine[]>(`/runs/${run.id}/logs`);
      setLogLines(resp.data);
    } catch {}
  };

  const selectRun = async (r: RunOut) => {
    try {
      const resp = await api.get<RunOut>(`/runs/${r.id}`);
      setRun(resp.data);
    } catch {
      setRun(r);
    }
  };

  const refreshLogsForRun = async (runId: number) => {
    try {
      const resp = await api.get<LogLine[]>(`/runs/${runId}/logs`);
      setLogLines(resp.data);
    } catch {
      setLogLines([]);
    }
  };

  /* ── Cancel / Kill a run ── */
  const cancelRun = async (runId: number) => {
    try {
      await api.post(`/runs/${runId}/cancel`);
      setStatusMessage(`Run #${runId} cancelled`);
      setIsRunning(false);
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      const r = await api.get<RunOut>(`/runs/${runId}`);
      setRun(r.data);
      loadSummaryData();
    } catch (err: any) {
      const detail = err?.response?.data?.detail || "Failed to cancel run";
      setStatusMessage(detail);
    }
  };

  /* ── Reports ── */
  const openReport = (type: string) => {
    if (!run) return;
    const url = `${API_BASE}/runs/${run.id}/reports/${type}?theme=${theme}`;
    window.open(url, "_blank");
    setOpenReportDropdown(null);
  };

  const openNodeReport = async (node: TreeNode) => {
    if (!run) return;
    const tabId = `report-${run.id}-${node.path}`;
    if (tabs.find((t) => t.id === tabId)) {
      setActiveTabId(tabId);
      return;
    }
    try {
      let resp;
      if (node.type === "test" && node.nodeid) {
        resp = await api.get(`/runs/${run.id}/reports/test/${node.nodeid}`);
        if (resp.data.result && !resp.data.summary) {
          resp.data = { ...resp.data, ...resp.data.result, run_id: run.id };
        }
      } else if (node.type === "file") {
        resp = await api.get(`/runs/${run.id}/reports/file/${node.path}`);
      } else {
        return;
      }
      setNodeReportData((prev) => ({ ...prev, [tabId]: resp.data }));
      setTabs((prev) => [
        ...prev,
        {
          id: tabId,
          label: `\u{1F4CB} ${node.name}`,
          type: "report",
          filterKey: tabId,
          closable: true,
        },
      ]);
      setActiveTabId(tabId);
    } catch {
      setStatusMessage(`No report data available for ${node.name}`);
    }
  };

  /* ── Summary data ── */
  const loadSummaryData = useCallback(async () => {
    try {
      const [h, m, c] = await Promise.all([
        api.get<RunOut[]>("/runs"),
        api.get("/metrics"),
        api.get<ClientOut[]>("/clients"),
      ]);
      setRunHistory(h.data);
      setMetrics(m.data);
      setClients(c.data);
    } catch {}
  }, []);

  // Auto-select the latest run when history loads and no run is selected
  useEffect(() => {
    if (!run && runHistory.length > 0) {
      const latest = runHistory[0];
      selectRun(latest);
      refreshLogsForRun(latest.id);
    }
  }, [runHistory]);

  useEffect(() => {
    if (activeTabId === "summary") loadSummaryData();
  }, [activeTabId, loadSummaryData]);

  /* ── Sidebar resize ── */
  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startWidth = sidebarWidth;

      const onMouseMove = (ev: MouseEvent) => {
        const newWidth = Math.min(600, Math.max(220, startWidth + ev.clientX - startX));
        setSidebarWidth(newWidth);
      };
      const onMouseUp = () => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [sidebarWidth]
  );

  /* ── Derived values ── */
  const activeTab = tabs.find((t) => t.id === activeTabId) || tabs[0];

  const canRun =
    clientKey &&
    !isRunning &&
    (explorerMode === "cli" ? cliCommand.trim().length > 0 : selectedTests.length > 0);

  const runButtonLabel = isRunning
    ? "Running\u2026"
    : explorerMode === "cli"
      ? "Execute Command"
      : `Run ${selectedTests.length} Test${selectedTests.length !== 1 ? "s" : ""}`;

  const handleRun = explorerMode === "cli" ? executeCli : createRun;

  /* ══════════ RENDER ══════════ */
  return (
    <div className="dvp-shell">
      <TitleBar
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        clientKey={clientKey}
      />

      <div className="dvp-workspace">
        <Sidebar
          explorerMode={explorerMode}
          onSetExplorerMode={setExplorerMode}
          name={name}
          onSetName={setName}
          clientKey={clientKey}
          onRegisterClient={registerClient}
          resourceName={resourceName}
          onSetResourceName={setResourceName}
          tests={tests}
          selectedTests={selectedTests}
          onSetSelectedTests={setSelectedTests}
          testFilter={testFilter}
          onSetTestFilter={setTestFilter}
          expandedNodes={expandedNodes}
          testStatuses={testStatuses}
          run={run}
          isRunning={isRunning}
          reportAvail={reportAvail}
          openReportDropdown={openReportDropdown}
          onToggleExpanded={toggleExpanded}
          onToggleNodeSelection={toggleNodeSelection}
          onOpenLogTab={openLogTab}
          onOpenNodeReport={openNodeReport}
          onSetReportDropdown={setOpenReportDropdown}
          onOpenReport={openReport}
          testSuites={testSuites}
          selectedSuiteId={selectedSuiteId}
          onSelectSuite={selectSuite}
          cliCommand={cliCommand}
          onSetCliCommand={setCliCommand}
          canRun={!!canRun}
          runButtonLabel={runButtonLabel}
          onRun={handleRun}
          onCancelRun={cancelRun}
          sidebarWidth={sidebarWidth}
          onResizeStart={handleResizeStart}
        />

        {/* Main Content */}
        <div className="dvp-main">
          {/* Tab bar */}
          <div className="dvp-tabbar">
            {tabs.map((tab) => (
              <div
                key={tab.id}
                className={`dvp-tab ${activeTabId === tab.id ? "dvp-tab--active" : ""}`}
                onClick={() => setActiveTabId(tab.id)}
              >
                <span className="dvp-tab__icon">
                  {tab.type === "summary"
                    ? "\u{1F4CA}"
                    : tab.type === "report"
                      ? "\u{1F4CB}"
                      : "\u{1F4DD}"}
                </span>
                {tab.label}
                {tab.type === "test-log" && logLines.length > 0 && (
                  <span className="dvp-tab__badge">
                    {getFilteredLogs(tab.filterKey || "").length}
                  </span>
                )}
                {tab.closable && (
                  <span
                    className="dvp-tab__close"
                    onClick={(e) => {
                      e.stopPropagation();
                      closeTab(tab.id);
                    }}
                  >
                    {"\u00D7"}
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* Tab content */}
          <div className="dvp-tab-content">
            {activeTab.type === "test-log" && activeTab.filterKey && (
              <LogPanel
                lines={getFilteredLogs(activeTab.filterKey)}
                label={activeTab.label}
                run={run}
                isRunning={isRunning}
                onRefreshLogs={refreshLogs}
              />
            )}

            {activeTab.type === "report" && activeTab.filterKey && (
              <ReportTab data={nodeReportData[activeTab.filterKey]} />
            )}

            {activeTab.type === "summary" && (
              <Dashboard
                run={run}
                isRunning={isRunning}
                testStatuses={testStatuses}
                runStats={runStats}
                logLines={logLines}
                reportAvail={reportAvail}
                metrics={metrics}
                runHistory={runHistory}
                onOpenReport={openReport}
                onOpenLogTab={openLogTab}
                onLoadSummaryData={loadSummaryData}
                onSetRun={selectRun}
                onRefreshLogsForRun={refreshLogsForRun}
                onCancelRun={cancelRun}
              />
            )}
          </div>
        </div>
      </div>

      <StatusBar
        isRunning={isRunning}
        statusMessage={statusMessage}
        testsCount={tests.length}
        selectedCount={selectedTests.length}
        explorerMode={explorerMode}
        cliCommand={cliCommand}
        run={run}
      />
    </div>
  );
}

export default App;
