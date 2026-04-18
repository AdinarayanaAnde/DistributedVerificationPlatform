interface MetricsPanelProps {
  metrics: any;
}

export function MetricsPanel({ metrics }: MetricsPanelProps) {
  if (!metrics) return null;

  return (
    <>
      <div className="dvp-summary__section-title">📊 Metrics Overview</div>
      <div className="dvp-metrics-grid">
        <div className="dvp-metric-card">
          <div className="dvp-metric-card__icon">🎯</div>
          <div className="dvp-metric-card__value dvp-metric-card__value--accent">
            {metrics.total_runs}
          </div>
          <div className="dvp-metric-card__label">Total Runs</div>
        </div>
        <div className="dvp-metric-card">
          <div className="dvp-metric-card__icon">✅</div>
          <div
            className={`dvp-metric-card__value ${
              metrics.success_rate >= 80
                ? "dvp-metric-card__value--green"
                : "dvp-metric-card__value--red"
            }`}
          >
            {metrics.success_rate}%
          </div>
          <div className="dvp-metric-card__label">Success Rate</div>
        </div>
        <div className="dvp-metric-card">
          <div className="dvp-metric-card__icon">🔄</div>
          <div className="dvp-metric-card__value dvp-metric-card__value--blue">
            {metrics.running_runs}
          </div>
          <div className="dvp-metric-card__label">Running</div>
        </div>
        <div className="dvp-metric-card">
          <div className="dvp-metric-card__icon">⏳</div>
          <div className="dvp-metric-card__value dvp-metric-card__value--yellow">
            {metrics.pending_runs}
          </div>
          <div className="dvp-metric-card__label">Pending</div>
        </div>
        <div className="dvp-metric-card">
          <div className="dvp-metric-card__icon">📅</div>
          <div className="dvp-metric-card__value">{metrics.recent_runs}</div>
          <div className="dvp-metric-card__label">Recent 24h</div>
        </div>
      </div>

      {metrics.client_stats?.length > 0 && (
        <>
          <div className="dvp-summary__section-title">👥 Client Activity</div>
          <div className="dvp-metrics-grid" style={{ marginBottom: 24 }}>
            {metrics.client_stats.map((stat: any) => (
              <div className="dvp-metric-card" key={stat.name}>
                <div className="dvp-metric-card__icon">👤</div>
                <div className="dvp-metric-card__value">{stat.runs}</div>
                <div className="dvp-metric-card__label">{stat.name}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {metrics.resource_stats?.length > 0 && (
        <>
          <div className="dvp-summary__section-title">🖥️ Resource Utilization</div>
          <div className="dvp-metrics-grid" style={{ marginBottom: 24 }}>
            {metrics.resource_stats.map((stat: any) => (
              <div className="dvp-metric-card" key={stat.name}>
                <div className="dvp-metric-card__icon">🔧</div>
                <div className="dvp-metric-card__value">{stat.runs}</div>
                <div className="dvp-metric-card__label">{stat.name}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
