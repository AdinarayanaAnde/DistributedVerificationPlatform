import { useRef, useCallback } from "react";
import type {
  ExplorerMode,
  TestItem,
  TestSuite,
  TreeNode,
  TestStatus,
  RunOut,
  ReportAvailability,
} from "../types";
import { buildTree, getAllTestIds } from "../utils/tree";
import { CLI_EXAMPLES } from "../constants";
import TreeNodeRow from "./TreeNodeRow";

interface SidebarProps {
  explorerMode: ExplorerMode;
  onSetExplorerMode: (mode: ExplorerMode) => void;
  name: string;
  onSetName: (name: string) => void;
  clientKey: string;
  onRegisterClient: () => void;
  resourceName: string;
  onSetResourceName: (name: string) => void;
  tests: TestItem[];
  selectedTests: string[];
  onSetSelectedTests: React.Dispatch<React.SetStateAction<string[]>>;
  testFilter: string;
  onSetTestFilter: (filter: string) => void;
  expandedNodes: Set<string>;
  testStatuses: Record<string, TestStatus>;
  run: RunOut | null;
  isRunning: boolean;
  reportAvail: ReportAvailability;
  openReportDropdown: string | null;
  onToggleExpanded: (path: string) => void;
  onToggleNodeSelection: (node: TreeNode) => void;
  onOpenLogTab: (nodeId: string, label: string, filterKey: string) => void;
  onOpenNodeReport: (node: TreeNode) => void;
  onSetReportDropdown: (path: string | null) => void;
  onOpenReport: (type: string) => void;
  testSuites: TestSuite[];
  selectedSuiteId: string | null;
  onSelectSuite: (suite: TestSuite) => void;
  cliCommand: string;
  onSetCliCommand: (cmd: string) => void;
  canRun: boolean;
  runButtonLabel: string;
  onRun: () => void;
  onCancelRun: (runId: number) => void;
  sidebarWidth: number;
  onResizeStart: (e: React.MouseEvent) => void;
}

export default function Sidebar({
  explorerMode,
  onSetExplorerMode,
  name,
  onSetName,
  clientKey,
  onRegisterClient,
  resourceName,
  onSetResourceName,
  tests,
  selectedTests,
  onSetSelectedTests,
  testFilter,
  onSetTestFilter,
  expandedNodes,
  testStatuses,
  run,
  isRunning,
  reportAvail,
  openReportDropdown,
  onToggleExpanded,
  onToggleNodeSelection,
  onOpenLogTab,
  onOpenNodeReport,
  onSetReportDropdown,
  onOpenReport,
  testSuites,
  selectedSuiteId,
  onSelectSuite,
  cliCommand,
  onSetCliCommand,
  canRun,
  runButtonLabel,
  onRun,
  onCancelRun,
  sidebarWidth,
  onResizeStart,
}: SidebarProps) {
  const filteredTests = tests.filter((t) =>
    t.nodeid.toLowerCase().includes(testFilter.toLowerCase())
  );
  const tree = buildTree(filteredTests);

  const selectAll = () => {
    onSetSelectedTests((prev) => [
      ...new Set([...prev, ...filteredTests.map((t) => t.nodeid)]),
    ]);
  };
  const deselectAll = () => {
    const ids = new Set(filteredTests.map((t) => t.nodeid));
    onSetSelectedTests((prev) => prev.filter((id) => !ids.has(id)));
  };

  return (
    <>
      <div className="dvp-sidebar" style={{ width: sidebarWidth }}>
        {/* Client section */}
        <div className="dvp-sidebar__section">
          <div className="dvp-sidebar__section-title">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
            Client
          </div>
          {!clientKey ? (
            <div className="dvp-inline-form">
              <input
                className="dvp-input"
                value={name}
                onChange={(e) => onSetName(e.target.value)}
                placeholder="Your name or team name"
                onKeyDown={(e) => e.key === "Enter" && onRegisterClient()}
              />
              <button className="dvp-btn dvp-btn--primary dvp-btn--sm" onClick={onRegisterClient}>
                Register
              </button>
            </div>
          ) : (
            <div className="dvp-client-badge">
              {"\u2713"} {name}
              <code title={clientKey}>
                {clientKey.slice(0, 12)}
                {"\u2026"}
              </code>
            </div>
          )}
          <div className="dvp-resource-row">
            <label>Resource:</label>
            <input
              className="dvp-input"
              value={resourceName}
              onChange={(e) => onSetResourceName(e.target.value)}
              style={{ height: 26, fontSize: 11 }}
            />
          </div>
        </div>

        {/* Explorer mode tabs */}
        <div className="dvp-explorer-tabs">
          {(["tests", "suites", "cli"] as const).map((mode) => (
            <button
              key={mode}
              className={`dvp-explorer-tab ${explorerMode === mode ? "dvp-explorer-tab--active" : ""}`}
              onClick={() => onSetExplorerMode(mode)}
            >
              {mode.charAt(0).toUpperCase() + mode.slice(1)}
            </button>
          ))}
        </div>

        {/* Tests explorer */}
        {explorerMode === "tests" && (
          <div className="dvp-test-explorer">
            <div className="dvp-test-explorer__header">
              <div className="dvp-sidebar__section-title" style={{ marginBottom: 0, flex: 1 }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2" />
                  <rect x="9" y="3" width="6" height="4" rx="1" />
                </svg>
                Test Explorer
              </div>
              <span className="dvp-test-counter">
                {selectedTests.length}/{tests.length}
              </span>
            </div>

            <div className="dvp-test-search">
              <input
                className="dvp-input dvp-input--search"
                value={testFilter}
                onChange={(e) => onSetTestFilter(e.target.value)}
                placeholder="Search tests\u2026"
              />
            </div>

            <div className="dvp-test-actions">
              <button className="dvp-btn dvp-btn--ghost dvp-btn--sm" onClick={selectAll}>
                Select All
              </button>
              <button className="dvp-btn dvp-btn--ghost dvp-btn--sm" onClick={deselectAll}>
                Clear
              </button>
            </div>

            <div className="dvp-test-list">
              {tree.map((node) => (
                <TreeNodeRow
                  key={node.path}
                  node={node}
                  depth={0}
                  selectedTests={selectedTests}
                  expandedNodes={expandedNodes}
                  testStatuses={testStatuses}
                  run={run}
                  isRunning={isRunning}
                  reportAvail={reportAvail}
                  openReportDropdown={openReportDropdown}
                  onToggleExpanded={onToggleExpanded}
                  onToggleSelection={onToggleNodeSelection}
                  onOpenLogTab={onOpenLogTab}
                  onOpenNodeReport={onOpenNodeReport}
                  onSetReportDropdown={onSetReportDropdown}
                  onOpenReport={onOpenReport}
                />
              ))}
              {tests.length === 0 && (
                <div
                  style={{
                    padding: 16,
                    textAlign: "center",
                    color: "var(--text-muted)",
                    fontSize: 12,
                  }}
                >
                  No tests discovered
                </div>
              )}
            </div>
          </div>
        )}

        {/* Test Suites */}
        {explorerMode === "suites" && (
          <div className="dvp-test-explorer">
            <div className="dvp-test-explorer__header">
              <div className="dvp-sidebar__section-title" style={{ marginBottom: 0, flex: 1 }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="7" height="7" rx="1" />
                  <rect x="14" y="3" width="7" height="7" rx="1" />
                  <rect x="3" y="14" width="7" height="7" rx="1" />
                  <rect x="14" y="14" width="7" height="7" rx="1" />
                </svg>
                Test Suites
              </div>
              <span className="dvp-test-counter">{testSuites.length}</span>
            </div>

            <div className="dvp-suite-list">
              {testSuites.length === 0 ? (
                <div className="dvp-empty-state">
                  <div className="dvp-empty-state__icon">{"\u{1F4E6}"}</div>
                  <div className="dvp-empty-state__text">Loading suites...</div>
                  <div className="dvp-empty-state__sub">
                    Test suites are auto-generated from your test directory structure
                  </div>
                </div>
              ) : (
                testSuites.map((suite) => (
                  <div
                    key={suite.id}
                    className={`dvp-suite-card ${selectedSuiteId === suite.id ? "dvp-suite-card--selected" : ""}`}
                    onClick={() => onSelectSuite(suite)}
                  >
                    <div className="dvp-suite-card__header">
                      <span className="dvp-suite-card__name">
                        {selectedSuiteId === suite.id ? "\u2611" : "\u2610"} {suite.name}
                      </span>
                      <span className="dvp-suite-card__count">{suite.tests.length} tests</span>
                    </div>
                    <div className="dvp-suite-card__desc">{suite.description}</div>
                    <div className="dvp-suite-card__tags">
                      {suite.tags.map((tag) => (
                        <span key={tag} className="dvp-suite-tag">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* CLI Panel */}
        {explorerMode === "cli" && (
          <div className="dvp-cli-panel">
            <div className="dvp-sidebar__section-title" style={{ marginBottom: 0 }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="4 17 10 11 4 5" />
                <line x1="12" y1="19" x2="20" y2="19" />
              </svg>
              CLI Command
            </div>

            <div className="dvp-cli-hint">
              Run any test command directly. Allowed prefixes:
              <br />
              <code>pytest</code>, <code>python -m pytest</code>, <code>python -m unittest</code>
            </div>

            <input
              className="dvp-cli-input"
              value={cliCommand}
              onChange={(e) => onSetCliCommand(e.target.value)}
              placeholder="pytest tests/ -v --tb=short"
              onKeyDown={(e) => e.key === "Enter" && canRun && onRun()}
            />

            <div className="dvp-sidebar__section-title" style={{ marginBottom: 0, marginTop: 8 }}>
              Quick Examples
            </div>
            <div className="dvp-cli-examples">
              {CLI_EXAMPLES.map((cmd) => (
                <div key={cmd} className="dvp-cli-example" onClick={() => onSetCliCommand(cmd)}>
                  $ {cmd}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Run / Stop buttons */}
        <div className="dvp-sidebar__footer">
          {isRunning && run ? (
            <button
              className="dvp-btn dvp-btn--danger dvp-btn--block dvp-run-btn"
              onClick={() => onCancelRun(run.id)}
            >
              {"\u25A0"} Stop Run #{run.id}
            </button>
          ) : (
            <button
              className="dvp-btn dvp-btn--primary dvp-btn--block dvp-run-btn"
              onClick={onRun}
              disabled={!canRun}
            >
              {"\u25B6"} {runButtonLabel}
            </button>
          )}
        </div>
      </div>
      {/* Resize handle */}
      <div className="dvp-sidebar-resize" onMouseDown={onResizeStart} />
    </>
  );
}
