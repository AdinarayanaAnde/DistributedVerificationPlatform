import { createContext, useContext } from "react";
import type { TreeNode, TestStatus, RunOut, ReportAvailability } from "../types";

export interface TreeContextType {
  selectedTests: string[];
  expandedNodes: Set<string>;
  testStatuses: Record<string, TestStatus>;
  run: RunOut | null;
  isRunning: boolean;
  reportAvail: ReportAvailability;
  openReportDropdown: string | null;
  onToggleExpanded: (path: string) => void;
  onToggleSelection: (node: TreeNode) => void;
  onOpenLogTab: (nodeId: string, label: string, filterKey: string) => void;
  onOpenNodeReport: (node: TreeNode) => void;
  onSetReportDropdown: (path: string | null) => void;
  onOpenReport: (type: string) => void;
}

export const TreeContext = createContext<TreeContextType | null>(null);

export function useTreeContext() {
  const ctx = useContext(TreeContext);
  if (!ctx) throw new Error("useTreeContext must be used within TreeContext.Provider");
  return ctx;
}
