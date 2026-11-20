/**
 * FrameGraphs
 * ===========
 * Four interactive recharts graphs built from real extracted frame stats:
 *
 *  Graph 1 — Average Intensity vs Frame Number
 *  Graph 2 — Min & Max Pixel Intensity vs Frame Number
 *  Graph 3 — Standard Deviation vs Frame Number
 *  Graph 4 — Pixel Distribution histogram for the selected frame
 *            (histogram data fetched from GET /frames/histogram on demand)
 *
 * Props
 * -----
 *   stats        – array of FrameStatModel objects (from FrameAnalysisResponse)
 *   selectedFrame – currently selected frame index (synced with FrameViewer)
 *   onSelectFrame(idx) – called when user clicks a point on graphs 1–3
 */

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getFrameHistogram } from "../api";

const C_AVG   = "#38bdf8";
const C_MIN   = "#34d399";
const C_MAX   = "#ef4444";
const C_STD   = "#a78bfa";
const C_HIST  = "#f59e0b";
const C_SEL   = "#fb923c";

/** Down-sample to at most maxPts for chart rendering performance */
function thin(arr, maxPts = 600) {
  if (arr.length <= maxPts) return arr;
  const step = arr.length / maxPts;
  return Array.from({ length: maxPts }, (_, i) => arr[Math.round(i * step)]);
}

function SelectedDot(props) {
  const { cx, cy, payload, selectedFrame } = props;
  if (payload?.frame_idx !== selectedFrame) return null;
  return (
    <circle
      cx={cx} cy={cy} r={6}
      fill={C_SEL} stroke="var(--bg)" strokeWidth={2}
    />
  );
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="card faChartCard">
      <div className="cardHeader" style={{ marginBottom: 8 }}>
        <h2 style={{ fontSize: 15 }}>{title}</h2>
        {subtitle && <span className="muted">{subtitle}</span>}
      </div>
      {children}
    </div>
  );
}

export default function FrameGraphs({ stats = [], selectedFrame = 0, onSelectFrame }) {
  const [histogram, setHistogram]   = useState([]);
  const [histLoading, setHistLoading] = useState(false);

  // Fetch histogram whenever selectedFrame changes
  useEffect(() => {
    if (stats.length === 0) return;
    setHistLoading(true);
    getFrameHistogram(selectedFrame, 32)
      .then((res) => setHistogram(res.data.buckets))
      .catch(() => setHistogram([]))
      .finally(() => setHistLoading(false));
  }, [selectedFrame, stats.length]);

  if (stats.length === 0) {
    return (
      <div className="card">
        <div className="cardHeader">
          <h2>Frame Statistics Graphs</h2>
          <span className="muted">Extract a video to see the graphs</span>
        </div>
        <p className="muted" style={{ padding: "16px 0", textAlign: "center" }}>
          Upload and extract a video in the Frame Extraction panel above.
        </p>
      </div>
    );
  }

  const chartData = thin(stats).map((s) => ({
    frame_idx:     s.frame_idx,
    avg_intensity: s.avg_intensity,
    min_intensity: s.min_intensity,
    max_intensity: s.max_intensity,
    std_intensity: s.std_intensity,
  }));

  const handleClick = (data) => {
    if (data?.activePayload?.[0]?.payload?.frame_idx != null) {
      onSelectFrame?.(data.activePayload[0].payload.frame_idx);
    }
  };

  const commonXAxis = (
    <XAxis
      dataKey="frame_idx"
      tick={{ fill: "var(--text)", fontSize: 10 }}
      label={{ value: "Frame", position: "insideBottomRight", offset: -4, fill: "var(--text)", fontSize: 11 }}
    />
  );

  const commonGrid = <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />;

  return (
    <div className="faGraphsGrid">

      {/* ── Graph 1: Average Intensity ─────────────────────────── */}
      <ChartCard
        title="Average Grayscale Intensity"
        subtitle={`${stats.length} frames`}
      >
        <div className="chart" style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} onClick={handleClick}
              margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
              {commonGrid}
              {commonXAxis}
              <YAxis domain={[0, 255]} tick={{ fill: "var(--text)", fontSize: 10 }}
                label={{ value: "Intensity (0–255)", angle: -90, position: "insideLeft", fill: "var(--text)", fontSize: 10 }} />
              <Tooltip content={<IntensityTooltip label="Avg" color={C_AVG} />} />
              <Line type="monotone" dataKey="avg_intensity" name="Avg Intensity"
                stroke={C_AVG} strokeWidth={1.5} dot={<SelectedDot selectedFrame={selectedFrame} />}
                activeDot={{ r: 4 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>

      {/* ── Graph 2: Min & Max Intensity ───────────────────────── */}
      <ChartCard
        title="Min & Max Pixel Intensity"
        subtitle="per frame"
      >
        <div className="chart" style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} onClick={handleClick}
              margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
              {commonGrid}
              {commonXAxis}
              <YAxis domain={[0, 255]} tick={{ fill: "var(--text)", fontSize: 10 }}
                label={{ value: "Intensity (0–255)", angle: -90, position: "insideLeft", fill: "var(--text)", fontSize: 10 }} />
              <Tooltip content={<MinMaxTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: "var(--text)" }} />
              <Line type="monotone" dataKey="min_intensity" name="Min"
                stroke={C_MIN} strokeWidth={1.5} dot={false}
                isAnimationActive={false} />
              <Line type="monotone" dataKey="max_intensity" name="Max"
                stroke={C_MAX} strokeWidth={1.5} dot={false}
                isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>

      {/* ── Graph 3: Standard Deviation ────────────────────────── */}
      <ChartCard
        title="Standard Deviation of Pixel Intensity"
        subtitle="variation across frames"
      >
        <div className="chart" style={{ height: 220 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} onClick={handleClick}
              margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
              {commonGrid}
              {commonXAxis}
              <YAxis tick={{ fill: "var(--text)", fontSize: 10 }}
                label={{ value: "Std Dev", angle: -90, position: "insideLeft", fill: "var(--text)", fontSize: 10 }} />
              <Tooltip content={<IntensityTooltip label="Std Dev" color={C_STD} dataKey="std_intensity" />} />
              <Line type="monotone" dataKey="std_intensity" name="Std Dev"
                stroke={C_STD} strokeWidth={1.5} dot={<SelectedDot selectedFrame={selectedFrame} />}
                activeDot={{ r: 4 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </ChartCard>

      {/* ── Graph 4: Pixel Distribution histogram ──────────────── */}
      <ChartCard
        title="Pixel Intensity Distribution"
        subtitle={histLoading ? "Loading…" : `Frame ${selectedFrame} · click any point above to change`}
      >
        <div className="chart" style={{ height: 220 }}>
          {histLoading ? (
            <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span className="spinner" /><span className="muted" style={{ marginLeft: 8 }}>Loading histogram…</span>
            </div>
          ) : histogram.length === 0 ? (
            <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <p className="muted">No histogram data</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={histogram}
                margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                {commonGrid}
                <XAxis dataKey="intensity" tick={{ fill: "var(--text)", fontSize: 10 }}
                  label={{ value: "Grayscale Value (0–255)", position: "insideBottomRight", offset: -4, fill: "var(--text)", fontSize: 11 }} />
                <YAxis tick={{ fill: "var(--text)", fontSize: 10 }}
                  label={{ value: "Pixel Count", angle: -90, position: "insideLeft", fill: "var(--text)", fontSize: 10 }} />
                <Tooltip content={<HistTooltip />} />
                <Bar dataKey="count" name="Pixel count" fill={C_HIST}
                  isAnimationActive={false} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </ChartCard>
    </div>
  );
}

// ── Custom tooltips ────────────────────────────────────────────────────────

function IntensityTooltip({ active, payload, label, color = C_AVG, dataKey = "avg_intensity" }) {
  if (!active || !payload?.length) return null;
  const val = payload[0]?.value;
  return (
    <div className="chartTooltip">
      <span><span className="tooltipLabel">Frame </span><span className="tooltipValue">{label}</span></span>
      <span><span className="tooltipLabel">Intensity </span>
        <span className="tooltipValue" style={{ color }}>{typeof val === "number" ? val.toFixed(2) : val}</span>
      </span>
    </div>
  );
}

function MinMaxTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chartTooltip">
      <span><span className="tooltipLabel">Frame </span><span className="tooltipValue">{label}</span></span>
      {payload.map((p) => (
        <span key={p.dataKey}>
          <span className="tooltipLabel">{p.name} </span>
          <span className="tooltipValue" style={{ color: p.stroke }}>{p.value}</span>
        </span>
      ))}
    </div>
  );
}

function HistTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chartTooltip">
      <span><span className="tooltipLabel">Intensity </span><span className="tooltipValue">{label}</span></span>
      <span><span className="tooltipLabel">Count </span>
        <span className="tooltipValue" style={{ color: C_HIST }}>{payload[0]?.value?.toLocaleString()}</span>
      </span>
    </div>
  );
}
