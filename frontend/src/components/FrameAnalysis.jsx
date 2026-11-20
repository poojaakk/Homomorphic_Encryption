/**
 * FrameAnalysis
 * =============
 * Upload card + live processing-progress panel + video-info summary.
 * Calls POST /frames/analyze and streams per-frame progress via the
 * WebSocket (frame_extraction_progress events arrive in App.jsx and
 * are passed down as `liveProgress`).
 *
 * Props
 * -----
 *   onResult(data)   – called with the full FrameAnalysisResponse once done
 *   onNewLog(entry)  – pushes a log entry to the shared log panel
 *   liveProgress     – { frames_done, total_frames, pct_done } from WS
 *   analyzing        – boolean set by App while the backend is working
 */

import { useRef, useState } from "react";
import { analyzeFrames } from "../api";

const ACCEPTED       = ".mp4,.avi,.mov,.mkv,.webm,.m4v";
const MAX_SIZE_BYTES = 200 * 1024 * 1024;   // 200 MB

export default function FrameAnalysis({
  onResult,
  onNewLog,
  liveProgress = null,
  analyzing    = false,
}) {
  const [file,       setFile]       = useState(null);
  const [busy,       setBusy]       = useState(false);
  const [uploadPct,  setUploadPct]  = useState(0);
  const [status,     setStatus]     = useState("");
  const [isError,    setIsError]    = useState(false);
  const [result,     setResult]     = useState(null);
  const inputRef = useRef(null);

  function handleFileChange(e) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setIsError(false);
    setUploadPct(0);
    setStatus("");
    if (f && f.size > MAX_SIZE_BYTES) {
      setStatus(`File is ${(f.size / 1024 / 1024).toFixed(0)} MB — exceeds the 200 MB limit.`);
      setIsError(true);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file || file.size > MAX_SIZE_BYTES) return;

    setBusy(true);
    setIsError(false);
    setStatus("Uploading…");
    setUploadPct(0);
    setResult(null);

    try {
      const res = await analyzeFrames(file, (evt) => {
        if (evt.total) setUploadPct(Math.round((evt.loaded / evt.total) * 100));
      });
      const d = res.data;
      setResult(d);
      setStatus(
        `Extracted ${d.info.frames_analyzed} frames from "${d.info.filename}".`
      );
      onResult(d);
      onNewLog({
        time: new Date().toISOString(),
        category: "api",
        message:
          `Frame extraction complete: ${d.info.filename} | ` +
          `${d.info.frames_analyzed} frames | ${d.info.fps} fps | ` +
          `${d.info.duration_sec.toFixed(2)} s`,
      });
    } catch (err) {
      const detail = err.response?.data?.detail ?? err.message ?? "Unknown error";
      setStatus(`Error: ${detail}`);
      setIsError(true);
      onNewLog({
        time: new Date().toISOString(),
        category: "error",
        message: `Frame analysis failed: ${detail}`,
      });
    } finally {
      setBusy(false);
      setUploadPct(0);
    }
  }

  // Decide which progress to show:
  // During upload: uploadPct (0–100)
  // During processing: liveProgress from WS
  const isUploading  = busy && uploadPct > 0 && uploadPct < 100;
  const isProcessing = busy && (uploadPct === 100 || uploadPct === 0) && analyzing;
  const procPct      = liveProgress?.pct_done ?? 0;
  const framesDone   = liveProgress?.frames_done ?? 0;
  const totalFrames  = liveProgress?.total_frames ?? 0;

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Frame Extraction</h2>
        <span className="muted">
          every frame · grayscale stats · no HE
        </span>
      </div>

      {/* ── Upload form ──────────────────────────────────────────── */}
      <form onSubmit={handleSubmit}>
        <div className="row" style={{ marginBottom: 10 }}>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            onChange={handleFileChange}
            style={{ display: "none" }}
            id="fa-file-input"
          />
          <label htmlFor="fa-file-input" className="btn" style={{ cursor: "pointer" }}>
            {file ? "Change file" : "Choose video"}
          </label>
          {file && (
            <span className="muted" style={{ fontSize: 13, alignSelf: "center" }}>
              {file.name}&nbsp;·&nbsp;{(file.size / 1024 / 1024).toFixed(1)} MB
            </span>
          )}
        </div>

        <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
          Upload a video (up to 200 MB). Every frame is decoded, converted to
          grayscale, and its statistics (avg, min, max, std) are computed without
          loading all frames into RAM at once.
        </p>

        <div className="row">
          <button
            className="btn"
            type="submit"
            disabled={busy || !file || file?.size > MAX_SIZE_BYTES}
          >
            {busy ? (
              <>
                <span className="spinner" />
                {isUploading
                  ? `Uploading ${uploadPct}%…`
                  : "Extracting frames…"}
              </>
            ) : (
              "Extract frames"
            )}
          </button>
        </div>
      </form>

      {/* ── Upload progress bar ──────────────────────────────────── */}
      {isUploading && (
        <div className="noiseBarWrap" style={{ marginTop: 10 }}>
          <div
            className="noiseBar"
            style={{ width: `${uploadPct}%`, background: "var(--accent)" }}
          />
        </div>
      )}

      {/* ── Processing progress ──────────────────────────────────── */}
      {(isProcessing || (busy && !isUploading)) && (
        <div className="faProgressBox">
          <div className="faProgressHeader">
            <span>Extracting frames…</span>
            <span className="muted" style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
              {framesDone} / {totalFrames || "?"} frames ({procPct.toFixed(1)}%)
            </span>
          </div>
          <div className="noiseBarWrap" style={{ marginTop: 6 }}>
            <div
              className="noiseBar"
              style={{ width: `${Math.min(procPct, 100)}%`, background: "#38bdf8" }}
            />
          </div>
        </div>
      )}

      {/* ── Status message ───────────────────────────────────────── */}
      {status && (
        <p className={`uploadStatus${isError ? " uploadStatus--error" : ""}`}>
          {status}
        </p>
      )}

      {/* ── Video info summary (shown after success) ─────────────── */}
      {result && !isError && (
        <div style={{ marginTop: 14 }}>
          <div className="videoInfoGrid">
            <InfoStat label="File"       value={result.info.filename} />
            <InfoStat label="Duration"   value={`${result.info.duration_sec.toFixed(2)} s`} />
            <InfoStat label="FPS"        value={result.info.fps} />
            <InfoStat label="Resolution" value={`${result.info.width} × ${result.info.height}`} />
            <InfoStat label="Total frames"    value={result.info.total_frames} />
            <InfoStat label="Frames extracted" value={result.info.frames_analyzed} accent />
          </div>
        </div>
      )}
    </div>
  );
}

function InfoStat({ label, value, accent = false }) {
  return (
    <div className="videoStat">
      <span className="videoStatLabel">{label}</span>
      <span className={`videoStatValue${accent ? " videoStatValue--accent" : ""}`}>
        {value}
      </span>
    </div>
  );
}
