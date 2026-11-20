/**
 * Original stream vs decrypt after HE add/scale.
 * Pixel look is not the proof — the CKKS noise chart is.
 *
 * Large-video note
 * ----------------
 * For 2000-frame results the response may contain 2000 base64 JPEGs.  We
 * never render more than one <img> per side at a time, so the DOM footprint
 * is constant regardless of frame count.  The play/pause loop and scrubber
 * both work at any size.
 */

import { useEffect, useRef, useState } from "react";

export default function VideoCompare({ result }) {
  const [playing, setPlaying] = useState(false);
  const [frame, setFrame]     = useState(0);
  const timer = useRef(null);

  const orig = result?.original_frames_jpeg ?? [];
  const he   = result?.result_frames_jpeg   ?? [];
  const n    = Math.min(orig.length, he.length);
  // Cap playback at 30 fps so large frame sets don't blast through instantly
  const fps  = Math.min(result?.fps > 1 ? result.fps : 12, 30);

  // Reset on new result
  useEffect(() => {
    setPlaying(false);
    setFrame(0);
  }, [result]);

  // Play/pause loop
  useEffect(() => {
    if (!playing || n === 0) {
      clearInterval(timer.current);
      return;
    }
    const ms = Math.max(40, Math.round(1000 / fps));
    timer.current = setInterval(() => {
      setFrame((i) => (i + 1) % n);
    }, ms);
    return () => clearInterval(timer.current);
  }, [playing, n, fps]);

  if (!result || n === 0) {
    return (
      <div className="card">
        <div className="cardHeader">
          <h2>Stream playback</h2>
          <span className="muted">every frame · encrypt · add last two · bootstrap</span>
        </div>
        <div className="chart" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <p className="muted">Upload a video to stream all frames through HE.</p>
        </div>
      </div>
    );
  }

  const truncated     = result?.truncated;
  const sourceTotal   = result?.info?.total_frames;
  const framesLabel   = truncated && sourceTotal && n < sourceTotal
    ? `${n} sampled frames of ${sourceTotal} source`
    : `${n} frames`;

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Stream playback</h2>
        <span className="muted">{framesLabel} · {result.computation}</span>
      </div>

      {/* Only two <img> elements are ever in the DOM, regardless of n */}
      <div className="videoCompareGrid">
        <Clip title="Original frames"                    jpeg={orig[frame]} />
        <Clip title="Decrypt after HE add(prev, curr) × 0.5" jpeg={he[frame]}   />
      </div>

      <div className="row" style={{ marginTop: 12 }}>
        <button className="btn" type="button" onClick={() => setPlaying((p) => !p)}>
          {playing ? "Pause" : "Play both"}
        </button>
        <input
          type="range"
          min={0}
          max={Math.max(0, n - 1)}
          value={frame}
          onChange={(e) => {
            setPlaying(false);
            setFrame(Number(e.target.value));
          }}
          style={{ flex: 1, minWidth: 120 }}
        />
        <span className="muted" style={{ fontFamily: "var(--mono)", fontSize: 12, whiteSpace: "nowrap" }}>
          frame {frame + 1}/{n}
        </span>
      </div>

      {truncated && (
        <p className="muted" style={{ fontSize: 12, marginTop: 6, color: "var(--accent)" }}>
          ⚡ Large video: {sourceTotal} source frames uniformly sampled down to {n} for HE processing.
        </p>
      )}

      <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
        Right side is decrypt of the streaming op (add last two encrypted frames,
        × 0.5). Noise generated, bootstrap, and the graph are in the panel below.
      </p>
    </div>
  );
}

function Clip({ title, jpeg }) {
  return (
    <div className="videoClip">
      <div className="videoClipTitle">{title}</div>
      <img
        className="videoClipImg"
        alt={title}
        src={jpeg ? `data:image/jpeg;base64,${jpeg}` : ""}
      />
    </div>
  );
}
