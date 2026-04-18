import { useState, useRef, useEffect } from "react";
import { api } from "../services/api";
import type { RunOut, LogLine } from "../types";
import { runLabel } from "../utils/format";

export function useRunManagement() {
  const [run, setRun] = useState<RunOut | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [logLines, setLogLines] = useState<LogLine[]>([]);
  const [statusMessage, setStatusMessage] = useState("Ready");
  const [reportAvail, setReportAvail] = useState<Record<string, boolean>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const createRun = async (
    clientKey: string,
    selectedTests: string[],
    resourceName: string,
    suiteIds?: string[],
    setupConfigId?: number | null,
    teardownConfigId?: number | null
  ) => {
    if (!clientKey) {
      setStatusMessage("Register a client first");
      return null;
    }
    if (selectedTests.length === 0) {
      setStatusMessage("Select at least one test");
      return null;
    }
    setIsRunning(true);
    setLogLines([]);
    setReportAvail({});
    setStatusMessage("Starting run...");

    try {
      const body: Record<string, unknown> = {
        client_key: clientKey,
        selected_tests: selectedTests,
        resource_name: resourceName,
      };
      if (suiteIds && suiteIds.length > 0) {
        body.suite_ids = suiteIds;
      }
      if (setupConfigId) {
        body.setup_config_id = setupConfigId;
      }
      if (teardownConfigId) {
        body.teardown_config_id = teardownConfigId;
      }
      const resp = await api.post("/runs", body);
      setRun(resp.data);
      const fileSet = new Set(selectedTests.map((t) => t.split("::")[0]));
      const fileCount = fileSet.size;
      setStatusMessage(
        `${runLabel(resp.data)} — ${selectedTests.length} test(s) across ${fileCount} file(s)${fileCount > 1 ? " (parallel)" : ""}`
      );
      return resp.data;
    } catch {
      setStatusMessage("Failed to create run");
      setIsRunning(false);
      return null;
    }
  };

  const executeCli = async (clientKey: string, command: string, resourceName: string) => {
    if (!clientKey) {
      setStatusMessage("Register a client first");
      return null;
    }
    if (!command.trim()) {
      setStatusMessage("Enter a command");
      return null;
    }
    setIsRunning(true);
    setLogLines([]);
    setReportAvail({});
    setStatusMessage("Executing CLI command...");

    try {
      const resp = await api.post("/cli/execute", {
        client_key: clientKey,
        command: command.trim(),
        resource_name: resourceName,
      });
      setRun(resp.data);
      setStatusMessage(`CLI ${runLabel(resp.data)} — ${command.trim()}`);
      return resp.data;
    } catch (err: any) {
      const detail = err?.response?.data?.detail || "Failed to execute command";
      const traceback = err?.response?.data?.traceback;
      setStatusMessage(traceback ? `${detail}\n\n${traceback}` : detail);
      setIsRunning(false);
      return null;
    }
  };

  const cancelRun = async (runId: number, clientKey: string) => {
    try {
      await api.post(`/runs/${runId}/cancel`, null, { params: { client_key: clientKey } });
      setIsRunning(false);
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      const r = await api.get<RunOut>(`/runs/${runId}`, { params: { client_key: clientKey } });
      setRun(r.data);
      setStatusMessage(`${runLabel(r.data)} cancelled`);
    } catch (err: any) {
      const detail = err?.response?.data?.detail || "Failed to cancel run";
      const traceback = err?.response?.data?.traceback;
      setStatusMessage(traceback ? `${detail}\n\n${traceback}` : detail);
    }
  };

  const refreshLogs = async (clientKey: string) => {
    if (!run) return;
    try {
      const resp = await api.get<LogLine[]>(`/runs/${run.id}/logs`, { params: { client_key: clientKey } });
      setLogLines(resp.data);
    } catch {
      // Silently fail
    }
  };

  const selectRun = async (r: RunOut, clientKey: string) => {
    setLogLines([]);
    try {
      const resp = await api.get<RunOut>(`/runs/${r.id}`, { params: { client_key: clientKey } });
      setRun(resp.data);
      const s = resp.data.status;
      setIsRunning(s === "running" || s === "pending" || s === "queued");
    } catch {
      setRun(r);
      const s = r.status;
      setIsRunning(s === "running" || s === "pending" || s === "queued");
    }
  };

  const refreshLogsForRun = async (runId: number, clientKey: string) => {
    try {
      const resp = await api.get<LogLine[]>(`/runs/${runId}/logs`, { params: { client_key: clientKey } });
      setLogLines(resp.data);
    } catch {
      setLogLines([]);
    }
  };

  return {
    run,
    setRun,
    isRunning,
    setIsRunning,
    logLines,
    setLogLines,
    statusMessage,
    setStatusMessage,
    reportAvail,
    setReportAvail,
    pollRef,
    createRun,
    executeCli,
    cancelRun,
    refreshLogs,
    selectRun,
    refreshLogsForRun,
  };
}
