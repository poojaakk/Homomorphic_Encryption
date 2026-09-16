/**
 * VideoUpload
 * ===========
 * Handles video file selection, optional noise-std control, upload progress,
 * and calling POST /video/process.  On success it fires onResult(data) so
 * the parent (App.jsx) can store the result in state for charting.
 *
 * Props
 * -----
 *  onResult(data)  – called with the VideoProcessResponse JSON on success
 *  onNewLog(entry) – called to push log entries to the shared log panel
 */

import { useRef, useState } from "react";
import { processVideo } from "../api";

const ACCEPTED = ".mp4,.avi,.mov,.mkv,.webm,.m4v";

export default function VideoUpload({ onResult, onNewLog }) {
  const [file, setFile]           = useState(null);
  const [noiseStd, setNoiseStd]   = useState(5.0);
  const [busy, setBusy]           = useState(false);
  const [progress, setProgress]   = useState(0);   // 0-100 upload %
  const [status, setStatus]       = useState("");
  const [isError, setIsError]     = useState(false);
  const inputRef = useRef(null);

  function handleFileChange(e) {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    setStatus("");
    setIsError(false);
    setProgress(0);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!file) { setStatus("Please select a video file."); setIsError(true); return; }

    setBusy(true);
    setIsError(false);
    setStatus("Uploading…");
    setProgress(0);

    try {
      const res = await processVideo(file, noiseStd, (evt) => {
        if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100));
      });

      const d = res.data;
      setStatus(
        `Processed ${d.total_frames_extracted} frames in ${d.total_batches} batch(es). ` +
        `MAE (HE vs plaintext): ${d.overall_mae_he_vs_plain.toFixed(5)}`
      );
      onNewLog({ time: new Date().toISOString(), category: "api",
        message: `Video processed: ${d.info.filename} | ${d.total_frames_extracted} frames | ` +
                 `${d.total_batches} batch(es) | noise_std=${d.noise_std}` });
      onResult(d);
    } catch (err) {
      const detail =
        err.response?.data?.detail ??
        err.message ??
        "Unknown error";
      setStatus(`Error: ${detail}`);
      setIsError(true);
      onNewLog({ time: new Date().toISOString(), category: "error",
        message: `Video upload failed: ${detail}` });
    } finally {
      setBusy(false);
      setProgress(0);
    }
  }

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Video Upload</h2>
        <span className="muted">mp4 · avi · mov · mkv · webm</span>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="row" style={{ marginBottom: 10 }}>
          {/* Hidden real input, styled button triggers it */}
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED}
            onChange={handleFileChange}
            style={{ display: "none" }}
            id="video-file-input"
          />
          <label
            htmlFor="video-file-input"
            className="btn"
            style={{ cursor: "pointer" }}
          >
            {file ? "Change file" : "Choose video"}
          </label>

          {file && (
            <span className="muted" style={{ fontSize: 13, alignSelf: "center" }}>
              {file.name}&nbsp;·&nbsp;{(file.size / 1024 / 1024).toFixed(1)} MB
            </span>
          )}
        </div>

        <div className="row" style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 13, color: "var(--text)", alignSelf: "center" }}>
            Noise σ (0 = none):
          </label>
          <input
            className="input"
            type="number"
            min={0}
            max={50}
            step={0.5}
            value={noiseStd}
            onChange={(e) => setNoiseStd(parseFloat(e.target.value) || 0)}
            style={{ maxWidth: 90 }}
            disabled={busy}
          />
          <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>
            Gaussian noise injected into the feature signal before HE smoothing
          </span>
        </div>

        <div className="row">
          <button className="btn" type="submit" disabled={busy || !file}>
            {busy ? (
              <>
                <span className="spinner" />
                {progress > 0 && progress < 100
                  ? `Uploading ${progress}%…`
                  : "Processing…"}
              </>
            ) : (
              "Process video"
            )}
          </button>
        </div>
      </form>

      {/* Upload progress bar */}
      {busy && progress > 0 && progress < 100 && (
        <div className="noiseBarWrap" style={{ marginTop: 10 }}>
          <div
            className="noiseBar"
            style={{
              width: `${progress}%`,
              background: "var(--accent)",
            }}
          />
        </div>
      )}

      {status && (
        <p className={`uploadStatus${isError ? " uploadStatus--error" : ""}`}>
          {status}
        </p>
      )}
    </div>
  );
}
