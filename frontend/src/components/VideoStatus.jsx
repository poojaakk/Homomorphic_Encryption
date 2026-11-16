/**
 * Video Info — stream length and CKKS bootstrap counts.
 */

export default function VideoStatus({ result }) {
  if (!result) {
    return (
      <div className="card">
        <div className="cardHeader">
          <h2>Video Info</h2>
        </div>
        <p className="muted" style={{ padding: "12px 0" }}>
          No stream yet. Upload a video to run HE on every frame.
        </p>
      </div>
    );
  }

  const {
    info, frames_processed, fps, process_width, process_height,
    total_bootstraps, peak_noise, computation,
  } = result;

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Video Info</h2>
        <span className="muted">{info.filename}</span>
      </div>

      <div className="videoInfoGrid">
        <Stat label="Source FPS" value={info.fps} />
        <Stat label="Source frames" value={info.total_frames} />
        <Stat label="Duration" value={`${info.duration_sec.toFixed(2)} s`} />
        <Stat label="Source size" value={`${info.width} × ${info.height}`} />
        <Stat label="Frames streamed" value={frames_processed} accent />
        <Stat label="HE grid" value={`${process_width} × ${process_height}`} />
        <Stat label="Playback FPS" value={Number(fps).toFixed(2)} />
        <Stat
          label="Bootstraps"
          value={total_bootstraps ?? 0}
          hint="Times CKKS computation noise was reset"
          accent
        />
        <Stat
          label="Peak CKKS noise"
          value={peak_noise}
          hint="Highest computation-noise counter before a reset"
        />
      </div>
      <p className="muted" style={{ fontSize: 12, marginTop: 10 }}>
        {computation}
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
