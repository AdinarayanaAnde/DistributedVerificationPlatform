import { useMemo } from "react";
import type { TestStatus, RunOut, LogLine } from "../types";

interface RunStats {
  total: number;
  passed: number;
  failed: number;
  errors: number;
  running: number;
  notStarted: number;
  cancelled: number;
}

export function useTestStatuses(
  selectedTests: string[],
  run: RunOut | null,
  logLines: LogLine[]
): { testStatuses: Record<string, TestStatus>; runStats: RunStats } {
  const testStatuses = useMemo<Record<string, TestStatus>>(() => {
    const statuses: Record<string, TestStatus> = {};
    for (const id of selectedTests) statuses[id] = "not-started";
    if (!run) return statuses;
    for (const id of run.selected_tests) {
      statuses[id] = "running";
    }
    for (const line of logLines) {
      const msg = line.message;
      const src = line.source || "";
      for (const id of run.selected_tests) {
        if (!(id in statuses)) continue;
        if (statuses[id] === "done" || statuses[id] === "fail" || statuses[id] === "error") continue;
        const parts = id.split("::");
        const funcName = parts[parts.length - 1];
        // Match by message content OR by source field (which carries the test nodeid)
        const matchesById = msg.includes(id) || (funcName && msg.includes(funcName));
        const matchesBySource = src === id;
        if (matchesById || matchesBySource) {
          if (msg.includes("PASSED") || (matchesBySource && line.level === "PASS")) statuses[id] = "done";
          else if (msg.includes("FAILED") || (matchesBySource && line.level === "FAIL" && !msg.startsWith("==="))) statuses[id] = "fail";
          else if (
            line.level === "FAIL" &&
            /\bERROR\b/.test(msg) &&
            !msg.match(/\d+\s+error/i) &&
            !msg.includes("short test summary")
          )
            statuses[id] = "error";
        }
      }
    }
    if (run.status === "cancelled") {
      for (const id of run.selected_tests) {
        if (statuses[id] === "running") {
          statuses[id] = "cancelled";
        }
      }
    } else if (run.status === "completed") {
      for (const id of run.selected_tests) {
        if (statuses[id] === "running") {
          statuses[id] = "done";
        }
      }
    } else if (run.status === "failed") {
      // Run "failed" means at least one test failed, but others may have passed.
      // Only mark remaining "running" tests as "done" — the actually failed ones
      // were already set to "fail"/"error" from log parsing above.
      for (const id of run.selected_tests) {
        if (statuses[id] === "running") {
          statuses[id] = "done";
        }
      }
    }
    return statuses;
  }, [selectedTests, run, logLines]);

  const runStats = useMemo<RunStats>(() => {
    const vals = Object.values(testStatuses);
    return {
      total: vals.length,
      passed: vals.filter((s) => s === "done").length,
      failed: vals.filter((s) => s === "fail").length,
      errors: vals.filter((s) => s === "error").length,
      running: vals.filter((s) => s === "running").length,
      notStarted: vals.filter((s) => s === "not-started").length,
      cancelled: vals.filter((s) => s === "cancelled").length,
    };
  }, [testStatuses]);

  return { testStatuses, runStats };
}
