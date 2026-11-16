/**
 * Video streaming: computations on which frames, CKKS noise generated,
 * bootstrap / noise reduced, and the noise-vs-frame graph — one panel.
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Dot,
} from "recharts";

const C_NOISE     = "#ef4444";
const C_THRESHOLD = "#f59e0b";
const C_BOOT_DOT  = "#fb923c";
const C_GEN       = "#38bdf8";
const C_RED       = "#34d399";

export default function VideoNoiseChart({ result, liveData = [] }) {
  const snapshots =
    result?.all_noise_snapshots?.length
      ? result.all_noise_snapshots
      : liveData;

  const hasData    = snapshots.length > 0;
  const lastSnap   = snapshots[snapshots.length - 1];
  const pctUsed    = lastSnap?.pct_used   ?? 0;
  const threshold  = lastSnap?.threshold  ?? result?.all_noise_snapshots?.[0]?.threshold ?? 50;
  const totalBoots = result?.total_bootstraps
    ?? lastSnap?.bootstraps
    ?? 0;
  const generated = result?.total_noise_generated
    ?? snapshots.reduce((s, x) => s + (x.noise_generated || 0), 0);
  const reduced = result?.total_noise_reduced
    ?? snapshots.reduce((s, x) => s + (x.noise_reduced || 0), 0);

  const chartData = thin(snapshots, 300).map((s) => ({
    frame:           s.frame_idx,
    noise:           s.noise,
    threshold:       s.threshold,
    pct_used:        s.pct_used,
    bootstrapped:    s.bootstrapped,
    bootstraps:      s.bootstraps,
    noise_generated: s.noise_generated || 0,
    noise_reduced:   s.noise_reduced || 0,
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

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Frame computations · CKKS noise</h2>
        <span className="muted">
          {hasData
            ? `${snapshots.length} frames · threshold ${threshold}`
            : "Waiting for video…"}
        </span>
      </div>

      <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
        {result?.computation
          ?? "Per frame t: encrypt luma of t; if t>0 add Enc(t-1)+Enc(t) and scale × 0.5. Bootstrap when noise exceeds 50."}
      </p>

      <div className="videoInfoGrid">
        <Stat label="Threshold" value={threshold} accent />
        <Stat label="Noise generated" value={generated} hint="CKKS units added by encrypt / add / scale / stream" />
        <Stat label="Bootstraps" value={totalBoots} hint="Times the budget was reset" accent />
        <Stat label="Noise reduced" value={reduced} hint="Units dropped by bootstrap" />
        <Stat label="Peak noise" value={result?.peak_noise ?? lastSnap?.noise ?? "—"} />
        <Stat label="Budget used" value={`${Number(pctUsed).toFixed(1)}%`} />
      </div>

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
          {Number(pctUsed).toFixed(1)}%
        </span>
      </div>

      <div className="videoOpsBox">
        <div className="videoOpsTitle">
          Computation now · wrt {wrt}
          {lastSnap?.bootstrapped ? " · bootstrap this frame" : ""}
        </div>
        {!hasData ? (
          <p className="muted" style={{ fontSize: 12, margin: 0 }}>
            Process a video to see encrypt / add / scale / bootstrap per frame.
          </p>
        ) : (
          <ul className="videoOpsList">
            {(lastSnap.ops?.length ? lastSnap.ops : ["encrypt + stream"]).map((op, i) => (
              <li key={i}>{op}</li>
            ))}
          </ul>
        )}
        {hasData && (
          <div className="videoOpsRecent">
            {recent.map((s) => (
              <div key={s.frame_idx} className="videoOpsRecentRow">
                <span className="videoOpsFrame">f{s.frame_idx}</span>
                <span>
                  {s.frame_b != null
                    ? `Enc(${s.frame_b})+Enc(${s.frame_a})×0.5`
                    : `Enc(${s.frame_a ?? s.frame_idx})`}
                </span>
                <span style={{ color: C_GEN }}>+{s.noise_generated || 0}</span>
                {s.bootstrapped ? (
                  <span style={{ color: C_RED }}>bootstrap −{s.noise_reduced || 0}</span>
                ) : (
                  <span className="muted">no bootstrap</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

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
                ? "Process a video to see the noise graph."
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

      <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
        Red = ciphertext noise after the ops on that frame. Dashed amber = threshold 50.
        Orange dots = bootstrap (noise reduced). Hover a point for generated / reduced
        and the exact encrypt/add/scale steps.
      </p>
    </div>
  );
}

function Stat({ label, value, hint }) {
  const accent = hint?.includes("reset") || label === "Threshold" || label === "Bootstraps";
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

function NoiseTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload ?? {};
  return (
    <div className="chartTooltip">
      <span className="tooltipLabel">
        Frame <span className="tooltipValue">{label}</span>
      </span>
      {d.frame_b != null ? (
        <span>
          wrt Enc({d.frame_b}) + Enc({d.frame_a}) × 0.5
        </span>
      ) : (
        <span>wrt Enc({d.frame_a ?? label})</span>
      )}
      {(d.ops || []).map((op, i) => (
        <span key={i} className="tooltipMono">{op}</span>
      ))}
      <span>
        <span className="tooltipLabel">Noise </span>
        <span className="tooltipValue" style={{ color: C_NOISE }}>{d.noise}</span>
      </span>
      <span>
        <span className="tooltipLabel">Generated </span>
        <span className="tooltipValue" style={{ color: C_GEN }}>+{d.noise_generated}</span>
      </span>
      <span>
        <span className="tooltipLabel">Reduced </span>
        <span className="tooltipValue" style={{ color: C_RED }}>−{d.noise_reduced}</span>
      </span>
      <span>
        <span className="tooltipLabel">Threshold </span>
        <span className="tooltipValue" style={{ color: C_THRESHOLD }}>{d.threshold}</span>
      </span>
      {d.bootstrapped && (
        <span className="tooltipBoot">
          Bootstrap #{d.bootstraps} — noise reduced
        </span>
      )}
    </div>
  );
}

function thin(arr, maxPts) {
  if (arr.length <= maxPts) return arr;
  const step = arr.length / maxPts;
  return Array.from({ length: maxPts }, (_, i) => arr[Math.round(i * step)]);
}
