export interface TestItem {
  nodeid: string;
  path: string;
  function: string;
}

export interface RunOut {
  id: number;
  client_id: number;
  resource_id: number | null;
  selected_tests: string[];
  status: string;
  note: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ClientOut {
  id: number;
  client_key: string;
  name: string;
  created_at: string;
}

export type Theme = "dark" | "light";
export type ExplorerMode = "tests" | "suites" | "cli";
export type TestStatus = "not-started" | "running" | "done" | "fail" | "error" | "cancelled";

export interface LogLine {
  timestamp: string;
  level: string;
  source: string;
  message: string;
}

export interface ViewTab {
  id: string;
  label: string;
  type: "summary" | "test-log" | "report";
  filterKey?: string;
  closable: boolean;
}

export interface TreeNode {
  name: string;
  path: string;
  type: "folder" | "file" | "test";
  children: TreeNode[];
  nodeid?: string;
}

export interface ReportAvailability {
  junit_xml?: boolean;
  html?: boolean;
  json?: boolean;
  coverage?: boolean;
  allure?: boolean;
  per_test?: boolean;
}

export interface TestSuite {
  id: string;
  name: string;
  description: string;
  tests: string[];
  tags: string[];
}
