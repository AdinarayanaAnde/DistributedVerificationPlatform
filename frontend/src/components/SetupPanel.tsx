import { useState, useEffect, useCallback } from "react";
import { api } from "../services/api";
import type { SetupConfiguration, SetupStep } from "../types";

interface SetupPanelProps {
  selectedConfigId: number | null;
  onSelectConfig: (id: number | null) => void;
}

interface SetupScript {
  name: string;
  filename: string;
  description: string;
}

const STEP_TYPES = [
  { value: "command", label: "Command", icon: "⌨️" },
  { value: "script", label: "Script", icon: "📜" },
  { value: "check", label: "Health Check", icon: "🔍" },
  { value: "env", label: "Environment", icon: "🌐" },
];

const FAILURE_ACTIONS = [
  { value: "fail", label: "Fail Run" },
  { value: "skip", label: "Skip Tests" },
  { value: "continue", label: "Continue" },
];

function EmptyStep(): SetupStep {
  return { name: "", step_type: "command", command: "", timeout: 300, on_failure: "fail" };
}

export function SetupPanel({ selectedConfigId, onSelectConfig }: SetupPanelProps) {
  const [configs, setConfigs] = useState<SetupConfiguration[]>([]);
  const [predefinedScripts, setPredefinedScripts] = useState<SetupScript[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [steps, setSteps] = useState<SetupStep[]>([EmptyStep()]);

  const loadConfigs = useCallback(async () => {
    try {
      const resp = await api.get<SetupConfiguration[]>("/setup-configurations");
      setConfigs(resp.data);
    } catch (e) {
      console.error("Failed to load setup configurations", e);
    }
  }, []);

  const loadScripts = useCallback(async () => {
    try {
      const resp = await api.get<SetupScript[]>("/setup-scripts");
      setPredefinedScripts(resp.data);
    } catch {
      /* server may not support this endpoint yet */
    }
  }, []);

  useEffect(() => {
    loadConfigs();
    loadScripts();
  }, [loadConfigs, loadScripts]);

  const useScriptAsTemplate = (script: SetupScript) => {
    setShowCreate(true);
    setEditId(null);
    setName(script.name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()));
    setDescription(script.description);
    setSteps([{
      name: script.name.replace(/_/g, " "),
      step_type: "script",
      command: `python setup_scripts/${script.filename}`,
      timeout: 300,
      on_failure: "fail",
    }]);
  };

  const updateStep = (idx: number, partial: Partial<SetupStep>) => {
    setSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, ...partial } : s)));
  };

  const removeStep = (idx: number) => {
    setSteps((prev) => prev.filter((_, i) => i !== idx));
  };

  const moveStep = (idx: number, dir: -1 | 1) => {
    setSteps((prev) => {
      const a = [...prev];
      const target = idx + dir;
      if (target < 0 || target >= a.length) return a;
      [a[idx], a[target]] = [a[target], a[idx]];
      return a;
    });
  };

  const resetForm = () => {
    setName("");
    setDescription("");
    setSteps([EmptyStep()]);
    setShowCreate(false);
    setEditId(null);
  };

  const handleSave = async () => {
    if (!name.trim() || steps.length === 0) return;
    const payload = {
      name: name.trim(),
      description: description.trim(),
      steps: steps.filter((s) => s.name.trim() && s.command.trim()),
    };
    try {
      if (editId) {
        await api.put(`/setup-configurations/${editId}`, payload);
      } else {
        await api.post("/setup-configurations", payload);
      }
      resetForm();
      await loadConfigs();
    } catch (e) {
      console.error("Failed to save setup configuration", e);
    }
  };

  const handleEdit = (config: SetupConfiguration) => {
    setEditId(config.id);
    setName(config.name);
    setDescription(config.description);
    setSteps(config.steps.length > 0 ? config.steps : [EmptyStep()]);
    setShowCreate(true);
  };

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/setup-configurations/${id}`);
      if (selectedConfigId === id) onSelectConfig(null);
      await loadConfigs();
    } catch (e) {
      console.error("Failed to delete setup configuration", e);
    }
  };

  return (
    <div className="dvp-test-explorer">
      <div className="dvp-test-explorer__header">
        <div className="dvp-sidebar__section-title" style={{ marginBottom: 0, flex: 1 }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z" />
          </svg>
          Environment Setup
        </div>
        <span className="dvp-test-counter">{configs.length}</span>
      </div>

      {/* ── Info banner ── */}
      <div className="dvp-setup-info">
        Configure pre-test setup steps for lab/environment preparation.
        Selected configuration runs before each test execution.
      </div>

      {/* ── Create/Edit button ── */}
      <div style={{ padding: "0 8px 6px" }}>
        <button
          className="dvp-btn dvp-btn--ghost dvp-btn--xs"
          style={{ width: "100%" }}
          onClick={() => { if (showCreate) resetForm(); else setShowCreate(true); }}
        >
          {showCreate ? "Cancel" : "+ New Configuration"}
        </button>
      </div>

      {/* ── Pre-defined Scripts (quick templates) ── */}
      {!showCreate && predefinedScripts.length > 0 && (
        <div style={{ padding: "0 8px 8px" }}>
          <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5, color: "var(--text-muted)", marginBottom: 4 }}>
            Quick Templates
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
            {predefinedScripts.map((script) => (
              <button
                key={script.filename}
                className="dvp-btn dvp-btn--ghost dvp-btn--xs"
                style={{ textAlign: "left", justifyContent: "flex-start", fontSize: 11, padding: "4px 8px" }}
                onClick={() => useScriptAsTemplate(script)}
                title={script.description || script.filename}
              >
                📜 {script.name.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Create/Edit Form ── */}
      {showCreate && (
        <div className="dvp-setup-form">
          <input
            className="dvp-filter-input"
            placeholder="Configuration name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="dvp-filter-input"
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <div className="dvp-setup-steps-header">
            <span className="dvp-setup-steps-label">Steps ({steps.length})</span>
            <button
              className="dvp-btn dvp-btn--ghost dvp-btn--xs"
              onClick={() => setSteps((p) => [...p, EmptyStep()])}
            >
              + Add Step
            </button>
          </div>
          {steps.map((step, idx) => (
            <div key={step.id ?? `new-${idx}`} className="dvp-setup-step-card">
              <div className="dvp-setup-step-row">
                <span className="dvp-setup-step-num">#{idx + 1}</span>
                <input
                  className="dvp-filter-input"
                  placeholder="Step name"
                  value={step.name}
                  onChange={(e) => updateStep(idx, { name: e.target.value })}
                  style={{ flex: 1 }}
                />
                <div className="dvp-setup-step-actions">
                  <button className="dvp-btn dvp-btn--ghost dvp-btn--xs" onClick={() => moveStep(idx, -1)} disabled={idx === 0}>↑</button>
                  <button className="dvp-btn dvp-btn--ghost dvp-btn--xs" onClick={() => moveStep(idx, 1)} disabled={idx === steps.length - 1}>↓</button>
                  <button className="dvp-btn dvp-btn--ghost dvp-btn--xs" onClick={() => removeStep(idx)} disabled={steps.length <= 1}>✕</button>
                </div>
              </div>
              <div className="dvp-setup-step-row">
                <select
                  className="dvp-filter-select"
                  value={step.step_type}
                  onChange={(e) => updateStep(idx, { step_type: e.target.value })}
                  style={{ width: "auto" }}
                >
                  {STEP_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.icon} {t.label}</option>
                  ))}
                </select>
                <select
                  className="dvp-filter-select"
                  value={step.on_failure}
                  onChange={(e) => updateStep(idx, { on_failure: e.target.value })}
                  style={{ width: "auto" }}
                >
                  {FAILURE_ACTIONS.map((a) => (
                    <option key={a.value} value={a.value}>On fail: {a.label}</option>
                  ))}
                </select>
                <input
                  className="dvp-filter-input"
                  type="number"
                  value={step.timeout}
                  onChange={(e) => updateStep(idx, { timeout: parseInt(e.target.value) || 300 })}
                  style={{ width: 60 }}
                  title="Timeout (seconds)"
                />
              </div>
              <textarea
                className="dvp-setup-command"
                placeholder={step.step_type === "env" ? "KEY=value (one per line)" : "Command or script..."}
                value={step.command}
                onChange={(e) => updateStep(idx, { command: e.target.value })}
                rows={2}
              />
            </div>
          ))}
          <button
            className="dvp-btn dvp-btn--primary dvp-btn--xs"
            disabled={!name.trim() || steps.every((s) => !s.name.trim() || !s.command.trim())}
            onClick={handleSave}
          >
            {editId ? "Update Configuration" : "Create Configuration"}
          </button>
        </div>
      )}

      {/* ── Config Cards ── */}
      <div className="dvp-suite-list">
        {configs.length === 0 && !showCreate ? (
          <div className="dvp-empty-state">
            <div className="dvp-empty-state__icon">🔧</div>
            <div className="dvp-empty-state__text">No configurations yet</div>
            <div className="dvp-empty-state__sub">
              Create setup configurations for lab/environment preparation before test runs
            </div>
          </div>
        ) : (
          configs.map((config) => (
            <div
              key={config.id}
              className={`dvp-suite-card ${selectedConfigId === config.id ? "dvp-suite-card--selected" : ""}`}
              onClick={() => onSelectConfig(selectedConfigId === config.id ? null : config.id)}
            >
              <div className="dvp-suite-card__header">
                <span className="dvp-suite-card__name">
                  {selectedConfigId === config.id ? "☑" : "☐"} 🔧 {config.name}
                </span>
                <span className="dvp-suite-card__count">{config.steps.length} steps</span>
              </div>
              {config.description && (
                <div className="dvp-suite-card__desc">{config.description}</div>
              )}
              <div className="dvp-setup-step-list">
                {config.steps.map((step, i) => (
                  <div key={step.id || i} className="dvp-setup-step-mini">
                    <span className="dvp-setup-step-mini__num">{i + 1}.</span>
                    <span className="dvp-setup-step-mini__icon">
                      {STEP_TYPES.find((t) => t.value === step.step_type)?.icon || "⌨️"}
                    </span>
                    <span className="dvp-setup-step-mini__name">{step.name}</span>
                    {step.on_failure !== "fail" && (
                      <span className="dvp-setup-step-mini__policy">({step.on_failure})</span>
                    )}
                  </div>
                ))}
              </div>
              <div className="dvp-setup-card-actions">
                <button
                  className="dvp-btn dvp-btn--ghost dvp-btn--xs"
                  onClick={(e) => { e.stopPropagation(); handleEdit(config); }}
                >
                  Edit
                </button>
                <button
                  className="dvp-btn dvp-btn--ghost dvp-btn--xs"
                  onClick={(e) => { e.stopPropagation(); handleDelete(config.id); }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {selectedConfigId && (
        <div className="dvp-suite-selection-summary">
          ✅ Setup configuration active — will run before tests
        </div>
      )}
    </div>
  );
}
