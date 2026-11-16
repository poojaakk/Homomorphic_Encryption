/**
 * Upload a full video; every frame is streamed through HE ops.
 */

import { useRef, useState } from "react";
import { processVideo } from "../api";

const ACCEPTED = ".mp4,.avi,.mov,.mkv,.webm,.m4v";

export default function VideoUpload({ onResult, onNewLog }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);
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
    if (!file) {
      setStatus("Please select a video file.");
      setIsError(true);
      return;
    }

    setBusy(true);
    setIsError(false);
    setStatus("Uploading…");
    setProgress(0);

    try {
      const res = await processVideo(file, (evt) => {
        if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100));
      });

      const d = res.data;
      setStatus(
        `Streamed ${d.frames_processed} frames. ` +
          `${d.total_bootstraps} bootstrap(s) reset CKKS computation noise ` +
          `(peak ${d.peak_noise}).`
      );
      onNewLog({
        time: new Date().toISOString(),
        category: "api",
        message:
          `Video HE stream: ${d.info.filename} | ${d.frames_processed} frames | ` +
          `${d.total_bootstraps} bootstraps | peak noise ${d.peak_noise}`,
      });
      onResult(d);
    } catch (err) {
      const detail =
        err.response?.data?.detail ?? err.message ?? "Unknown error";
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

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Video Upload</h2>
        <span className="muted">all frames · no extra noise added</span>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="row" style={{ marginBottom: 10 }}>
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

        <p className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
          Each frame is encrypted, then the last two ciphertexts are added and
          scaled by 0.5 (same add/scale as CSV). Noise on the graph is from
          those ops. Bootstrap drops it when the threshold is hit. Nothing is
          injected into the pixels.
        </p>

        <div className="row">
          <button className="btn" type="submit" disabled={busy || !file}>
            {busy ? (
              <>
                <span className="spinner" />
                {progress > 0 && progress < 100
                  ? `Uploading ${progress}%…`
                  : "Streaming frames…"}
              </>
            ) : (
              "Run HE stream"
            )}
          </button>
        </div>
      </form>

      {busy && progress > 0 && progress < 100 && (
        <div className="noiseBarWrap" style={{ marginTop: 10 }}>
          <div
            className="noiseBar"
            style={{ width: `${progress}%`, background: "var(--accent)" }}
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
