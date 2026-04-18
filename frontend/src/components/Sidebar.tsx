import { useCallback } from "react";
import type {
  ExplorerMode,
  TestItem,
  TestSuite,
  TreeNode,
  TestStatus,
  RunOut,
  ReportAvailability,
} from "../types";
import { ClientRegistrationPanel } from "./ClientRegistrationPanel";
import { ExplorerTabs } from "./ExplorerTabs";
import { TestExplorer } from "./TestExplorer";
import { TestSuitesPanel } from "./TestSuitesPanel";
import { CliPanel } from "./CliPanel";
import { SetupPanel } from "./SetupPanel";
import { TeardownPanel } from "./TeardownPanel";
import { UploadPanel } from "./UploadPanel";
import { RunControls } from "./RunControls";

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
  selectedSuiteIds: string[];
  onToggleSuite: (suite: TestSuite) => void;
  onCreateSuite: (name: string, description: string, tests: string[], tags: string[]) => Promise<boolean>;
  onDeleteSuite: (suiteId: string) => Promise<boolean>;
  cliCommand: string;
  onSetCliCommand: (cmd: string) => void;
  selectedSetupConfigId: number | null;
  onSelectSetupConfig: (id: number | null) => void;
  selectedTeardownConfigId: number | null;
  onSelectTeardownConfig: (id: number | null) => void;
  onRefreshTests?: () => void;
  isLoadingTests?: boolean;
  testDiscoveryError?: string | null;
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
  selectedSuiteIds,
  onToggleSuite,
  onCreateSuite,
  onDeleteSuite,
  cliCommand,
  onSetCliCommand,
  selectedSetupConfigId,
  onSelectSetupConfig,
  selectedTeardownConfigId,
  onSelectTeardownConfig,
  onRefreshTests,
  isLoadingTests,
  testDiscoveryError,
  canRun,
  runButtonLabel,
  onRun,
  onCancelRun,
  sidebarWidth,
  onResizeStart,
}: SidebarProps) {
  const handleResizeStart = useCallback(
    (e: React.MouseEvent) => {
      onResizeStart(e);
    },
    [onResizeStart]
  );

  return (
    <>
      <div className="dvp-sidebar" style={{ width: sidebarWidth }}>
        {/* Client Section */}
        <ClientRegistrationPanel
          name={name}
          onSetName={onSetName}
          clientKey={clientKey}
          onRegisterClient={onRegisterClient}
          resourceName={resourceName}
          onSetResourceName={onSetResourceName}
        />

        {/* Explorer Mode Tabs */}
        <ExplorerTabs explorerMode={explorerMode} onSetExplorerMode={onSetExplorerMode} clientKey={clientKey} />

        {/* Tests Explorer */}
        {explorerMode === "tests" && (
          <TestExplorer
            tests={tests}
            testFilter={testFilter}
            onSetTestFilter={onSetTestFilter}
            selectedTests={selectedTests}
            onSetSelectedTests={onSetSelectedTests}
            expandedNodes={expandedNodes}
            testStatuses={testStatuses}
            run={run}
            isRunning={isRunning}
            reportAvail={reportAvail}
            openReportDropdown={openReportDropdown}
            onToggleExpanded={onToggleExpanded}
            onToggleNodeSelection={onToggleNodeSelection}
            onOpenLogTab={onOpenLogTab}
            onOpenNodeReport={onOpenNodeReport}
            onSetReportDropdown={onSetReportDropdown}
            onOpenReport={onOpenReport}
            isLoadingTests={isLoadingTests}
            testDiscoveryError={testDiscoveryError}
            onRetryDiscovery={onRefreshTests}
          />
        )}

        {/* Test Suites */}
        {explorerMode === "suites" && (
          <TestSuitesPanel
            testSuites={testSuites}
            selectedSuiteIds={selectedSuiteIds}
            onToggleSuite={onToggleSuite}
            onCreateSuite={onCreateSuite}
            onDeleteSuite={onDeleteSuite}
            selectedTests={selectedTests}
          />
        )}

        {/* CLI Panel */}
        {explorerMode === "cli" && (
          <CliPanel
            cliCommand={cliCommand}
            onSetCliCommand={onSetCliCommand}
            canRun={canRun}
            onRun={onRun}
          />
        )}

        {/* Setup Panel */}
        {explorerMode === "setup" && (
          <SetupPanel
            selectedConfigId={selectedSetupConfigId}
            onSelectConfig={onSelectSetupConfig}
          />
        )}

        {/* Teardown Panel */}
        {explorerMode === "teardown" && (
          <TeardownPanel
            selectedConfigId={selectedTeardownConfigId}
            onSelectConfig={onSelectTeardownConfig}
          />
        )}

        {/* Upload Panel */}
        {explorerMode === "upload" && clientKey && (
          <UploadPanel clientKey={clientKey} onUploadComplete={onRefreshTests} />
        )}

        {/* Run/Stop Buttons */}
        <RunControls
          isRunning={isRunning}
          run={run}
          canRun={canRun}
          runButtonLabel={runButtonLabel}
          onRun={onRun}
          onCancelRun={onCancelRun}
        />
      </div>

      {/* Resize handle */}
      <div className="dvp-sidebar-resize" onMouseDown={handleResizeStart} />
    </>
  );
}
