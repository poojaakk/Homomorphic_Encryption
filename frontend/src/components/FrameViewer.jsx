/**
 * FrameViewer
 * ===========
 * Displays one extracted frame at a time with its grayscale statistics.
 * Navigation: Prev / Next buttons, scrubber slider, and a "Go to frame" input.
 * The displayed frame is synchronized with the graph selection via
 * selectedFrame / onSelectFrame props.
 *
 * Fetches JPEG thumbnails from GET /frames/page on demand — only the
 * currently displayed frame is ever in the DOM.
 *
 * Props
 * -----
 *   stats          – FrameStatModel[]  (full stats list from analysis result)
 *   selectedFrame  – currently selected frame index
 *   onSelectFrame  – called with new index when user navigates
 */

import { useEffect, useState } from "react";
import { getFramePage } from "../api";

export default function FrameViewer({ stats = [], selectedFrame = 0, onSelectFrame }) {
  const [jpeg,      setJpeg]      = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [jumpInput, setJumpInput] = useState("");

  const total = stats.length;
  const stat  = stats[selectedFrame] ?? null;

  // Fetch JPEG whenever the selected frame changes
  useEffect(() => {
    if (total === 0) return;
    setLoading(true);
    getFramePage(selectedFrame, 640, 360)
      .then((res) => setJpeg(res.data.jpeg_b64))
      .catch(() => setJpeg(null))
      .finally(() => setLoading(false));
  }, [selectedFrame, total]);

  if (total === 0) {
    return (
      <div className="card">
        <div className="cardHeader">
          <h2>Frame Viewer</h2>
          <span className="muted">navigate extracted frames</span>
        </div>
        <p className="muted" style={{ padding: "16px 0", textAlign: "center" }}>
          Extract a video to browse its frames here.
        </p>
      </div>
    );
  }

  function go(idx) {
    const clamped = Math.max(0, Math.min(total - 1, idx));
    onSelectFrame?.(clamped);
  }

  function handleJump(e) {
    e.preventDefault();
    const n = parseInt(jumpInput, 10);
    if (!isNaN(n)) go(n);
    setJumpInput("");
  }

  const ts = stat ? stat.timestamp_s.toFixed(3) : "—";

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Frame Viewer</h2>
        <span className="muted">
          frame {selectedFrame} of {total - 1} · {ts} s
        </span>
      </div>

      {/* ── Frame image ─────────────────────────────────────────── */}
      <div className="faViewerImg">
        {loading ? (
          <div className="faViewerPlaceholder">
            <span className="spinner" />
            <span className="muted" style={{ marginLeft: 10 }}>Loading frame…</span>
          </div>
        ) : jpeg ? (
          <img
            src={`data:image/jpeg;base64,${jpeg}`}
            alt={`Frame ${selectedFrame}`}
            className="faFrameImg"
          />
        ) : (
          <div className="faViewerPlaceholder">
            <span className="muted">Frame unavailable</span>
          </div>
        )}
      </div>

      {/* ── Navigation controls ──────────────────────────────────── */}
      <div className="row" style={{ marginTop: 12, flexWrap: "wrap", gap: 8 }}>
        <button className="btn" type="button" onClick={() => go(selectedFrame - 1)}
          disabled={selectedFrame === 0}>
          ← Prev
        </button>
        <input
          type="range"
          min={0} max={Math.max(0, total - 1)}
          value={selectedFrame}
          onChange={(e) => go(Number(e.target.value))}
          style={{ flex: 1, minWidth: 120 }}
        />
        <button className="btn" type="button" onClick={() => go(selectedFrame + 1)}
          disabled={selectedFrame >= total - 1}>
          Next →
        </button>
      </div>

      {/* ── Go-to-frame search ───────────────────────────────────── */}
      <form onSubmit={handleJump} className="row" style={{ marginTop: 10, gap: 8 }}>
        <input
          type="number"
          min={0} max={total - 1}
          placeholder={`0 – ${total - 1}`}
          value={jumpInput}
          onChange={(e) => setJumpInput(e.target.value)}
          className="faJumpInput"
        />
        <button className="btn" type="submit">Go to frame</button>
        <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>
          {selectedFrame + 1} / {total}
        </span>
      </form>

      {/* ── Per-frame stats ──────────────────────────────────────── */}
      {stat && (
        <div className="videoInfoGrid" style={{ marginTop: 14 }}>
          <StatCell label="Frame #"      value={stat.frame_idx} />
          <StatCell label="Timestamp"    value={`${stat.timestamp_s.toFixed(3)} s`} />
          <StatCell label="Resolution"   value={`${stat.width} × ${stat.height}`} />
          <StatCell label="Avg intensity" value={stat.avg_intensity.toFixed(2)} accent />
          <StatCell label="Min intensity" value={stat.min_intensity} />
          <StatCell label="Max intensity" value={stat.max_intensity} />
          <StatCell label="Std deviation" value={stat.std_intensity.toFixed(3)} />
          <StatCell label="Frame size"   value={`${stat.frame_size_kb.toFixed(1)} KB`} />
        </div>
      )}
    </div>
  );
}

function StatCell({ label, value, accent = false }) {
  return (
    <div className="videoStat">
      <span className="videoStatLabel">{label}</span>
      <span className={`videoStatValue${accent ? " videoStatValue--accent" : ""}`}>
        {value}
      </span>
    </div>
  );
}
