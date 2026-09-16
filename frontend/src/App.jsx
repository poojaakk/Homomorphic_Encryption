/**
 * App  –  root component
 * ======================
 * Owns ALL shared state and the single WebSocket connection.
 *
 * Modes
 * -----
 *   "csv"   – existing static CSV pipeline (completely unchanged)
 *   "video" – new video streaming pipeline
 *
 * WebSocket event types handled
 * ------------------------------
 *   stream          – CSV mode: new encrypted sample ingested
 *   noise           – CSV mode: periodic noise heartbeat
 *   kafka_ack       – CSV mode: Kafka consumer ack
 *   bootstrap       – CSV mode: ciphertext refresh
 *   video_frame     – VIDEO: per-frame noise snapshot (fires during processing)
 *   video_bootstrap – VIDEO: bootstrap fired inside video pipeline
 *   video_stream    – VIDEO: one batch completed
 *   error           – any pipeline error
 */

import { useEffect, useRef, useState } from "react";
import "./App.css";
import { getStatus } from "./api";
import Dashboard from "./components/Dashboard";

const WS_URL  = "ws://127.0.0.1:8000/ws";
const MAX_PTS = 60;      // max CSV chart points
const MAX_VID_LIVE = 500; // max live video noise frames kept in state

export default function App() {
  // ── Mode ──────────────────────────────────────────────────────────────
  const [mode, setMode] = useState("csv");   // "csv" | "video"

  // ── CSV / static state ────────────────────────────────────────────────
  const [stream,    setStream]    = useState([]);
  const [noise,     setNoise]     = useState([]);
  const [logs,      setLogs]      = useState([]);
  const [kafkaAcks, setKafkaAcks] = useState(0);
  const [status,    setStatus]    = useState(null);

  const streamIdx = useRef(0);
  const noiseIdx  = useRef(0);

  // ── Video state ───────────────────────────────────────────────────────
  // Full VideoProcessResponse once POST /video/process returns
  const [videoResult,   setVideoResult]   = useState(null);
  // Live per-frame noise snapshots arriving via WS during processing.
  // Shape: { frame_idx, noise, threshold, pct_used, bootstrapped, bootstraps }
  const [videoLiveNoise, setVideoLiveNoise] = useState([]);

  // ── WebSocket ─────────────────────────────────────────────────────────
  useEffect(() => {
    let ws;
    let reconnectTimer;

    function connect() {
      ws = new WebSocket(WS_URL);

      ws.onopen  = () => pushLog("system", "WebSocket connected");
      ws.onerror = () => pushLog("error",  "WebSocket error");
      ws.onclose = () => {
        pushLog("system", "WebSocket closed — reconnecting in 3 s…");
        reconnectTimer = setTimeout(connect, 3000);
      };

      ws.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); } catch { return; }

        switch (msg.type) {

          // ── CSV pipeline events ──────────────────────────────────────
          case "stream": {
            const t  = streamIdx.current++;
            const nt = noiseIdx.current++;
            setStream((prev) => [
              ...prev.slice(-(MAX_PTS - 1)),
              { t, value: msg.data?.[0] ?? null, key: msg.message_key },
            ]);
            setNoise((prev) => [
              ...prev.slice(-(MAX_PTS - 1)),
              {
                t: nt,
                noise:          msg.noise,
                threshold:      msg.threshold,
                noise_rate:     msg.noise_rate,
                pct_used:       msg.pct_used,
                bootstraps:     msg.bootstraps,
                refreshed:      msg.refreshed,
                refresh_before: msg.refresh_before,
                refresh_after:  msg.refresh_after,
              },
            ]);
            break;
          }

          case "noise": {
            const nt = noiseIdx.current++;
            setNoise((prev) => [
              ...prev.slice(-(MAX_PTS - 1)),
              {
                t: nt,
                noise:      msg.noise,
                threshold:  msg.threshold,
                noise_rate: msg.noise_rate,
                pct_used:   msg.pct_used,
                bootstraps: msg.bootstraps,
                refreshed:  false,
              },
            ]);
            break;
          }

          case "kafka_ack":
            setKafkaAcks((n) => n + 1);
            break;

          case "bootstrap":
            pushLog(
              "noise",
              `Bootstrap (${msg.label}): ${msg.before} → ${msg.after} | total ${msg.bootstraps}`,
            );
            break;

          // ── Video pipeline events ────────────────────────────────────
          case "video_frame": {
            // Arrives for every processed frame — build the live noise chart
            setVideoLiveNoise((prev) => [
              ...prev.slice(-(MAX_VID_LIVE - 1)),
              {
                frame_idx:    msg.frame_idx,
                noise:        msg.noise,
                threshold:    msg.threshold,
                pct_used:     msg.pct_used,
                bootstrapped: msg.bootstrapped,
                bootstraps:   msg.bootstraps,
              },
            ]);
            break;
          }

          case "video_bootstrap":
            pushLog(
              "noise",
              `Video bootstrap #${msg.bootstraps}: frame ${msg.frame_idx} | ` +
              `noise ${msg.before} → ${msg.after} | threshold ${msg.threshold}`,
            );
            break;

          case "video_stream":
            pushLog(
              "api",
              `Video batch ${msg.batch_index + 1} complete — ` +
              `${msg.frame_count} frames | ` +
              `${msg.bootstraps_in_batch} bootstrap(s) | ` +
              `noise Δ ${msg.noise_units_used}`,
            );
            break;

          case "error":
            pushLog("error", msg.message ?? "Unknown pipeline error");
            break;

          default:
            break;
        }
      };
    }

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  // ── Status polling ────────────────────────────────────────────────────
  useEffect(() => {
    const poll = async () => {
      try {
        const res = await getStatus();
        setStatus(res.data);
      } catch { /* silent while backend starts */ }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  // ── Helpers ───────────────────────────────────────────────────────────
  function pushLog(category, message) {
    setLogs((prev) => [
      ...prev.slice(-499),
      { time: new Date().toISOString(), category, message },
    ]);
  }
  function handleNewLog(entry) {
    setLogs((prev) => [...prev.slice(-499), entry]);
  }

  function handleVideoResult(data) {
    setVideoResult(data);
    // Clear live data — VideoNoiseChart will use the full snapshots from result
    setVideoLiveNoise([]);
  }

  // When user switches to video mode, clear stale live noise data
  function handleModeChange(newMode) {
    setMode(newMode);
    if (newMode === "video") setVideoLiveNoise([]);
  }

  return (
    <Dashboard
      /* shared */
      mode={mode}
      onModeChange={handleModeChange}
      status={status}
      logs={logs}
      onNewLog={handleNewLog}
      /* csv */
      stream={stream}
      noise={noise}
      kafkaAcks={kafkaAcks}
      /* video */
      videoResult={videoResult}
      onVideoResult={handleVideoResult}
      videoLiveNoise={videoLiveNoise}
    />
  );
}
