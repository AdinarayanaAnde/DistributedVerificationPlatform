export function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return "";
  }
}

export function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "\u2014";
}

export function formatDuration(start: string | null, end: string | null): string {
  if (!start || !end) return "\u2014";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.round(ms / 1000);
  if (secs < 60) return `${secs}s`;
  return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

export function levelClass(level: string): string {
  const l = level.toUpperCase();
  if (l.includes("PASS") || l === "SUCCESS") return "PASS";
  if (l.includes("FAIL") || l === "ERROR") return "FAIL";
  if (l.includes("WARN")) return "WARNING";
  return "INFO";
}
