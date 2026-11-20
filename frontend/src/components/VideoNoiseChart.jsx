/**
 * VideoNoiseChart
 * ===============
 * Visualises exactly what happens to CKKS noise while the video processes.
 *
 * Graph 1 — Noise level vs frame (line chart)
 *   Red line  = noise after all ops on that frame
 *   Amber dash = threshold (the value the user set)
 *   Orange dot = frame where bootstrap fired
 *
 * Graph 2 — Noise generated vs noise reduced per frame (bar chart)
 *   Blue bar  = noise units added by encrypt / add / scale on that frame
 *   Green bar = noise units removed by bootstrap (0 on non-bootstrap frames)
 *
 * Operations table — last 8 frames, every computation step listed
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Dot,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const C_NOISE     = "#ef4444";
const C_THRESHOLD = "#f59e0b";
const C_BOOT_DOT  = "#fb923c";
const C_GEN       = "#38bdf8";
const C_RED       = "#34d399";

function thin(arr, maxPts) {
  if (arr.length <= maxPts) return arr;
  const step = arr.length / maxPts;
  return Array.from({ length: maxPts }, (_, i) => arr[Math.round(i * step)]);
}

export default function VideoNoiseChart({ result, liveData = [] }) {
  const snapshots =
    result?.all_noise_snapshots?.length
      ? result.all_noise_snapshots
      : liveData;

  const hasData    = snapshots.length > 0;
  const lastSnap   = snapshots[snapshots.length - 1];
  const pctUsed    = lastSnap?.pct_used   ?? 0;
  const threshold  = lastSnap?.threshold  ?? result?.all_noise_snapshots?.[0]?.threshold ?? 50;
  const totalBoots = result?.total_bootstraps ?? lastSnap?.bootstraps ?? 0;

  const generated = result?.total_noise_generated
    ?? snapshots.reduce((s, x) => s + (x.noise_generated || 0), 0);
  const reduced = result?.total_noise_reduced
    ?? snapshots.reduce((s, x) => s + (x.noise_reduced || 0), 0);

  // Frame count label
  const framesLabel = (() => {
    const processed  = result?.frames_processed ?? snapshots.length;
    const srcTotal   = result?.info?.total_frames;
    const truncated  = result?.truncated;
    if (!hasData) return "Waiting for video…";
    if (truncated && srcTotal && processed < srcTotal)
      return `${processed} sampled of ${srcTotal} source frames · threshold ${threshold}`;
    return `${processed} frames · threshold ${threshold}`;
  })();

  // Shared chart dataset
  const chartData = thin(snapshots, 600).map((s) => ({
    frame:           s.frame_idx,
    noise:           s.noise,
    threshold:       s.threshold,
    pct_used:        s.pct_used,
    bootstrapped:    s.bootstrapped,
    bootstraps:      s.bootstraps,
    noise_generated: s.noise_generated || 0,
    noise_reduced:   s.noise_reduced   || 0,
    ops:             s.ops || [],
    frame_a:         s.frame_a,
    frame_b:         s.frame_b,
  }));

  const barColor =
    pctUsed > 85 ? "#ef4444" : pctUsed > 60 ? "#f59e0b" : "#34d399";

  const wrt =
    lastSnap?.frame_b != null
      ? `frames ${lastSnap.frame_b} and ${lastSnap.frame_a}`
      : lastSnap
        ? `frame ${lastSnap.frame_a ?? lastSnap.frame_idx}`
        : "—";

  const recent = snapshots.slice(-8).reverse();

  const commonAxis = {
    xAxis: (
      <XAxis
        dataKey="frame"
        tick={{ fill: "var(--text)", fontSize: 10 }}
        label={{ value: "Frame", position: "insideBottomRight", offset: -4, fill: "var(--text)", fontSize: 10 }}
      />
    ),
    grid: <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />,
  };

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>HE Computations &amp; Noise Control</h2>
        <span className="muted">{framesLabel}</span>
      </div>

      <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
        {result?.computation
          ?? `Per frame t: encrypt luma → add Enc(t-1)+Enc(t) → scale × 0.5. Bootstrap fires when noise > threshold.`}
      </p>

      {/* ── Summary stats grid ───────────────────────────────────── */}
      <div className="videoInfoGrid" style={{ marginBottom: 10 }}>
        <Stat label="Threshold (user set)"  value={threshold}  accent />
        <Stat label="Noise generated total" value={generated}  hint="CKKS units added by encrypt / add / scale / stream" />
        <Stat label="Bootstraps"            value={totalBoots} hint="Times the budget was reset" accent />
        <Stat label="Noise reduced total"   value={reduced}    hint="Units removed by bootstrap" />
        <Stat label="Peak noise"            value={result?.peak_noise ?? lastSnap?.noise ?? "—"} />
        <Stat label="Budget used now"       value={`${Number(pctUsed).toFixed(1)}%`} />
      </div>

      {/* ── Progress bar ─────────────────────────────────────────── */}
      <div className="noiseMetaRow">
        <span className="noiseBadge">Threshold&nbsp;<strong>{threshold}</strong></span>
        <div className="noiseBarWrap">
          <div
            className="noiseBar"
            style={{ width: `${Math.min(pctUsed, 100)}%`, background: barColor }}
          />
        </div>
        <span className="noisePct" style={{ color: barColor }}>
          {Number(pctUsed).toFixed(1)}%
        </span>
      </div>

      {/* ════════════════════════════════════════════════════════════
          GRAPH 1 — Noise level vs frame
      ════════════════════════════════════════════════════════════ */}
      <div className="chartSectionLabel">Noise level per frame</div>
      <div className="chart" style={{ height: 230 }}>
        {!hasData ? (
          <EmptyChart liveData={liveData} />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
              {commonAxis.grid}
              {commonAxis.xAxis}
              <YAxis
                tick={{ fill: "var(--text)", fontSize: 10 }}
                domain={[0, "auto"]}
                label={{ value: "HE noise units", angle: -90, position: "insideLeft", fill: "var(--text)", fontSize: 10 }}
              />
              <Tooltip content={<NoiseTooltip />} />
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
      <p className="muted" style={{ fontSize: 11, marginTop: 4, marginBottom: 14 }}>
        Red = CKKS noise after all operations on that frame.
        Dashed amber = bootstrap threshold ({threshold}).
        Orange dot = bootstrap fired (noise reset to baseline).
      </p>

      {/* ════════════════════════════════════════════════════════════
          GRAPH 2 — Noise generated vs reduced per frame
      ════════════════════════════════════════════════════════════ */}
      <div className="chartSectionLabel">Noise generated vs reduced per frame</div>
      <div className="chart" style={{ height: 230 }}>
        {!hasData ? (
          <EmptyChart liveData={liveData} />
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
              {commonAxis.grid}
              {commonAxis.xAxis}
              <YAxis
                tick={{ fill: "var(--text)", fontSize: 10 }}
                label={{ value: "Noise units", angle: -90, position: "insideLeft", fill: "var(--text)", fontSize: 10 }}
              />
              <Tooltip content={<BarTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: "var(--text)" }} />
              <Bar
                dataKey="noise_generated"
                name="Generated (encrypt+add+scale)"
                fill={C_GEN}
                isAnimationActive={false}
                maxBarSize={8}
              />
              <Bar
                dataKey="noise_reduced"
                name="Reduced (bootstrap)"
                fill={C_RED}
                isAnimationActive={false}
                maxBarSize={8}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
      <p className="muted" style={{ fontSize: 11, marginTop: 4, marginBottom: 14 }}>
        Blue = noise added by HE ops (encrypt + add + scale) on each frame.
        Green = noise removed when bootstrap fired.
        Green only appears on frames where noise exceeded threshold {threshold}.
      </p>

      {/* ── Operations table ─────────────────────────────────────── */}
      <div className="videoOpsBox">
        <div className="videoOpsTitle">
          Last computation · wrt {wrt}
          {lastSnap?.bootstrapped ? " · ⚡ bootstrap fired this frame" : ""}
        </div>
        {!hasData ? (
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>
            Process a video to see per-frame encrypt / add / scale / bootstrap steps.
          </p>
        ) : (
          <ul className="videoOpsList">
            {(lastSnap.ops?.length ? lastSnap.ops : ["encrypt + stream"]).map((op, i) => (
              <li key={i}>{op}</li>
            ))}
          </ul>
        )}
        {hasData && (
          <>
            <div className="videoOpsRecentHeader">Recent frames</div>
            <div className="videoOpsRecent">
              {recent.map((s) => (
                <div key={s.frame_idx} className="videoOpsRecentRow">
                  <span className="videoOpsFrame">f{s.frame_idx}</span>
                  <span className="videoOpsExpr">
                    {s.frame_b != null
                      ? `Enc(f${s.frame_b})+Enc(f${s.frame_a})×0.5`
                      : `Enc(f${s.frame_a ?? s.frame_idx})`}
                  </span>
                  <span style={{ color: C_GEN, fontFamily: "var(--mono)", fontSize: 11 }}>
                    +{s.noise_generated || 0}
                  </span>
                  {s.bootstrapped ? (
                    <span style={{ color: C_RED, fontFamily: "var(--mono)", fontSize: 11 }}>
                      ⚡ −{s.noise_reduced || 0}
                    </span>
                  ) : (
                    <span className="muted" style={{ fontSize: 11 }}>—</span>
                  )}
                  <span className="muted" style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                    noise={s.noise}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function EmptyChart({ liveData }) {
  return (
    <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <p className="muted" style={{ fontSize: 13 }}>
        {liveData.length === 0 ? "Process a video to see the graph." : "Processing…"}
      </p>
    </div>
  );
}

function Stat({ label, value, hint, accent = false }) {
  return (
    <div className="videoStat" title={hint ?? ""}>
      <span className="videoStatLabel">{label}</span>
      <span className={`videoStatValue${accent ? " videoStatValue--accent" : ""}`}>
        {value}
      </span>
    </div>
  );
}

function BootstrapDot(props) {
  const { cx, cy, payload } = props;
  if (!payload?.bootstrapped) return null;
  return (
    <Dot cx={cx} cy={cy} r={5} fill={C_BOOT_DOT} stroke="var(--bg)" strokeWidth={1.5} />
  );
}

function NoiseTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload ?? {};
  return (
    <div className="chartTooltip">
      <span><span className="tooltipLabel">Frame </span><span className="tooltipValue">{label}</span></span>
      {d.frame_b != null
        ? <span className="tooltipMono">Enc(f{d.frame_b}) + Enc(f{d.frame_a}) × 0.5</span>
        : <span className="tooltipMono">Enc(f{d.frame_a ?? label})</span>}
      {(d.ops || []).map((op, i) => (
        <span key={i} className="tooltipMono" style={{ color: "var(--text)" }}>{op}</span>
      ))}
      <span><span className="tooltipLabel">Noise </span>
        <span className="tooltipValue" style={{ color: C_NOISE }}>{d.noise}</span></span>
      <span><span className="tooltipLabel">Generated </span>
        <span className="tooltipValue" style={{ color: C_GEN }}>+{d.noise_generated}</span></span>
      <span><span className="tooltipLabel">Threshold </span>
        <span className="tooltipValue" style={{ color: C_THRESHOLD }}>{d.threshold}</span></span>
      {d.bootstrapped && (
        <span className="tooltipBoot">⚡ Bootstrap #{d.bootstraps} — noise reduced by {d.noise_reduced}</span>
      )}
    </div>
  );
}

function BarTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chartTooltip">
      <span><span className="tooltipLabel">Frame </span><span className="tooltipValue">{label}</span></span>
      {payload.map((p) => (
        <span key={p.dataKey}>
          <span className="tooltipLabel">{p.name.split("(")[0].trim()} </span>
          <span className="tooltipValue" style={{ color: p.fill }}>{p.value}</span>
        </span>
      ))}
    </div>
  );
}
