import { useState, useMemo } from "react";
import type { TestSuite } from "../types";

interface TestSuitesPanelProps {
  testSuites: TestSuite[];
  selectedSuiteIds: string[];
  onToggleSuite: (suite: TestSuite) => void;
  onCreateSuite: (name: string, description: string, tests: string[], tags: string[]) => Promise<boolean>;
  onDeleteSuite: (suiteId: string) => Promise<boolean>;
  selectedTests: string[];
}

const SOURCE_ICON: Record<string, string> = {
  auto: "📁",
  marker: "🏷️",
  custom: "✏️",
};

const STATUS_DOT: Record<string, string> = {
  completed: "🟢",
  failed: "🔴",
  running: "🟡",
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const min = Math.floor(seconds / 60);
  const sec = Math.round(seconds % 60);
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
}

export function TestSuitesPanel({
  testSuites,
  selectedSuiteIds,
  onToggleSuite,
  onCreateSuite,
  onDeleteSuite,
  selectedTests,
}: TestSuitesPanelProps) {
  const [tagFilter, setTagFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newTags, setNewTags] = useState("");

  // Collect all unique tags for filtering
  const allTags = useMemo(() => {
    const tags = new Set<string>();
    testSuites.forEach((s) => s.tags.forEach((t) => tags.add(t)));
    return [...tags].sort();
  }, [testSuites]);

  // Filter suites by tag and source
  const filteredSuites = useMemo(() => {
    return testSuites.filter((suite) => {
      if (sourceFilter !== "all" && suite.source !== sourceFilter) return false;
      if (tagFilter && !suite.tags.some((t) => t.toLowerCase().includes(tagFilter.toLowerCase()))) return false;
      return true;
    });
  }, [testSuites, tagFilter, sourceFilter]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    const tags = newTags.split(",").map((t) => t.trim()).filter(Boolean);
    const ok = await onCreateSuite(newName.trim(), newDesc.trim(), selectedTests, tags);
    if (ok) {
      setNewName("");
      setNewDesc("");
      setNewTags("");
      setShowCreateForm(false);
    }
  };

  return (
    <div className="dvp-test-explorer">
      <div className="dvp-test-explorer__header">
        <div className="dvp-sidebar__section-title" style={{ marginBottom: 0, flex: 1 }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
          Test Suites
        </div>
        <span className="dvp-test-counter">{filteredSuites.length}</span>
      </div>

      {/* ── Filters ── */}
      <div className="dvp-suite-filters">
        <div className="dvp-suite-filters__row">
          <select
            className="dvp-filter-select dvp-suite-source-filter"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value)}
          >
            <option value="all">All Sources</option>
            <option value="auto">📁 Auto</option>
            <option value="marker">🏷️ Marker</option>
            <option value="custom">✏️ Custom</option>
          </select>
          <input
            type="text"
            className="dvp-filter-input"
            placeholder="Filter by tag..."
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            style={{ flex: 1 }}
          />
        </div>
        {allTags.length > 0 && (
          <div className="dvp-suite-tag-cloud">
            {allTags.slice(0, 12).map((tag) => (
              <span
                key={tag}
                className={`dvp-suite-tag dvp-suite-tag--clickable ${tagFilter === tag ? "dvp-suite-tag--active" : ""}`}
                onClick={() => setTagFilter(tagFilter === tag ? "" : tag)}
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* ── Create Suite Button ── */}
      <div style={{ padding: "0 8px 6px" }}>
        <button
          className="dvp-btn dvp-btn--ghost dvp-btn--xs"
          style={{ width: "100%" }}
          onClick={() => setShowCreateForm((v) => !v)}
        >
          {showCreateForm ? "Cancel" : "+ Create Custom Suite"}
        </button>
      </div>

      {/* ── Create Form ── */}
      {showCreateForm && (
        <div className="dvp-suite-create-form">
          <input
            className="dvp-filter-input"
            placeholder="Suite name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <input
            className="dvp-filter-input"
            placeholder="Description (optional)"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
          />
          <input
            className="dvp-filter-input"
            placeholder="Tags (comma-separated)"
            value={newTags}
            onChange={(e) => setNewTags(e.target.value)}
          />
          <div className="dvp-suite-create-form__info">
            Will include {selectedTests.length} currently selected test(s)
          </div>
          <button
            className="dvp-btn dvp-btn--primary dvp-btn--xs"
            disabled={!newName.trim() || selectedTests.length === 0}
            onClick={handleCreate}
          >
            Create Suite
          </button>
        </div>
      )}

      {/* ── Suite Cards ── */}
      <div className="dvp-suite-list">
        {filteredSuites.length === 0 ? (
          <div className="dvp-empty-state">
            <div className="dvp-empty-state__icon">📦</div>
            <div className="dvp-empty-state__text">
              {testSuites.length === 0 ? "No suites available" : "No suites match filters"}
            </div>
            <div className="dvp-empty-state__sub">
              Test suites are auto-generated from directory structure, markers, and user-created
            </div>
          </div>
        ) : (
          filteredSuites.map((suite) => {
            const isSelected = selectedSuiteIds.includes(suite.id);
            return (
              <div
                key={suite.id}
                className={`dvp-suite-card ${isSelected ? "dvp-suite-card--selected" : ""}`}
                onClick={() => onToggleSuite(suite)}
              >
                <div className="dvp-suite-card__header">
                  <span className="dvp-suite-card__name">
                    {isSelected ? "☑" : "☐"} {SOURCE_ICON[suite.source] || "📁"} {suite.name}
                  </span>
                  <span className="dvp-suite-card__count">{suite.tests.length} tests</span>
                </div>
                <div className="dvp-suite-card__desc">{suite.description}</div>
                <div className="dvp-suite-card__meta">
                  <div className="dvp-suite-card__tags">
                    {suite.tags.map((tag) => (
                      <span key={tag} className="dvp-suite-tag">{tag}</span>
                    ))}
                  </div>
                  <div className="dvp-suite-card__stats">
                    {suite.estimated_duration != null && (
                      <span className="dvp-suite-stat" title="Estimated duration (avg of recent runs)">
                        ⏱ {formatDuration(suite.estimated_duration)}
                      </span>
                    )}
                    {suite.last_run && (
                      <span className="dvp-suite-stat" title={`Last: ${suite.last_run.run_name || '#' + suite.last_run.run_id}`}>
                        {STATUS_DOT[suite.last_run.status] || "⚪"} {suite.last_run.run_name || '#' + suite.last_run.run_id}
                      </span>
                    )}
                  </div>
                </div>
                {suite.source === "custom" && (
                  <button
                    className="dvp-btn dvp-btn--ghost dvp-btn--xs dvp-suite-delete"
                    onClick={(e) => { e.stopPropagation(); onDeleteSuite(suite.id); }}
                    title="Delete custom suite"
                  >
                    🗑
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* ── Selection summary ── */}
      {selectedSuiteIds.length > 0 && (
        <div className="dvp-suite-selection-summary">
          {selectedSuiteIds.length} suite(s) selected · {selectedTests.length} test(s) total
        </div>
      )}
    </div>
  );
}
