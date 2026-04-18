import { useMemo } from "react";
import type {
  TestItem,
  TreeNode,
  TestStatus,
  RunOut,
  ReportAvailability,
} from "../types";
import { buildTree } from "../utils/tree";
import { TreeContext, type TreeContextType } from "../contexts/TreeContext";
import TreeNodeRow from "./TreeNodeRow";

interface TestExplorerProps {
  tests: TestItem[];
  testFilter: string;
  onSetTestFilter: (filter: string) => void;
  selectedTests: string[];
  onSetSelectedTests: React.Dispatch<React.SetStateAction<string[]>>;
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
  isLoadingTests?: boolean;
  testDiscoveryError?: string | null;
  onRetryDiscovery?: () => void;
}

export function TestExplorer({
  tests,
  testFilter,
  onSetTestFilter,
  selectedTests,
  onSetSelectedTests,
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
  isLoadingTests,
  testDiscoveryError,
  onRetryDiscovery,
}: TestExplorerProps) {
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
          placeholder="Search tests…"
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
        <TreeContext.Provider
          value={{
            selectedTests,
            expandedNodes,
            testStatuses,
            run,
            isRunning,
            reportAvail,
            openReportDropdown,
            onToggleExpanded,
            onToggleSelection: onToggleNodeSelection,
            onOpenLogTab,
            onOpenNodeReport,
            onSetReportDropdown,
            onOpenReport,
          }}
        >
        {tree.map((node) => (
          <TreeNodeRow
            key={node.path}
            node={node}
            depth={0}
          />
        ))}
        </TreeContext.Provider>
        {tests.length === 0 && !isLoadingTests && !testDiscoveryError && (
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
        {isLoadingTests && (
          <div
            style={{
              padding: 16,
              textAlign: "center",
              color: "var(--text-muted)",
              fontSize: 12,
            }}
          >
            Discovering tests…
          </div>
        )}
        {testDiscoveryError && (
          <div
            style={{
              padding: 16,
              textAlign: "center",
              fontSize: 12,
            }}
          >
            <div style={{ color: "var(--danger, #e74c3c)", marginBottom: 8 }}>
              {testDiscoveryError}
            </div>
            {onRetryDiscovery && (
              <button
                className="dvp-btn dvp-btn--ghost dvp-btn--sm"
                onClick={onRetryDiscovery}
              >
                Retry
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
