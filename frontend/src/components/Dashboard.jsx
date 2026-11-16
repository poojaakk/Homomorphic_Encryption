/**
 * Dashboard
 * =========
 * Top-level layout component. Receives all live state from App.jsx and
 * composes every panel for whichever mode is active.
 *
 * CSV mode panels (original, completely unchanged):
 *  Header → Upload → Charts (Streaming + Noise side-by-side) → Controls → Logs
 *
 * Video mode panels:
 *  Header → VideoUpload → playback → computations + noise/bootstrap + graph → Logs
 *
 * The mode selector bar sits between the header and the content panels.
 * Logs are shared across both modes.
 */

import Controls        from "./Controls";
import Logs            from "./Logs";
import NoiseChart      from "./NoiseChart";
import StreamingChart  from "./StreamingChart";
import Upload          from "./Upload";
import VideoCompare    from "./VideoCompare";
import VideoNoiseChart from "./VideoNoiseChart";
import VideoUpload     from "./VideoUpload";

export default function Dashboard({
  mode, onModeChange,
  status, logs, onNewLog,
  // csv
  stream, noise, kafkaAcks,
  // video
  videoResult, onVideoResult, videoLiveNoise = [],
}) {
  const latestNoise = noise[noise.length - 1];
  const pctUsed     = latestNoise?.pct_used  ?? 0;
  const noiseRate   = latestNoise?.noise_rate ?? 0;

  return (
    <div className="app">

      {/* ── Header ───────────────────────────────────────────────────── */}
      <header className="header">
        <div className="title">
          <div className="badge" aria-label="FHE">FHE</div>
          <div className="titleText">
            <h1 className="titleH1">Homomorphic HE Streaming</h1>
            <p className="sub">
              CKKS · Kafka pipeline · Adaptive noise budget · Real-time dashboard
            </p>
          </div>
        </div>

        <div className="pillrow">
          <StatusPill label="Kafka acks"  value={kafkaAcks} />
          <StatusPill label="Store size"  value={stream.length} />
          <StatusPill
            label="Noise %"
            value={`${pctUsed}%`}
            highlight={pctUsed > 80}
          />
          <StatusPill label="Noise rate"  value={`${noiseRate}/s`} />
          <StatusPill
            label="Context"
            value={status?.context_ready ? "✓ Ready" : "…"}
            highlight={!status?.context_ready}
          />
          <StatusPill
            label="Kafka"
            value={status?.kafka_producer_ready ? "✓ Live" : "✗ Down"}
            highlight={!status?.kafka_producer_ready}
          />
        </div>
      </header>

      {/* ── Mode selector ────────────────────────────────────────────── */}
      <div className="modeBar">
        <span className="modeLabel">Data source:</span>
        <button
          className={`modeBtn${mode === "csv" ? " modeBtn--active" : ""}`}
          onClick={() => onModeChange("csv")}
        >
          CSV / Static Data
        </button>
        <button
          className={`modeBtn${mode === "video" ? " modeBtn--active" : ""}`}
          onClick={() => onModeChange("video")}
        >
          Video Streaming
        </button>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          CSV / STATIC MODE  — all original panels, completely unchanged
      ═══════════════════════════════════════════════════════════════ */}
      {mode === "csv" && (
        <>
          <section className="section">
            <Upload onNewLog={onNewLog} />
          </section>

          <section className="grid">
            <StreamingChart data={stream} />
            <NoiseChart data={noise} />
          </section>

          <section className="section">
            <Controls onNewLog={onNewLog} />
          </section>
        </>
      )}

      {/* ═══════════════════════════════════════════════════════════════
          VIDEO STREAMING MODE  — new panels
      ═══════════════════════════════════════════════════════════════ */}
      {mode === "video" && (
        <>
          {/* Upload */}
          <section className="section">
            <VideoUpload onResult={onVideoResult} onNewLog={onNewLog} />
          </section>

          <section className="section">
            <VideoCompare result={videoResult} />
          </section>

          <section className="section">
            <VideoNoiseChart result={videoResult} liveData={videoLiveNoise} />
          </section>
        </>
      )}

      {/* ── Logs — shared across both modes ──────────────────────────── */}
      <section className="section">
        <Logs entries={logs} />
      </section>

    </div>
  );
}

/** Reusable stat pill */
function StatusPill({ label, value, highlight = false }) {
  return (
    <div className={`pill${highlight ? " pill--alert" : ""}`}>
      <span className="pillLabel">{label}</span>
      <span className="pillValue">{value}</span>
    </div>
  );
}
