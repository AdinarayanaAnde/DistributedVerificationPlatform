import type { TreeNode, TestStatus, RunOut, ReportAvailability } from "../types";
import { getAllTestIds, getCheckState, getNodeStatus } from "../utils/tree";
import { STATUS_LABELS } from "../constants";
import { useTreeContext } from "../contexts/TreeContext";
import { useMemo } from "react";

interface TreeNodeRowProps {
  node: TreeNode;
  depth: number;
}

export default function TreeNodeRow({ node, depth }: TreeNodeRowProps) {
  const {
    selectedTests,
    expandedNodes,
    testStatuses,
    run,
    isRunning,
    reportAvail,
    openReportDropdown,
    onToggleExpanded,
    onToggleSelection,
    onOpenLogTab,
    onOpenNodeReport,
    onSetReportDropdown,
    onOpenReport,
  } = useTreeContext();
  const isExpandable = node.type !== "test" && node.children.length > 0;
  const isExpanded = expandedNodes.has(node.path);
  const checkState = getCheckState(node, selectedTests);
  const isSelected = checkState !== "none";
  const status = getNodeStatus(node, testStatuses, selectedTests);

  const icon =
    node.type === "folder"
      ? isExpanded
        ? "\u{1F4C2}"
        : "\u{1F4C1}"
      : node.type === "file"
        ? "\u{1F4C4}"
        : "\u{1F9EA}";

  const nodeFilterKey = node.type === "test" ? node.nodeid! : node.path;

  // Check if this node has tests that were part of the completed run
  const nodeWasRun = useMemo(() => {
    if (!run) return false;
    const runTests = new Set(run.selected_tests);
    if (node.type === "test" && node.nodeid) return runTests.has(node.nodeid);
    const nodeTestIds = getAllTestIds(node);
    return nodeTestIds.some((id) => runTests.has(id));
  }, [run, node]);

  return (
    <div key={node.path}>
      <div
        className={`dvp-tree-item ${isSelected ? "dvp-tree-item--selected" : ""}`}
        style={{ paddingLeft: 8 + depth * 16 }}
      >
        {isExpandable ? (
          <span
            className="dvp-tree-item__arrow"
            onClick={(e) => {
              e.stopPropagation();
              onToggleExpanded(node.path);
            }}
          >
            {isExpanded ? "\u25BE" : "\u25B8"}
          </span>
        ) : (
          <span className="dvp-tree-item__arrow-placeholder" />
        )}
        <input
          type="checkbox"
          className="dvp-tree-item__checkbox"
          checked={checkState === "all"}
          ref={(el) => {
            if (el) el.indeterminate = checkState === "some";
          }}
          onChange={() => onToggleSelection(node)}
          onClick={(e) => e.stopPropagation()}
        />
        <span className="dvp-tree-item__icon">{icon}</span>
        <span
          className="dvp-tree-item__name"
          onClick={() =>
            isExpandable ? onToggleExpanded(node.path) : onToggleSelection(node)
          }
          title={node.path}
        >
          {node.name}
        </span>
        {isSelected && (
          <div className="dvp-tree-actions">
            {status && (
              <button
                className={`dvp-status-btn dvp-status-btn--${status}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenLogTab(node.path, node.name, nodeFilterKey);
                }}
              >
                {status === "running" && <span className="dvp-spinner dvp-spinner--tiny" />}
                {STATUS_LABELS[status]}
              </button>
            )}
          </div>
        )}
        {run &&
          nodeWasRun &&
          (run.status === "completed" || run.status === "failed" || run.status === "cancelled") && (
          <div className="dvp-tree-actions">
            {(node.type === "file" || node.type === "test") && (
                <button
                  className="dvp-report-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenNodeReport(node);
                  }}
                >
                  {"\u{1F4CB}"} Report
                </button>
              )}
            {node.type === "folder" && (
                <div style={{ position: "relative" }}>
                  <button
                    className="dvp-report-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSetReportDropdown(openReportDropdown === node.path ? null : node.path);
                    }}
                  >
                    {"\u{1F4CB}"} Reports
                  </button>
                  {openReportDropdown === node.path && (
                    <div className="dvp-reports-dropdown" onClick={(e) => e.stopPropagation()}>
                      {(
                        [
                          { key: "html", icon: "\u{1F310}", label: "HTML Report" },
                          { key: "junit_xml", icon: "\u{1F4C4}", label: "JUnit XML" },
                          { key: "json", icon: "\u{1F4CA}", label: "JSON Report" },
                          { key: "coverage", icon: "\u{1F4C8}", label: "Coverage" },
                          { key: "allure", icon: "\u{1F3AF}", label: "Allure" },
                        ] as const
                      ).map(({ key, icon: ico, label }) => (
                        <button
                          key={key}
                          className={`dvp-reports-dropdown__item ${
                            !reportAvail[key] ? "dvp-reports-dropdown__item--disabled" : ""
                          }`}
                          onClick={() => reportAvail[key] && onOpenReport(key)}
                        >
                          <span className="dvp-reports-dropdown__icon">{ico}</span>
                          <span className="dvp-reports-dropdown__label">{label}</span>
                          <span
                            className={`dvp-reports-dropdown__badge ${
                              reportAvail[key]
                                ? "dvp-reports-dropdown__badge--ready"
                                : "dvp-reports-dropdown__badge--na"
                            }`}
                          >
                            {reportAvail[key] ? "Ready" : "N/A"}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
          </div>
        )}
      </div>
      {isExpandable &&
        isExpanded &&
        node.children.map((child) => (
          <TreeNodeRow
            key={child.path}
            node={child}
            depth={depth + 1}
          />
        ))}
    </div>
  );
}
