/**
 * Dashboard
 * =========
 * The top-level layout component. Receives all live state from App.jsx
 * (via props) and composes every panel in the order shown in the
 * architecture diagram:
 *
 *  1. Header    – system status pills
 *  2. Upload    – CSV ingest
 *  3. Charts    – Streaming data + Noise budget (side-by-side)
 *  4. Controls  – HE operations
 *  5. Logs      – live categorised log feed
 */

import Controls from "./Controls";
import Logs from "./Logs";
import NoiseChart from "./NoiseChart";
import StreamingChart from "./StreamingChart";
import Upload from "./Upload";

export default function Dashboard({
  stream,
  noise,
  logs,
  kafkaAcks,
  status,
  onNewLog,
}) {
  const latestNoise = noise[noise.length - 1];
  const pctUsed = latestNoise?.pct_used ?? 0;
  const noiseRate = latestNoise?.noise_rate ?? 0;

  return (
    <div className="app">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="header">
        <div className="title">
          <div className="badge">FHE</div>
          <div>
            <h1>Noise-Resilient HE Streaming</h1>
            <p className="sub">
              CKKS · Kafka pipeline · Adaptive noise budget · Real-time dashboard
            </p>
          </div>
        </div>

        <div className="pillrow">
          <StatusPill label="Kafka acks" value={kafkaAcks} />
          <StatusPill label="Store size" value={stream.length} />
          <StatusPill
            label="Noise %"
            value={`${pctUsed}%`}
            highlight={pctUsed > 80}
          />
          <StatusPill label="Noise rate" value={`${noiseRate}/s`} />
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

      {/* ── Upload ──────────────────────────────────────────────────── */}
      <section className="section">
        <Upload onNewLog={onNewLog} />
      </section>

      {/* ── Charts ──────────────────────────────────────────────────── */}
      <section className="grid">
        <StreamingChart data={stream} />
        <NoiseChart data={noise} />
      </section>

      {/* ── Controls ────────────────────────────────────────────────── */}
      <section className="section">
        <Controls onNewLog={onNewLog} />
      </section>

      {/* ── Logs ────────────────────────────────────────────────────── */}
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
