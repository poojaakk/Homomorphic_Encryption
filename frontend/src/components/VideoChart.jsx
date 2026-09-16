/**
 * VideoChart
 * ==========
 * Three-line Recharts comparison chart for video mode:
 *
 *   ─ Original    (raw mean grayscale intensity)
 *   ─ Noisy       (original + Gaussian noise)
 *   ─ HE-Smoothed (decrypted weighted moving average from CKKS)
 *
 * X-axis: frame number
 * Y-axis: mean grayscale intensity (0–255)
 *
 * Also renders a small plaintext reference line (dashed) so the user
 * can visually confirm the HE result matches the plaintext MA.
 *
 * Props
 * -----
 *  result – VideoProcessResponse object (null renders empty state)
 */

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// Colour palette (stays visible on the dark dashboard theme)
const C_ORIGINAL  = "#60a5fa";   // blue
const C_NOISY     = "#f87171";   // red
const C_HE        = "#34d399";   // emerald
const C_PLAINTEXT = "#fbbf24";   // amber (dashed reference)

export default function VideoChart({ result }) {
  if (!result) {
    return (
      <div className="card">
        <div className="cardHeader">
          <h2>Signal Comparison</h2>
          <span className="muted">Original · Noisy · HE-Smoothed</span>
        </div>
        <div
          className="chart"
          style={{ display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <p className="muted">Process a video to see the comparison chart.</p>
        </div>
      </div>
    );
  }

  const {
    all_frame_indices,
    all_original,
    all_noisy,
    all_he_smoothed,
    all_plaintext_smoothed,
  } = result;

  // Build recharts data array
  const data = all_frame_indices.map((fi, i) => ({
    frame: fi,
    original:  all_original[i]  ?? null,
    noisy:     all_noisy[i]     ?? null,
    he:        all_he_smoothed[i] ?? null,
    plaintext: all_plaintext_smoothed[i] ?? null,
  }));

  // Thin the data to at most 300 points so the chart stays responsive
  const thinned = thin(data, 300);

  const n = all_frame_indices.length;

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Signal Comparison</h2>
        <span className="muted">{n} frames · mean grayscale intensity</span>
      </div>

      {/* ── Main comparison chart ─────────────────────────────────── */}
      <div className="chart" style={{ height: 280 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={thinned} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis
              dataKey="frame"
              tick={{ fill: "var(--text)", fontSize: 11 }}
              label={{ value: "Frame", position: "insideBottomRight", offset: -4,
                       fill: "var(--text)", fontSize: 11 }}
            />
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fill: "var(--text)", fontSize: 11 }}
              label={{ value: "Intensity", angle: -90, position: "insideLeft",
                       fill: "var(--text)", fontSize: 11 }}
            />
            <Tooltip content={<ChartTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 12, color: "var(--text)", paddingTop: 4 }}
            />

            <Line
              type="monotone"
              dataKey="original"
              name="Original"
              stroke={C_ORIGINAL}
              dot={false}
              strokeWidth={1.5}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="noisy"
              name="+ Gaussian noise (σ)"
              stroke={C_NOISY}
              dot={false}
              strokeWidth={1}
              strokeOpacity={0.7}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="he"
              name="HE-Smoothed"
              stroke={C_HE}
              dot={false}
              strokeWidth={2}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="plaintext"
              name="Plaintext MA (ref)"
              stroke={C_PLAINTEXT}
              dot={false}
              strokeWidth={1}
              strokeDasharray="4 3"
              strokeOpacity={0.6}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* ── Legend note ───────────────────────────────────────────── */}
      <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
        Y-axis = mean pixel brightness (0–255). <strong>Left chart only — unrelated to the HE noise counter on the right.</strong>{" "}
        HE-Smoothed = CKKS weighted moving average (window 5 × 0.2).
        Dashed amber = plaintext reference (validation).
        {result.overall_mae_he_vs_plain !== undefined && (
          <>
            {" "}MAE(HE vs PT):{" "}
            <span style={{ fontFamily: "var(--mono)", color: "var(--text-h)" }}>
              {result.overall_mae_he_vs_plain.toFixed(5)}
            </span>
          </>
        )}
      </p>
    </div>
  );
}

// ── Custom tooltip ─────────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chartTooltip">
      <span className="tooltipLabel">Frame <span className="tooltipValue">{label}</span></span>
      {payload.map((p) => (
        <span key={p.name} style={{ color: p.stroke ?? p.color, fontSize: 12 }}>
          {p.name}:{" "}
          <span className="tooltipValue">
            {p.value != null ? p.value.toFixed(3) : "—"}
          </span>
        </span>
      ))}
    </div>
  );
}

// ── Utility: thin an array to at most maxPts by evenly sampling ────────────
function thin(arr, maxPts) {
  if (arr.length <= maxPts) return arr;
  const step = arr.length / maxPts;
  return Array.from({ length: maxPts }, (_, i) => arr[Math.round(i * step)]);
}
