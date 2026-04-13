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
      for (const id of run.selected_tests) {
        if (!(id in statuses)) continue;
        if (statuses[id] === "done" || statuses[id] === "fail" || statuses[id] === "error") continue;
        const parts = id.split("::");
        const funcName = parts[parts.length - 1];
        if (msg.includes(id) || (funcName && msg.includes(funcName))) {
          if (msg.includes("PASSED")) statuses[id] = "done";
          else if (msg.includes("FAILED")) statuses[id] = "fail";
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
      for (const id of run.selected_tests) {
        if (statuses[id] === "running") {
          statuses[id] = "error";
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
