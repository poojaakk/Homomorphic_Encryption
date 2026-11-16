/**
 * Original stream vs decrypt after HE add/scale.
 * Pixel look is not the proof — the CKKS noise chart is.
 */

import { useEffect, useRef, useState } from "react";

export default function VideoCompare({ result }) {
  const [playing, setPlaying] = useState(false);
  const [frame, setFrame] = useState(0);
  const timer = useRef(null);

  const orig = result?.original_frames_jpeg ?? [];
  const he = result?.result_frames_jpeg ?? [];
  const n = Math.min(orig.length, he.length);
  const fps = result?.fps > 1 ? result.fps : 12;

  useEffect(() => {
    setPlaying(false);
    setFrame(0);
  }, [result]);

  useEffect(() => {
    if (!playing || n === 0) {
      if (timer.current) clearInterval(timer.current);
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

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Stream playback</h2>
        <span className="muted">{n} frames · {result.computation}</span>
      </div>

      <div className="videoCompareGrid">
        <Clip title="Original frames" jpeg={orig[frame]} />
        <Clip title="Decrypt after HE add(prev, curr) × 0.5" jpeg={he[frame]} />
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
        <span className="muted" style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
          frame {frame + 1}/{n}
        </span>
      </div>

      <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
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
