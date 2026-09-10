/**
 * NoiseChart
 * ==========
 * Renders the live noise-budget line with:
 *  - A red reference line at the current adaptive threshold
 *  - Bootstrap-event markers (orange dots) on the noise line
 *  - A noise-rate badge and percentage-used progress bar
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// Custom dot: renders a larger orange circle on bootstrap events.
function BootstrapDot(props) {
  const { cx, cy, payload } = props;
  if (!payload?.refreshed) return null;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={6}
      fill="#f59e0b"
      stroke="#fff"
      strokeWidth={2}
    />
  );
}

// Tooltip showing noise, threshold and bootstrap info.
function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chartTooltip">
      <div>
        <span className="tooltipLabel">Noise</span>
        <span className="tooltipValue">{d.noise}</span>
      </div>
      <div>
        <span className="tooltipLabel">Threshold</span>
        <span className="tooltipValue">{d.threshold ?? "—"}</span>
      </div>
      {d.refreshed && (
        <div className="tooltipBoot">
          ⚡ Bootstrap {d.refresh_before} → {d.refresh_after}
        </div>
      )}
    </div>
  );
}

export default function NoiseChart({ data }) {
  const latest = data?.[data.length - 1];
  const bootstraps = latest?.bootstraps ?? 0;
  const threshold = latest?.threshold ?? 50;
  const pctUsed = latest?.pct_used ?? 0;
  const noiseRate = latest?.noise_rate ?? 0;

  // Colour the progress bar: green < 60%, yellow < 85%, red otherwise.
  const barColor =
    pctUsed < 60 ? "#22c55e" : pctUsed < 85 ? "#f59e0b" : "#ef4444";

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Noise budget</h2>
        <span className="muted">
          adaptive threshold · {bootstraps} bootstrap{bootstraps !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Rate + progress bar */}
      <div className="noiseMetaRow">
        <span className="noiseBadge">
          Rate&nbsp;<strong>{noiseRate}/s</strong>
        </span>
        <div className="noiseBarWrap" title={`${pctUsed}% of threshold used`}>
          <div
            className="noiseBar"
            style={{ width: `${Math.min(pctUsed, 100)}%`, background: barColor }}
          />
        </div>
        <span className="noisePct" style={{ color: barColor }}>
          {pctUsed}%
        </span>
      </div>

      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="t" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} />

            {/* Adaptive threshold reference line */}
            <ReferenceLine
              y={threshold}
              stroke="#f59e0b"
              strokeDasharray="6 3"
              label={{
                value: `Threshold ${threshold}`,
                position: "insideTopRight",
                fontSize: 11,
                fill: "#f59e0b",
              }}
            />

            {/* Noise line with bootstrap markers */}
            <Line
              dataKey="noise"
              stroke="#ef4444"
              dot={<BootstrapDot />}
              activeDot={{ r: 4 }}
              strokeWidth={2}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
