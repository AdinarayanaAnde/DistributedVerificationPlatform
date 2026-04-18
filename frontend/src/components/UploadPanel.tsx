import { useState, useCallback, useEffect } from "react";
import { api } from "../services/api";

interface UploadPanelProps {
  clientKey: string;
  onUploadComplete?: () => void;
}

interface UploadEntry {
  upload_id: string;
  label: string;
  files_count: number;
  created_at: string;
}

interface UploadResult {
  upload_id: string;
  files: string[];
  total_files: number;
  path: string;
  cleanup_after_minutes: number;
}

export function UploadPanel({ clientKey, onUploadComplete }: UploadPanelProps) {
  const [uploads, setUploads] = useState<UploadEntry[]>([]);
  const [uploading, setUploading] = useState(false);
  const [lastResult, setLastResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const loadUploads = useCallback(async () => {
    if (!clientKey) return;
    try {
      const resp = await api.get<UploadEntry[]>("/tests/uploads", {
        params: { client_key: clientKey },
      });
      setUploads(resp.data);
    } catch {
      /* ignore */
    }
  }, [clientKey]);

  useEffect(() => {
    loadUploads();
  }, [loadUploads]);

  const handleUpload = useCallback(
    async (file: File) => {
      if (!file.name.endsWith(".zip")) {
        setError("Only .zip files are accepted");
        return;
      }
      if (file.size > 50 * 1024 * 1024) {
        setError("File too large (max 50 MB)");
        return;
      }

      setUploading(true);
      setError(null);
      setLastResult(null);

      const formData = new FormData();
      formData.append("file", file);

      try {
        const resp = await api.post<UploadResult>(
          `/tests/upload?client_key=${encodeURIComponent(clientKey)}`,
          formData,
          { headers: { "Content-Type": "multipart/form-data" } },
        );
        setLastResult(resp.data);
        loadUploads();
        onUploadComplete?.();
      } catch (e: any) {
        setError(e?.response?.data?.detail || "Upload failed");
      } finally {
        setUploading(false);
      }
    },
    [clientKey, loadUploads, onUploadComplete],
  );

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const handleDelete = async (uploadId: string) => {
    try {
      await api.delete(`/tests/uploads/${uploadId}`, {
        params: { client_key: clientKey },
      });
      setUploads((prev) => prev.filter((u) => u.upload_id !== uploadId));
      onUploadComplete?.();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="dvp-panel-scroll" style={{ padding: 8 }}>
      <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-muted)", marginBottom: 8 }}>
        Upload Tests
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        style={{
          border: `2px dashed ${dragOver ? "var(--accent)" : "var(--border)"}`,
          borderRadius: 6,
          padding: 16,
          textAlign: "center",
          cursor: "pointer",
          background: dragOver ? "var(--accent-bg)" : "transparent",
          transition: "all 0.2s",
          marginBottom: 10,
        }}
        onClick={() => document.getElementById("upload-input")?.click()}
      >
        <input
          id="upload-input"
          type="file"
          accept=".zip"
          onChange={handleFileInput}
          style={{ display: "none" }}
        />
        {uploading ? (
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>Uploading…</span>
        ) : (
          <>
            <div style={{ fontSize: 24, marginBottom: 4 }}>📁</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
              Drag &amp; drop a .zip file here<br />or click to browse
            </div>
            <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
              Max 50 MB · Auto-cleaned after 10 min
            </div>
          </>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{ fontSize: 11, color: "var(--error)", marginBottom: 8, padding: "4px 8px", background: "var(--error-bg)", borderRadius: 4 }}>
          {error}
        </div>
      )}

      {/* Last upload result */}
      {lastResult && (
        <div style={{ fontSize: 11, padding: 8, background: "var(--success-bg)", borderRadius: 4, marginBottom: 10, border: "1px solid var(--success)" }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>✅ Upload successful</div>
          <div>{lastResult.total_files} test file(s) found</div>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
            Auto-cleanup in {lastResult.cleanup_after_minutes} min
          </div>
        </div>
      )}

      {/* Uploads list */}
      {uploads.length > 0 && (
        <>
          <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-muted)", marginBottom: 4 }}>
            Your Uploads
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {uploads.map((u) => (
              <div
                key={u.upload_id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  fontSize: 11,
                  padding: "4px 8px",
                  background: "var(--bg-secondary)",
                  borderRadius: 4,
                }}
              >
                <div>
                  <div style={{ fontWeight: 500 }}>📦 {u.label || u.upload_id}</div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
                    {u.files_count} file(s) · {new Date(u.created_at).toLocaleString()}
                  </div>
                </div>
                <button
                  className="dvp-btn dvp-btn--ghost dvp-btn--xs"
                  onClick={() => handleDelete(u.upload_id)}
                  title="Delete upload"
                  style={{ fontSize: 10, color: "var(--error)" }}
                >
                  🗑
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Info */}
      <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 12, lineHeight: 1.5 }}>
        <strong>How it works:</strong>
        <ul style={{ margin: "4px 0", paddingLeft: 16 }}>
          <li>ZIP your test folder and upload it</li>
          <li>Uploaded tests appear in the Tests tree</li>
          <li>Run them like any other test</li>
          <li>Files are auto-cleaned after 10 minutes</li>
          <li>Only you can see your uploaded files</li>
        </ul>
      </div>
    </div>
  );
}
