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
const MAX_PTS = 60;       // max CSV chart points
const MAX_VID_LIVE = 2000; // max live video noise frames kept in state (matches MAX_FRAMES)

export default function App() {
  // ── Mode ──────────────────────────────────────────────────────────────
  const [mode, setMode] = useState("csv");   // "csv" | "video" | "frames"

  // ── CSV / static state ────────────────────────────────────────────────
  const [stream,    setStream]    = useState([]);
  const [noise,     setNoise]     = useState([]);
  const [logs,      setLogs]      = useState([]);
  const [kafkaAcks, setKafkaAcks] = useState(0);
  const [status,    setStatus]    = useState(null);

  const streamIdx = useRef(0);
  const noiseIdx  = useRef(0);

  // ── Video state ───────────────────────────────────────────────────────
  // Full VideoProcessResponse once POST /video/process returns (jpegs + totals)
  const [videoResult,   setVideoResult]   = useState(null);
  // Frames revealed on the charts (drained from the WS queue so the line grows)
  const [videoLiveNoise, setVideoLiveNoise] = useState([]);
  const [videoStreaming, setVideoStreaming] = useState(false);
  const [videoExpected,  setVideoExpected]  = useState(0);
  const videoQueue = useRef([]);

  // ── Frame analysis state ──────────────────────────────────────────────
  // Full FrameAnalysisResponse once POST /frames/analyze returns
  const [frameAnalysisResult, setFrameAnalysisResult] = useState(null);
  // Live WS progress during frame extraction
  const [frameLiveProgress,   setFrameLiveProgress]   = useState(null);
  // true while backend is analyzing
  const [frameAnalyzing,      setFrameAnalyzing]      = useState(false);
  // currently selected frame index (shared between FrameGraphs and FrameViewer)
  const [selectedFrame,       setSelectedFrame]       = useState(0);

  // Drain queued video frames onto the charts so they stream instead of dumping.
  useEffect(() => {
    const id = setInterval(() => {
      const q = videoQueue.current;
      if (!q.length) return;
      const backlog = q.length;
      const take = backlog > 400 ? 16 : backlog > 120 ? 8 : backlog > 40 ? 3 : 1;
      const batch = q.splice(0, take);
      setVideoLiveNoise((prev) => [...prev, ...batch].slice(-MAX_VID_LIVE));
    }, 40);
    return () => clearInterval(id);
  }, []);

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
            const recv = performance.now();
            setStream((prev) => [
              ...prev.slice(-(MAX_PTS - 1)),
              {
                t,
                value: msg.data?.[0] ?? null,
                key: msg.message_key,
                sample_ms: msg.sample_ms ?? null,
                recv,
              },
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
                recv,
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
          case "video_start":
            videoQueue.current = [];
            setVideoLiveNoise([]);
            setVideoResult(null);
            setVideoStreaming(true);
            setVideoExpected(msg.total_frames || 0);
            pushLog("api", `Video HE stream started — ${msg.total_frames} frames (${msg.filename})`);
            break;

          case "video_frame": {
            videoQueue.current.push({
              frame_idx:       msg.frame_idx,
              noise:           msg.noise,
              threshold:       msg.threshold,
              pct_used:        msg.pct_used,
              bootstrapped:    msg.bootstrapped,
              bootstraps:      msg.bootstraps,
              ops:             msg.ops || [],
              noise_generated: msg.noise_generated || 0,
              noise_reduced:   msg.noise_reduced || 0,
              frame_a:         msg.frame_a,
              frame_b:         msg.frame_b,
              frame_ms:        msg.frame_ms || 0,
              elapsed_ms:      msg.elapsed_ms || 0,
              he_ops:          msg.he_ops || 0,
            });
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
            setVideoStreaming(false);
            pushLog(
              "api",
              `Video HE stream complete — ${msg.frame_count} frames | ` +
              `${msg.bootstraps_in_batch} bootstrap(s)` +
              (msg.throughput_fps ? ` | ${msg.throughput_fps} frames/s` : ""),
            );
            break;

          case "error":
            pushLog("error", msg.message ?? "Unknown pipeline error");
            break;

          // ── Frame extraction events ──────────────────────────────────
          case "frame_extraction_progress":
            setFrameAnalyzing(true);
            setFrameLiveProgress({
              frames_done:  msg.frames_done,
              total_frames: msg.total_frames,
              pct_done:     msg.pct_done,
            });
            break;

          case "frame_extraction_done":
            setFrameAnalyzing(false);
            pushLog(
              "api",
              `Frame extraction complete — ${msg.frames_analyzed} frames from "${msg.filename}"`,
            );
            break;

          case "frame_extraction_error":
            setFrameAnalyzing(false);
            pushLog("error", `Frame extraction error: ${msg.message}`);
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

  function handleVideoStart() {
    videoQueue.current = [];
    setVideoLiveNoise([]);
    setVideoResult(null);
    setVideoStreaming(true);
    setVideoExpected(0);
  }

  function handleVideoResult(data) {
    // Keep the live chart — do not dump all snapshots at once.
    setVideoResult(data);
    setVideoStreaming(false);
    if (data?.frames_processed) setVideoExpected(data.frames_processed);
    // If WS frames never arrived, stream the result onto the chart instead.
    setVideoLiveNoise((prev) => {
      if (prev.length === 0 && videoQueue.current.length === 0 && data?.all_noise_snapshots?.length) {
        videoQueue.current = data.all_noise_snapshots.map((s) => ({
          frame_idx: s.frame_idx,
          noise: s.noise,
          threshold: s.threshold,
          pct_used: s.pct_used,
          bootstrapped: s.bootstrapped,
          bootstraps: s.bootstraps,
          ops: s.ops || [],
          noise_generated: s.noise_generated || 0,
          noise_reduced: s.noise_reduced || 0,
          frame_a: s.frame_a,
          frame_b: s.frame_b,
          frame_ms: s.frame_ms || 0,
          elapsed_ms: s.elapsed_ms || 0,
          he_ops: s.he_ops || 0,
        }));
      }
      return prev;
    });
  }

  function handleFrameAnalysisResult(data) {
    setFrameAnalysisResult(data);
    setFrameLiveProgress(null);
    setFrameAnalyzing(false);
    setSelectedFrame(0);
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
      onVideoStart={handleVideoStart}
      onVideoResult={handleVideoResult}
      videoLiveNoise={videoLiveNoise}
      videoStreaming={videoStreaming}
      videoExpected={videoExpected}
      /* frame analysis */
      frameAnalysisResult={frameAnalysisResult}
      onFrameAnalysisResult={handleFrameAnalysisResult}
      frameLiveProgress={frameLiveProgress}
      frameAnalyzing={frameAnalyzing}
      selectedFrame={selectedFrame}
      onSelectFrame={setSelectedFrame}
    />
  );
}
