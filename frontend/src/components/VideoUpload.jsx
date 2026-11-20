/**
 * VideoUpload
 * ===========
 * Upload card for the Video Streaming pipeline.
 * Lets the user pick a video file, set the CKKS bootstrap threshold,
 * and start the HE stream. Progress bar during upload; spinner during
 * frame processing.
 */

import { useRef, useState } from "react";
import { processVideo } from "../api";

const ACCEPTED       = ".mp4,.avi,.mov,.mkv,.webm,.m4v";
const MAX_SIZE_BYTES = 500 * 1024 * 1024; // 500 MB — matches backend guard
const THRESHOLD_MIN  = 10;
const THRESHOLD_MAX  = 500;
const THRESHOLD_DEFAULT = 50;

// Noise cost breakdown shown as a hint
const NOISE_COSTS = [
  { op: "encrypt",       cost: 1 },
  { op: "stream",        cost: 2 },
  { op: "add (frames)",  cost: 2 },
  { op: "scale × 0.5",  cost: 2 },
];
const PER_FRAME_COST = NOISE_COSTS.reduce((s, x) => s + x.cost, 0); // 7

export default function VideoUpload({ onResult, onNewLog }) {
  const [file,      setFile]      = useState(null);
  const [busy,      setBusy]      = useState(false);
  const [progress,  setProgress]  = useState(0);
  const [status,    setStatus]    = useState("");
  const [isError,   setIsError]   = useState(false);
  const [threshold, setThreshold] = useState(THRESHOLD_DEFAULT);
  const inputRef = useRef(null);

  function handleFileChange(e) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setIsError(false);
    setProgress(0);
    if (f && f.size > MAX_SIZE_BYTES) {
      setStatus(`File is ${(f.size / 1024 / 1024).toFixed(0)} MB — exceeds the 500 MB limit.`);
      setIsError(true);
    } else {
      setStatus("");
    }
  }

  function handleThresholdChange(e) {
    const v = Number(e.target.value);
    if (!isNaN(v)) setThreshold(Math.max(THRESHOLD_MIN, Math.min(THRESHOLD_MAX, v)));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file || file.size > MAX_SIZE_BYTES) return;

    setBusy(true);
    setIsError(false);
    setStatus("Uploading…");
    setProgress(0);

    try {
      const res = await processVideo(file, (evt) => {
        if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100));
      }, threshold);

      const d = res.data;
      setStatus(
        `Streamed ${d.frames_processed} frames · threshold ${threshold} · ` +
        `${d.total_bootstraps} bootstrap(s) · peak noise ${d.peak_noise}.`
      );
      onNewLog({
        time: new Date().toISOString(),
        category: "api",
        message:
          `Video HE stream: ${d.info.filename} | ${d.frames_processed} frames | ` +
          `threshold ${threshold} | ${d.total_bootstraps} bootstraps | peak noise ${d.peak_noise}`,
      });
      onResult(d);
    } catch (err) {
      const detail = err.response?.data?.detail ?? err.message ?? "Unknown error";
      setStatus(`Error: ${detail}`);
      setIsError(true);
      onNewLog({
        time: new Date().toISOString(),
        category: "error",
        message: `Video upload failed: ${detail}`,
      });
    } finally {
      setBusy(false);
      setProgress(0);
    }
  }

  // Estimated frames between bootstraps at current threshold
  const framesPerBoot = Math.max(1, Math.floor((threshold - 10) / PER_FRAME_COST));

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Video Upload</h2>
        <span className="muted">CKKS encrypt · add · scale · bootstrap</span>
      </div>

      <form onSubmit={handleSubmit}>
        {/* ── File picker ───────────────────────────────────────────── */}
        <div className="row" style={{ marginBottom: 12 }}>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            onChange={handleFileChange}
            style={{ display: "none" }}
            id="video-file-input"
          />
          <label htmlFor="video-file-input" className="btn" style={{ cursor: "pointer" }}>
            {file ? "Change file" : "Choose video"}
          </label>
          {file && (
            <span className="muted" style={{ fontSize: 13, alignSelf: "center" }}>
              {file.name}&nbsp;·&nbsp;{(file.size / 1024 / 1024).toFixed(1)} MB
            </span>
          )}
        </div>

        {/* ── Threshold control ─────────────────────────────────────── */}
        <div className="thresholdRow">
          <div className="thresholdLabel">
            <span>Bootstrap threshold</span>
            <span className="muted" style={{ fontSize: 11 }}>
              noise resets when it exceeds this value
            </span>
          </div>

          <div className="thresholdControls">
            <input
              type="range"
              min={THRESHOLD_MIN}
              max={THRESHOLD_MAX}
              step={5}
              value={threshold}
              onChange={handleThresholdChange}
              className="thresholdSlider"
              disabled={busy}
            />
            <input
              type="number"
              min={THRESHOLD_MIN}
              max={THRESHOLD_MAX}
              value={threshold}
              onChange={handleThresholdChange}
              className="thresholdNumber"
              disabled={busy}
            />
          </div>
        </div>

        {/* ── Noise cost breakdown ──────────────────────────────────── */}
        <div className="thresholdHint">
          <span>
            Per-frame noise cost:&nbsp;
            {NOISE_COSTS.map((c, i) => (
              <span key={c.op}>
                <span className="thresholdOp">{c.op}</span>
                <span className="thresholdCost"> +{c.cost}</span>
                {i < NOISE_COSTS.length - 1 ? " · " : ""}
              </span>
            ))}
            &nbsp;=&nbsp;<strong>{PER_FRAME_COST} units/frame</strong>
          </span>
          <span style={{ marginTop: 4 }}>
            Bootstrap fires approximately every&nbsp;
            <strong style={{ color: "var(--accent)" }}>~{framesPerBoot} frames</strong>
            &nbsp;at threshold&nbsp;<strong>{threshold}</strong>.
          </span>
        </div>

        {/* ── Submit ────────────────────────────────────────────────── */}
        <div className="row" style={{ marginTop: 14 }}>
          <button
            className="btn"
            type="submit"
            disabled={busy || !file || file?.size > MAX_SIZE_BYTES}
          >
            {busy ? (
              <>
                <span className="spinner" />
                {progress > 0 && progress < 100
                  ? `Uploading ${progress}%…`
                  : "Streaming frames…"}
              </>
            ) : (
              `Run HE stream  (threshold ${threshold})`
            )}
          </button>
        </div>
      </form>

      {/* ── Upload progress bar ───────────────────────────────────── */}
      {busy && progress > 0 && progress < 100 && (
        <div className="noiseBarWrap" style={{ marginTop: 10 }}>
          <div
            className="noiseBar"
            style={{ width: `${progress}%`, background: "var(--accent)" }}
          />
        </div>
      )}

      {/* ── Status ────────────────────────────────────────────────── */}
      {status && (
        <p className={`uploadStatus${isError ? " uploadStatus--error" : ""}`}>
          {status}
        </p>
      )}
    </div>
  );
}
