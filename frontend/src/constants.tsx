import type { TestStatus } from "./types";

export const STATUS_LABELS: Record<TestStatus, string> = {
  "not-started": "Not started",
  running: "Running",
  done: "Done",
  fail: "Fail",
  error: "Error",
  cancelled: "Cancelled",
};

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "/api";

export const CLI_EXAMPLES = [
  "pytest tests/ -v",
  "pytest tests/unit/ -v --tb=short",
  "pytest tests/smoke/ -v",
  "python -m pytest tests/ -k 'test_basic'",
  "pytest tests/ --co -q",
];
