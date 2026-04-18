import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../services/api";
import { API_BASE } from "../constants";
import type { RunOut, LogLine } from "../types";
import { runLabel } from "../utils/format";

const MAX_RECONNECT_DELAY = 10_000;
const BASE_RECONNECT_DELAY = 1_000;
const HTTP_POLL_INTERVAL = 3_000;

export function useRunPolling(
  runId: number | null,
  clientKey: string | null,
  onRunComplete?: (run: RunOut, reports: Record<string, boolean>) => void,
  onStatusChange?: (status: string) => void
) {
  const [logLines, setLogLines] = useState<LogLine[]>([]);
  const [run, setRun] = useState<RunOut | null>(null);
  const [isWsConnected, setIsWsConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempts = useRef(0);
  const doneRef = useRef(false);

  // Stable callback refs to avoid re-creating the effect
  const onRunCompleteRef = useRef(onRunComplete);
  onRunCompleteRef.current = onRunComplete;
  const onStatusChangeRef = useRef(onStatusChange);
  onStatusChangeRef.current = onStatusChange;

  const cleanup = useCallback(() => {
    if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (reconnectTimer.current) { clearTimeout(reconnectTimer.current); reconnectTimer.current = null; }
    setIsWsConnected(false);
  }, []);

  const fetchRunAndCheckDone = useCallback(async (rid: number, ck: string): Promise<boolean> => {
    const r = await api.get<RunOut>(`/runs/${rid}`, { params: { client_key: ck } });
    setRun(r.data);
    if (r.data.status === "completed" || r.data.status === "failed" || r.data.status === "cancelled") {
      doneRef.current = true;
      cleanup();
      try {
        const rpts = await api.get(`/runs/${rid}/reports`, { params: { client_key: ck } });
        onRunCompleteRef.current?.(r.data, rpts.data.available || {});
      } catch {
        onRunCompleteRef.current?.(r.data, {});
      }
      return true;
    }
    if (r.data.status === "queued") {
      onStatusChangeRef.current?.(`${runLabel(r.data)} queued — waiting for resource...`);
    }
    return false;
  }, [cleanup]);

  useEffect(() => {
    if (!runId || !clientKey) return;

    const rid = runId;
    const ck = clientKey;

    // Reset
    setLogLines([]);
    setRun(null);
    doneRef.current = false;
    reconnectAttempts.current = 0;

    // ── WebSocket connect with auto-reconnect ──
    const connectWs = () => {
      if (doneRef.current) return;

      const wsBase = API_BASE.replace(/^http(s)?:/, (_: string, s: string) => s ? 'wss:' : 'ws:');
      const wsUrl = `${wsBase}/runs/${rid}/logs/ws?client_key=${encodeURIComponent(ck)}`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setIsWsConnected(true);
        reconnectAttempts.current = 0;
        // Stop HTTP fallback while WS is active
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      };

      ws.onmessage = (event) => {
        try {
          const data: LogLine[] = JSON.parse(event.data);
          if (data.length === 0) return; // keepalive ping — ignore

          // Check for server-sent completion sentinel
          const sentinel = data.find((l) => l.level === "__DONE__");
          if (sentinel) {
            // Fetch final run state via HTTP for complete data
            fetchRunAndCheckDone(rid, ck).catch(() => {});
            return;
          }

          setLogLines((prev) => [...prev, ...data]);
        } catch {
          // ignore parse errors
        }
      };

      ws.onerror = () => {
        setIsWsConnected(false);
      };

      ws.onclose = () => {
        setIsWsConnected(false);
        wsRef.current = null;
        if (doneRef.current) return;

        // Start HTTP fallback polling while WS is down
        startHttpPoll();

        // Schedule reconnect with exponential backoff
        const delay = Math.min(BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts.current), MAX_RECONNECT_DELAY);
        reconnectAttempts.current += 1;
        reconnectTimer.current = setTimeout(connectWs, delay);
      };

      wsRef.current = ws;
    };

    // ── HTTP fallback polling (only runs when WS is disconnected) ──
    const startHttpPoll = () => {
      if (pollRef.current || doneRef.current) return;
      pollRef.current = setInterval(async () => {
        if (doneRef.current) { cleanup(); return; }
        try {
          const done = await fetchRunAndCheckDone(rid, ck);
          if (done) return;

          // Fetch logs via HTTP as fallback
          try {
            const logsResp = await api.get<LogLine[]>(`/runs/${rid}/logs`, { params: { client_key: ck } });
            if (logsResp.data.length > 0) setLogLines(logsResp.data);
          } catch { /* silently fail */ }
        } catch { /* silently fail */ }
      }, HTTP_POLL_INTERVAL);
    };

    // Also poll run status periodically (lightweight — just GET /runs/{id})
    // This catches completion even if WS delivery is slightly delayed
    const statusPoll = setInterval(async () => {
      if (doneRef.current) return;
      try { await fetchRunAndCheckDone(rid, ck); } catch { /* ignore */ }
    }, 5_000);

    connectWs();

    return () => {
      cleanup();
      clearInterval(statusPoll);
    };
  }, [runId, clientKey, cleanup, fetchRunAndCheckDone]);

  return { logLines, run, isWsConnected };
}
