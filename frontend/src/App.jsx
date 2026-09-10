/**
 * App  –  root component
 * ======================
 * Owns all shared state and the WebSocket connection.
 * Passes slices of state down to Dashboard which composes the panels.
 *
 * WebSocket event types handled:
 *   stream    – new encrypted sample ingested
 *   noise     – periodic noise-heartbeat snapshot
 *   kafka_ack – Kafka consumer acknowledged a message
 *   bootstrap – a ciphertext refresh was performed
 *   error     – pipeline error
 *
 * The /status endpoint is polled every 5 s to populate the header pills.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import { getStatus } from "./api";
import Dashboard from "./components/Dashboard";

const WS_URL  = "ws://127.0.0.1:8000/ws";   // backend always on 8000
const MAX_PTS = 60;   // max chart points kept in state

export default function App() {
  // ── Live stream data (plaintext values for charting) ──────────────────
  const [stream, setStream]     = useState([]);
  // ── Noise history (for NoiseChart) ───────────────────────────────────
  const [noise, setNoise]       = useState([]);
  // ── In-memory log entries ─────────────────────────────────────────────
  const [logs, setLogs]         = useState([]);
  // ── Kafka ack counter ─────────────────────────────────────────────────
  const [kafkaAcks, setKafkaAcks] = useState(0);
  // ── System status from /status ────────────────────────────────────────
  const [status, setStatus]     = useState(null);

  const streamIdx = useRef(0);
  const noiseIdx  = useRef(0);

  // ── WebSocket ─────────────────────────────────────────────────────────
  useEffect(() => {
    let ws;
    let reconnectTimer;

    function connect() {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        pushLog("system", "WebSocket connected");
      };

      ws.onmessage = (e) => {
        let msg;
        try { msg = JSON.parse(e.data); }
        catch { return; }

        switch (msg.type) {
          case "stream": {
            const t = streamIdx.current++;
            const nt = noiseIdx.current++;

            setStream((prev) => [
              ...prev.slice(-(MAX_PTS - 1)),
              { t, value: msg.data?.[0] ?? null, key: msg.message_key },
            ]);

            setNoise((prev) => [
              ...prev.slice(-(MAX_PTS - 1)),
              {
                t: nt,
                noise:        msg.noise,
                threshold:    msg.threshold,
                noise_rate:   msg.noise_rate,
                pct_used:     msg.pct_used,
                bootstraps:   msg.bootstraps,
                refreshed:    msg.refreshed,
                refresh_before: msg.refresh_before,
                refresh_after:  msg.refresh_after,
              },
            ]);
            break;
          }

          case "noise": {
            // Heartbeat snapshot — update the last noise point's metadata.
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

          case "error":
            pushLog("error", msg.message ?? "Unknown pipeline error");
            break;

          default:
            break;
        }
      };

      ws.onerror = () => pushLog("error", "WebSocket error");
      ws.onclose = () => {
        pushLog("system", "WebSocket closed — reconnecting in 3 s…");
        reconnectTimer = setTimeout(connect, 3000);
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
      } catch {
        // backend may not be up yet — silent
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  // ── Log helper (used by child components via onNewLog prop) ───────────
  function pushLog(category, message) {
    setLogs((prev) => [
      ...prev.slice(-499),
      { time: new Date().toISOString(), category, message },
    ]);
  }

  function handleNewLog(entry) {
    setLogs((prev) => [...prev.slice(-499), entry]);
  }

  return (
    <Dashboard
      stream={stream}
      noise={noise}
      logs={logs}
      kafkaAcks={kafkaAcks}
      status={status}
      onNewLog={handleNewLog}
    />
  );
}
