interface DonutChartProps {
  total: number;
  passed: number;
  failed: number;
  errors: number;
  running: number;
  notStarted: number;
  cancelled: number;
}

export default function DonutChart({ total, passed, failed, errors, running, notStarted, cancelled }: DonutChartProps) {
  if (total === 0) return null;

  const size = 100;
  const strokeWidth = 14;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  const segments = [
    { value: passed, color: "var(--green)", label: "Passed" },
    { value: failed, color: "var(--red)", label: "Failed" },
    { value: errors, color: "var(--orange)", label: "Errors" },
    { value: running, color: "var(--blue)", label: "Running" },
    { value: notStarted, color: "var(--text-muted)", label: "Pending" },
    { value: cancelled, color: "var(--yellow)", label: "Cancelled" },
  ].filter((s) => s.value > 0);

  let offset = 0;
  const passRate = total > 0 ? Math.round((passed / total) * 100) : 0;

  return (
    <div className="dvp-donut-wrapper">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {segments.map((seg, i) => {
          const pct = seg.value / total;
          const dashLength = pct * circumference;
          const dashOffset = -offset;
          offset += dashLength;
          return (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={seg.color}
              strokeWidth={strokeWidth}
              strokeDasharray={`${dashLength} ${circumference - dashLength}`}
              strokeDashoffset={dashOffset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
              style={{ transition: "stroke-dasharray 0.5s ease" }}
            />
          );
        })}
        <text
          x={size / 2}
          y={size / 2}
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--text-primary)"
          fontSize="18"
          fontWeight="800"
          fontFamily="var(--font-mono)"
        >
          {passRate}%
        </text>
      </svg>
      <div className="dvp-donut-legend">
        {segments.map((seg, i) => (
          <div key={i} className="dvp-donut-legend__item">
            <span className="dvp-donut-legend__dot" style={{ background: seg.color }} />
            <span>{seg.label}</span>
            <span className="dvp-donut-legend__value">{seg.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
