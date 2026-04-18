export interface TestItem {
  nodeid: string;
  path: string;
  function: string;
}

export interface RunOut {
  id: number;
  run_name: string | null;
  client_id: number;
  resource_id: number | null;
  selected_tests: string[];
  setup_config_id: number | null;
  setup_status: string | null;
  teardown_config_id: number | null;
  teardown_status: string | null;
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
export type ExplorerMode = "tests" | "suites" | "cli" | "setup" | "teardown" | "upload";
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
  source: "auto" | "custom" | "marker";
  estimated_duration?: number | null;
  last_run?: { run_id: number; run_name?: string | null; status: string; timestamp: string } | null;
}

export interface SetupStep {
  id?: number;
  name: string;
  step_type: string;
  command: string;
  timeout: number;
  order?: number;
  on_failure: string;
  env_vars?: Record<string, string> | null;
}

export interface SetupConfiguration {
  id: number;
  name: string;
  description: string;
  steps: SetupStep[];
  created_by?: number | null;
  created_at: string;
  updated_at: string;
}

export interface TeardownStep {
  id?: number;
  name: string;
  step_type: string;
  command: string;
  timeout: number;
  order?: number;
  on_failure: string;
  env_vars?: Record<string, string> | null;
}

export interface TeardownConfiguration {
  id: number;
  name: string;
  description: string;
  steps: TeardownStep[];
  created_by?: number | null;
  created_at: string;
  updated_at: string;
}
