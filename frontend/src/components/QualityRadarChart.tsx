type RadarMetric = {
  label: string;
  score: number | null;
};

const SIZE = 220;
const CENTER = SIZE / 2;
const RADIUS = 82;
const MAX_SCORE = 100;
const RING_COUNT = 4;

function pointAt(index: number, total: number, ratio: number) {
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
  return {
    x: CENTER + Math.cos(angle) * RADIUS * ratio,
    y: CENTER + Math.sin(angle) * RADIUS * ratio,
  };
}

function polygonPoints(values: number[]) {
  return values
    .map((value, index) => {
      const ratio = Math.max(0, Math.min(1, value / MAX_SCORE));
      const point = pointAt(index, values.length, ratio);
      return `${point.x},${point.y}`;
    })
    .join(' ');
}

function QualityRadarChart({ metrics }: { metrics: RadarMetric[] }) {
  const total = metrics.length;
  const values = metrics.map((metric) => metric.score ?? 0);
  const hasAnyScore = metrics.some((metric) => metric.score !== null);

  return (
    <div className="flex flex-col items-center">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label="四项指标质量雷达图">
        {Array.from({ length: RING_COUNT }, (_, ringIndex) => {
          const ratio = (ringIndex + 1) / RING_COUNT;
          return (
            <polygon
              key={ringIndex}
              points={polygonPoints(metrics.map(() => MAX_SCORE * ratio))}
              fill="none"
              stroke="#d9e1ea"
              strokeWidth={1}
            />
          );
        })}

        {metrics.map((_, index) => {
          const outer = pointAt(index, total, 1);
          return <line key={index} x1={CENTER} y1={CENTER} x2={outer.x} y2={outer.y} stroke="#d9e1ea" strokeWidth={1} />;
        })}

        {hasAnyScore ? (
          <polygon points={polygonPoints(values)} fill="rgba(47,128,237,0.25)" stroke="#2f80ed" strokeWidth={2} />
        ) : null}

        {metrics.map((metric, index) => {
          const ratio = Math.max(0, Math.min(1, (metric.score ?? 0) / MAX_SCORE));
          const point = pointAt(index, total, ratio);
          const labelPoint = pointAt(index, total, 1.22);
          const axisLabel = metric.label.length > 2 ? metric.label.slice(0, 2) : metric.label;
          return (
            <g key={metric.label}>
              {metric.score !== null ? <circle cx={point.x} cy={point.y} r={3.5} fill="#2f80ed" /> : null}
              <text
                x={labelPoint.x}
                y={labelPoint.y}
                fontSize={12}
                fontWeight={600}
                fill="#536476"
                textAnchor="middle"
                dominantBaseline="middle"
              >
                {axisLabel}
              </text>
            </g>
          );
        })}
      </svg>

      {!hasAnyScore ? <p className="mt-2 text-sm text-slate-500">暂无可绘制的指标数据</p> : null}
    </div>
  );
}

export default QualityRadarChart;
