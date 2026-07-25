// EquityCurve — SVG line chart for backtest equity growth
export default function EquityCurve({ equityCurve }) {
  if (!equityCurve || equityCurve.length === 0) return null;

  const dataPoints = equityCurve.map((pt) => pt.balance);
  const minVal  = Math.min(...dataPoints);
  const maxVal  = Math.max(...dataPoints);
  const range   = maxVal - minVal || 1;
  const W = 500, H = 180, P = 20;

  const points = dataPoints
    .map((val, idx) => {
      const x = P + (idx / (dataPoints.length - 1)) * (W - 2 * P);
      const y = H - P - ((val - minVal) / range) * (H - 2 * P);
      return `${x},${y}`;
    })
    .join(' ');

  const fillPts = `${P},${H - P} ${points} ${W - P},${H - P}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto">
      <defs>
        <linearGradient id="gradient-equity" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#3b82f6" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.0" />
        </linearGradient>
      </defs>
      {/* Grid lines */}
      {[P, H / 2, H - P].map((y) => (
        <line key={y} x1={P} y1={y} x2={W - P} y2={y} stroke="rgba(255,255,255,0.05)" />
      ))}
      {/* Area fill */}
      <polygon points={fillPts} fill="url(#gradient-equity)" />
      {/* Line */}
      <polyline
        points={points}
        fill="none"
        stroke="#3b82f6"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
