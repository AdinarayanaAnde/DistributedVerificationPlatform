import { useEffect, useState, useCallback, useRef } from "react";
import { AppProvider, useAppContext } from "./contexts/AppContext";
import { api } from "./services/api";
import type { RunOut, LogLine, TreeNode } from "./types";
import { API_BASE } from "./constants";
import { runLabel } from "./utils/format";
import { useTestStatuses } from "./hooks/useTestStatuses";
import { useRunPolling } from "./hooks/useRunPolling";
import TitleBar from "./components/TitleBar";
import Sidebar from "./components/Sidebar";
import LogPanel from "./components/LogPanel";
import ReportTab from "./components/ReportTab";
import Dashboard from "./components/Dashboard";
import StatusBar from "./components/StatusBar";
import ErrorModal from "./components/ErrorModal";
import "./App.css";

function AppContent() {
  const ctx = useAppContext();
  const { client, runMgmt, testMgmt, tabs, theme } = ctx;

  /* ── Local UI state ── */
  const [errorModal, setErrorModal] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [runHistory, setRunHistory] = useState<RunOut[]>([]);
  const [metrics, setMetrics] = useState<any>(null);
  const [openReportDropdown, setOpenReportDropdown] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<number | null>(null);
  const [tabContextMenu, setTabContextMenu] = useState<{ x: number; y: number; tabId: string } | null>(null);
  const ctxMenuRef = useRef<HTMLDivElement>(null);
  const loadSummaryDataRef = useRef<() => void>(() => {});

  /* ── Derived state ── */
  const { testStatuses, runStats } = useTestStatuses(
    testMgmt.selectedTests,
    runMgmt.run,
    runMgmt.logLines,
  );

  /* ── Run polling ── */
  const onRunComplete = useCallback(
    (completedRun: RunOut, reports: Record<string, boolean>) => {
      runMgmt.setRun(completedRun);
      runMgmt.setIsRunning(false);
      runMgmt.setReportAvail(reports);
      runMgmt.setStatusMessage(`${runLabel(completedRun)} ${completedRun.status}`);
      setActiveRunId(null);
      // Immediately patch the completed run into local history so the
      // dropdown reflects the new status without waiting for the network.
      setRunHistory((prev) =>
        prev.map((r) => (r.id === completedRun.id ? completedRun : r))
      );
      loadSummaryDataRef.current();
    },
    [],
  );

  const onStatusChange = useCallback(
    (status: string) => {
      runMgmt.setStatusMessage(status);
    },
    [],
  );

  const polling = useRunPolling(activeRunId, client.clientKey, onRunComplete, onStatusChange);

  // Sync polling logs/run into runMgmt
  useEffect(() => {
    if (polling.logLines.length > 0) {
      runMgmt.setLogLines(polling.logLines);
    }
  }, [polling.logLines]);

  useEffect(() => {
    if (polling.run) {
      runMgmt.setRun(polling.run);
    }
  }, [polling.run]);

  /* ── Listen for backend unavailability ── */
  useEffect(() => {
    const handler = (e: any) => {
      setErrorModal(e.detail?.message || "Backend server is unavailable.");
    };
    window.addEventListener("api-unavailable", handler);
    return () => window.removeEventListener("api-unavailable", handler);
  }, []);

  /* ── Close tab context menu on outside click ── */
  useEffect(() => {
    if (!tabContextMenu) return;
    const handler = (e: MouseEvent) => {
      if (ctxMenuRef.current && !ctxMenuRef.current.contains(e.target as Node)) {
        setTabContextMenu(null);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [tabContextMenu]);

  /* ── Proactive backend health polling ── */
  useEffect(() => {
    let pollTimer: ReturnType<typeof setTimeout>;
    let cancelled = false;
    const pollHealth = async () => {
      try {
        await api.get("/health");
        if (!cancelled && errorModal) setErrorModal(null);
      } catch {
        if (!cancelled && !errorModal)
          setErrorModal("Backend server is unavailable. Please check your connection and try again.");
      } finally {
        if (!cancelled) pollTimer = setTimeout(pollHealth, 10000);
      }
    };
    pollTimer = setTimeout(pollHealth, 10000);
    return () => {
      cancelled = true;
      clearTimeout(pollTimer);
    };
  }, [errorModal]);

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
    const run = runMgmt.run;
    if (run && client.clientKey && (run.status === "completed" || run.status === "failed" || run.status === "cancelled")) {
      api
        .get(`/runs/${run.id}/reports`, { params: { client_key: client.clientKey } })
        .then((r) => runMgmt.setReportAvail(r.data.available || {}))
        .catch(() => {});
    }
  }, [runMgmt.run?.id, runMgmt.run?.status, client.clientKey]);

  /* ── Manual retry handler ── */
  const handleRetry = async () => {
    setRetrying(true);
    try {
      await api.get("/health");
      setErrorModal(null);
    } catch {
      // keep modal open
    } finally {
      setRetrying(false);
    }
  };

  /* ── Run tests ── */
  const handleCreateRun = async () => {
    const result = await runMgmt.createRun(
      client.clientKey,
      testMgmt.selectedTests,
      client.resourceName,
      testMgmt.selectedSuiteIds.length > 0 ? testMgmt.selectedSuiteIds : undefined,
      ctx.selectedSetupConfigId,
      ctx.selectedTeardownConfigId,
    );
    if (result) {
      setActiveRunId(result.id);
      loadSummaryData();
    }
  };

  /* ── CLI execution ── */
  const handleExecuteCli = async () => {
    const result = await runMgmt.executeCli(
      client.clientKey,
      ctx.cliCommand,
      client.resourceName,
    );
    if (result) {
      setActiveRunId(result.id);
      loadSummaryData();
    }
  };

  /* ── Cancel run ── */
  const handleCancelRun = async (runId: number) => {
    await runMgmt.cancelRun(runId, client.clientKey);
    setActiveRunId(null);
    loadSummaryData();
  };

  /* ── Reports ── */
  const openReport = (type: string) => {
    if (!runMgmt.run) return;
    const url = `${API_BASE}/runs/${runMgmt.run.id}/reports/${type}?theme=${theme.value}&client_key=${encodeURIComponent(client.clientKey)}`;
    window.open(url, "_blank");
    setOpenReportDropdown(null);
  };

  const openNodeReport = async (node: TreeNode) => {
    if (!runMgmt.run) return;
    const tabId = `report-${runMgmt.run.id}-${node.path}`;
    if (tabs.tabs.find((t) => t.id === tabId)) {
      tabs.setActiveTabId(tabId);
      return;
    }
    try {
      let resp;
      const ck = { params: { client_key: client.clientKey } };
      if (node.type === "test" && node.nodeid) {
        resp = await api.get(`/runs/${runMgmt.run.id}/reports/test/${node.nodeid}`, ck);
        if (resp.data.result && !resp.data.summary) {
          resp.data = { ...resp.data, ...resp.data.result, run_id: runMgmt.run.id };
        }
      } else if (node.type === "file") {
        resp = await api.get(`/runs/${runMgmt.run.id}/reports/file/${node.path}`, ck);
      } else {
        return;
      }
      tabs.openReportTab(tabId, `📋 ${node.name}`, tabId, resp.data);
    } catch {
      runMgmt.setStatusMessage(`No report data available for ${node.name}`);
    }
  };

  /* ── Summary data ── */
  const loadSummaryData = useCallback(async () => {
    if (!client.clientKey) return;
    try {
      const [h, m] = await Promise.all([
        api.get<RunOut[]>("/runs", { params: { client_key: client.clientKey } }),
        api.get("/metrics", { params: { client_key: client.clientKey } }),
      ]);
      setRunHistory(h.data);
      setMetrics(m.data);
    } catch {}
  }, [client.clientKey]);

  // Keep the ref in sync so onRunComplete always calls the latest version
  loadSummaryDataRef.current = loadSummaryData;

  // Auto-select the latest run when history loads and no run is selected
  useEffect(() => {
    if (!runMgmt.run && runHistory.length > 0 && client.clientKey) {
      const latest = runHistory[0];
      runMgmt.selectRun(latest, client.clientKey);
      runMgmt.refreshLogsForRun(latest.id, client.clientKey);
    }
  }, [runHistory, client.clientKey]);

  useEffect(() => {
    if (tabs.activeTabId === "summary" && client.clientKey) loadSummaryData();
  }, [tabs.activeTabId, loadSummaryData, client.clientKey]);

  /* ── Derived values ── */
  const activeTab = tabs.tabs.find((t) => t.id === tabs.activeTabId) || tabs.tabs[0];

  const canRun =
    client.clientKey &&
    !runMgmt.isRunning &&
    (ctx.explorerMode === "cli"
      ? ctx.cliCommand.trim().length > 0
      : testMgmt.selectedTests.length > 0);

  const runButtonLabel = runMgmt.isRunning
    ? "Running\u2026"
    : ctx.explorerMode === "cli"
      ? "Execute Command"
      : `Run ${testMgmt.selectedTests.length} Test${testMgmt.selectedTests.length !== 1 ? "s" : ""}`;

  const handleRun = ctx.explorerMode === "cli" ? handleExecuteCli : handleCreateRun;

  /* ══════════ RENDER ══════════ */
  return (
    <div className="dvp-shell">
      <TitleBar
        theme={theme.value}
        onToggleTheme={theme.toggle}
        clientKey={client.clientKey}
      />

      <div className="dvp-workspace">
        <Sidebar
          explorerMode={ctx.explorerMode}
          onSetExplorerMode={ctx.setExplorerMode}
          name={client.name}
          onSetName={client.setName}
          clientKey={client.clientKey}
          onRegisterClient={client.registerClient}
          resourceName={client.resourceName}
          onSetResourceName={client.setResourceName}
          tests={testMgmt.tests}
          selectedTests={testMgmt.selectedTests}
          onSetSelectedTests={testMgmt.setSelectedTests}
          testFilter={testMgmt.testFilter}
          onSetTestFilter={testMgmt.setTestFilter}
          expandedNodes={testMgmt.expandedNodes}
          testStatuses={testStatuses}
          run={runMgmt.run}
          isRunning={runMgmt.isRunning}
          reportAvail={runMgmt.reportAvail}
          openReportDropdown={openReportDropdown}
          onToggleExpanded={testMgmt.toggleExpanded}
          onToggleNodeSelection={testMgmt.toggleNodeSelection}
          onOpenLogTab={tabs.openLogTab}
          onOpenNodeReport={openNodeReport}
          onSetReportDropdown={setOpenReportDropdown}
          onOpenReport={openReport}
          testSuites={testMgmt.testSuites}
          selectedSuiteIds={testMgmt.selectedSuiteIds}
          onToggleSuite={testMgmt.toggleSuite}
          onCreateSuite={testMgmt.createCustomSuite}
          onDeleteSuite={testMgmt.deleteCustomSuite}
          cliCommand={ctx.cliCommand}
          onSetCliCommand={ctx.setCliCommand}
          selectedSetupConfigId={ctx.selectedSetupConfigId}
          onSelectSetupConfig={ctx.setSelectedSetupConfigId}
          selectedTeardownConfigId={ctx.selectedTeardownConfigId}
          onSelectTeardownConfig={ctx.setSelectedTeardownConfigId}
          onRefreshTests={testMgmt.refreshTests}
          isLoadingTests={testMgmt.isLoadingTests}
          testDiscoveryError={testMgmt.testDiscoveryError}
          canRun={!!canRun}
          runButtonLabel={runButtonLabel}
          onRun={handleRun}
          onCancelRun={handleCancelRun}
          sidebarWidth={ctx.sidebarWidth}
          onResizeStart={ctx.onResizeStart}
        />

        {/* Main Content */}
        <div className="dvp-main">
          {/* Tab bar */}
          <div className="dvp-tabbar">
            {tabs.tabs.map((tab) => (
              <div
                key={tab.id}
                className={`dvp-tab ${tabs.activeTabId === tab.id ? "dvp-tab--active" : ""}`}
                onClick={() => tabs.setActiveTabId(tab.id)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setTabContextMenu({ x: e.clientX, y: e.clientY, tabId: tab.id });
                }}
              >
                <span className="dvp-tab__icon">
                  {tab.type === "summary"
                    ? "\u{1F4CA}"
                    : tab.type === "report"
                      ? "\u{1F4CB}"
                      : "\u{1F4DD}"}
                </span>
                {tab.label}
                {tab.type === "test-log" && runMgmt.logLines.length > 0 && (
                  <span className="dvp-tab__badge">
                    {tabs.getFilteredLogs(tab.filterKey || "", runMgmt.logLines).length}
                  </span>
                )}
                {tab.closable && (
                  <span
                    className="dvp-tab__close"
                    onClick={(e) => {
                      e.stopPropagation();
                      tabs.closeTab(tab.id);
                    }}
                  >
                    {"\u00D7"}
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* Tab context menu */}
          {tabContextMenu && (
            <div
              ref={ctxMenuRef}
              className="dvp-tab-context-menu"
              style={{ top: tabContextMenu.y, left: tabContextMenu.x }}
            >
              {tabs.tabs.find((t) => t.id === tabContextMenu.tabId)?.closable && (
                <button
                  className="dvp-tab-context-menu__item"
                  onClick={() => { tabs.closeTab(tabContextMenu.tabId); setTabContextMenu(null); }}
                >
                  Close
                </button>
              )}
              <button
                className="dvp-tab-context-menu__item"
                onClick={() => { tabs.closeOtherTabs(tabContextMenu.tabId); setTabContextMenu(null); }}
                disabled={tabs.tabs.filter((t) => t.closable && t.id !== tabContextMenu.tabId).length === 0}
              >
                Close Others
              </button>
              <button
                className="dvp-tab-context-menu__item"
                onClick={() => { tabs.closeAllTabs(); setTabContextMenu(null); }}
                disabled={tabs.tabs.filter((t) => t.closable).length === 0}
              >
                Close All
              </button>
            </div>
          )}

          {/* Tab content */}
          <div className="dvp-tab-content">
            {activeTab.type === "test-log" && activeTab.filterKey && (
              <LogPanel
                lines={tabs.getFilteredLogs(activeTab.filterKey, runMgmt.logLines)}
                label={activeTab.label}
                run={runMgmt.run}
                isRunning={runMgmt.isRunning}
                onRefreshLogs={() => runMgmt.refreshLogs(client.clientKey)}
              />
            )}

            {activeTab.type === "report" && activeTab.filterKey && (
              <ReportTab data={tabs.nodeReportData[activeTab.filterKey]} />
            )}

            {activeTab.type === "summary" && (
              <Dashboard
                run={runMgmt.run}
                isRunning={runMgmt.isRunning}
                testStatuses={testStatuses}
                runStats={runStats}
                logLines={runMgmt.logLines}
                reportAvail={runMgmt.reportAvail}
                metrics={metrics}
                runHistory={runHistory}
                clientKey={client.clientKey}
                onOpenReport={openReport}
                onOpenLogTab={tabs.openLogTab}
                onLoadSummaryData={loadSummaryData}
                onSetRun={(r: RunOut) => runMgmt.selectRun(r, client.clientKey)}
                onRefreshLogsForRun={(id: number) => runMgmt.refreshLogsForRun(id, client.clientKey)}
                onCancelRun={handleCancelRun}
              />
            )}
          </div>
        </div>
      </div>

      <StatusBar
        isRunning={runMgmt.isRunning}
        statusMessage={client.statusMessage || runMgmt.statusMessage}
        testsCount={testMgmt.tests.length}
        selectedCount={testMgmt.selectedTests.length}
        explorerMode={ctx.explorerMode}
        cliCommand={ctx.cliCommand}
        run={runMgmt.run}
      />

      {/* Error Modal */}
      {errorModal && (
        <ErrorModal
          message={errorModal}
          onClose={() => setErrorModal(null)}
          onRetry={handleRetry}
          retrying={retrying}
        />
      )}
    </div>
  );
}

function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}

export default App;
