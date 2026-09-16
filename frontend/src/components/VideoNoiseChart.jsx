/**
 * VideoNoiseChart
 * ===============
 * Noise budget chart for video streaming mode.
 *
 * Shows — per video frame — how the simulated CKKS noise counter grows
 * during homomorphic operations and drops back to a safe baseline each
 * time the adaptive bootstrap threshold is crossed.
 *
 * Data sources (two complementary feeds)
 * ----------------------------------------
 * 1. liveData   – real-time array of {frame_idx, noise, threshold, pct_used,
 *                  bootstrapped} pushed frame-by-frame via WebSocket while the
 *                  pipeline is running.  Gives instant visual feedback.
 * 2. result     – the complete VideoProcessResponse after processing finishes.
 *                  Its all_noise_snapshots field replaces liveData so the
 *                  chart shows the full, authoritative record.
 *
 * Visual encoding
 * ---------------
 *  Red line        – noise counter value
 *  Dashed amber    – adaptive threshold (can move up/down between frames)
 *  Orange dot      – bootstrap fired at this frame (noise reset to baseline)
 *  Progress bar    – current noise % of threshold  (green / amber / red)
 *
 * Props
 * -----
 *  result    – VideoProcessResponse | null  (null = show live data only)
 *  liveData  – array of frame snapshots arriving via WS  ([] if none yet)
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
  Dot,
} from "recharts";

const C_NOISE     = "#ef4444";   // red
const C_THRESHOLD = "#f59e0b";   // amber
const C_BOOT_DOT  = "#fb923c";   // orange

export default function VideoNoiseChart({ result, liveData = [] }) {
  // Prefer the authoritative result snapshots over live WS data once done
  const snapshots =
    result?.all_noise_snapshots?.length
      ? result.all_noise_snapshots
      : liveData;

  const hasData    = snapshots.length > 0;
  const lastSnap   = snapshots[snapshots.length - 1];
  const pctUsed    = lastSnap?.pct_used   ?? 0;
  const threshold  = lastSnap?.threshold  ?? "—";
  const totalBoots = result?.total_bootstraps
    ?? lastSnap?.bootstraps
    ?? 0;

  // Recharts data – thin to ≤ 300 points for performance
  const chartData = thin(snapshots, 300).map((s) => ({
    frame:       s.frame_idx,
    noise:       s.noise,
    threshold:   s.threshold,
    pct_used:    s.pct_used,
    bootstrapped: s.bootstrapped,
    bootstraps:  s.bootstraps,
  }));

  // Progress bar colour
  const barColor =
    pctUsed > 85 ? "#ef4444" : pctUsed > 60 ? "#f59e0b" : "#34d399";

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>HE Noise Budget</h2>
        <span className="muted">
          {hasData
            ? `${snapshots.length} frames · ${totalBoots} bootstrap${totalBoots !== 1 ? "s" : ""}`
            : "Waiting for video…"}
        </span>
      </div>

      {/* ── Progress bar ─────────────────────────────────────────── */}
      <div className="noiseMetaRow">
        <span className="noiseBadge">
          Threshold&nbsp;<strong>{threshold}</strong>
        </span>
        <div className="noiseBarWrap">
          <div
            className="noiseBar"
            style={{ width: `${Math.min(pctUsed, 100)}%`, background: barColor }}
          />
        </div>
        <span className="noisePct" style={{ color: barColor }}>
          {pctUsed.toFixed(1)}%
        </span>
        <span className="noiseBadge" style={{ marginLeft: 6 }}>
          🔄&nbsp;{totalBoots}
        </span>
      </div>

      {/* ── Chart ────────────────────────────────────────────────── */}
      <div className="chart" style={{ height: 220 }}>
        {!hasData ? (
          <div
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <p className="muted" style={{ fontSize: 13 }}>
              {liveData.length === 0
                ? "Process a video to see the noise budget chart."
                : "Processing…"}
            </p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={chartData}
              margin={{ top: 4, right: 16, bottom: 4, left: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis
                dataKey="frame"
                tick={{ fill: "var(--text)", fontSize: 11 }}
                label={{
                  value: "Frame",
                  position: "insideBottomRight",
                  offset: -4,
                  fill: "var(--text)",
                  fontSize: 11,
                }}
              />
              <YAxis
                tick={{ fill: "var(--text)", fontSize: 11 }}
                domain={[0, "auto"]}
                label={{
                  value: "HE noise units",
                  angle: -90,
                  position: "insideLeft",
                  fill: "var(--text)",
                  fontSize: 11,
                }}
              />
              <Tooltip content={<NoiseTooltip />} />

              {/* Dynamic threshold line — drawn per data point as a line */}
              <Line
                type="stepAfter"
                dataKey="threshold"
                name="Threshold"
                stroke={C_THRESHOLD}
                strokeWidth={1.5}
                strokeDasharray="5 3"
                dot={false}
                isAnimationActive={false}
              />

              {/* Noise counter */}
              <Line
                type="monotone"
                dataKey="noise"
                name="Noise"
                stroke={C_NOISE}
                strokeWidth={2}
                dot={<BootstrapDot />}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* ── Legend note ───────────────────────────────────────────── */}
      <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
        <strong>This is NOT pixel brightness.</strong> Y-axis = CKKS encryption noise
        counter — goes up ~23 units per frame from HE operations (encrypt + scalar
        multiply × 5 + HE addition × 4), resets to 20 when bootstrap fires.{" "}
        <span style={{ color: C_BOOT_DOT }}>●</span> = bootstrap. Threshold range 200–500.
      </p>
    </div>
  );
}

// ── Custom dot: orange circle only on bootstrap frames ────────────────────
function BootstrapDot(props) {
  const { cx, cy, payload } = props;
  if (!payload?.bootstrapped) return null;
  return (
    <Dot
      cx={cx}
      cy={cy}
      r={5}
      fill={C_BOOT_DOT}
      stroke="var(--bg)"
      strokeWidth={1.5}
    />
  );
}

// ── Custom tooltip ────────────────────────────────────────────────────────
function NoiseTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload ?? {};
  return (
    <div className="chartTooltip">
      <span className="tooltipLabel">
        Frame <span className="tooltipValue">{label}</span>
      </span>
      <span>
        <span className="tooltipLabel">Noise </span>
        <span className="tooltipValue" style={{ color: C_NOISE }}>
          {d.noise}
        </span>
      </span>
      <span>
        <span className="tooltipLabel">Threshold </span>
        <span className="tooltipValue" style={{ color: C_THRESHOLD }}>
          {d.threshold}
        </span>
      </span>
      <span>
        <span className="tooltipLabel">Used </span>
        <span className="tooltipValue">{d.pct_used?.toFixed(1)}%</span>
      </span>
      {d.bootstrapped && (
        <span className="tooltipBoot">
          🔄 Bootstrap #{d.bootstraps} — noise reset
        </span>
      )}
    </div>
  );
}

// ── Utility: thin array to maxPts by even sampling ────────────────────────
function thin(arr, maxPts) {
  if (arr.length <= maxPts) return arr;
  const step = arr.length / maxPts;
  return Array.from({ length: maxPts }, (_, i) => arr[Math.round(i * step)]);
}
