/**
 * VideoStatus
 * ===========
 * Shows video metadata and per-batch processing stats after a successful
 * POST /video/process call.
 *
 * Props
 * -----
 *  result  – VideoProcessResponse object (null while no video has been processed)
 */

export default function VideoStatus({ result }) {
  if (!result) {
    return (
      <div className="card">
        <div className="cardHeader">
          <h2>Video Info</h2>
        </div>
        <p className="muted" style={{ padding: "12px 0" }}>
          No video processed yet. Upload a video to see details here.
        </p>
      </div>
    );
  }

  const { info, total_frames_extracted, total_batches, noise_std,
          total_bootstraps,
          overall_mae_he_vs_plain, overall_mse_he_vs_plain,
          overall_mae_noisy_vs_orig, overall_mse_noisy_vs_orig, batches } = result;

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Video Info</h2>
        <span className="muted">{info.filename}</span>
      </div>

      {/* ── Metadata grid ─────────────────────────────────────────── */}
      <div className="videoInfoGrid">
        <Stat label="FPS"           value={info.fps} />
        <Stat label="Total frames"  value={info.total_frames} />
        <Stat label="Duration"      value={`${info.duration_sec.toFixed(2)} s`} />
        <Stat label="Resolution"    value={`${info.width} × ${info.height}`} />
        <Stat label="Extracted"     value={`${total_frames_extracted} samples`} />
        <Stat label="Batches"       value={total_batches} />
        <Stat label="Noise σ"       value={noise_std === 0 ? "none" : noise_std} />
        <Stat label="Bootstraps"    value={total_bootstraps ?? 0}
              hint="Total adaptive bootstrap refreshes during HE processing" accent />
      </div>

      {/* ── Validation metrics ────────────────────────────────────── */}
      <div className="cardHeader" style={{ marginTop: 14, marginBottom: 6 }}>
        <span style={{ fontSize: 13, color: "var(--text-h)", fontWeight: 500 }}>
          Validation metrics
        </span>
      </div>
      <div className="videoInfoGrid">
        <Stat
          label="MAE — HE vs plaintext"
          value={overall_mae_he_vs_plain.toFixed(6)}
          hint="HE smoothed vs equivalent plaintext average (CKKS approximation error)"
          accent
        />
        <Stat
          label="MSE — HE vs plaintext"
          value={overall_mse_he_vs_plain.toFixed(8)}
          accent
        />
        <Stat
          label="MAE — noisy vs original"
          value={overall_mae_noisy_vs_orig.toFixed(4)}
          hint="How much noise was injected before HE processing"
        />
        <Stat
          label="MSE — noisy vs original"
          value={overall_mse_noisy_vs_orig.toFixed(4)}
        />
      </div>

      {/* ── Batch table ───────────────────────────────────────────── */}
      {batches && batches.length > 0 && (
        <>
          <div className="cardHeader" style={{ marginTop: 14, marginBottom: 6 }}>
            <span style={{ fontSize: 13, color: "var(--text-h)", fontWeight: 500 }}>
              Batch breakdown
            </span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="videoTable">
              <thead>
                <tr>
                  <th>Batch</th>
                  <th>Frames</th>
                  <th>Range</th>
                  <th>Bootstraps</th>
                  <th>MAE (HE vs PT)</th>
                  <th>MSE (HE vs PT)</th>
                  <th>Noise Δ</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <tr key={b.batch_index}>
                    <td>{b.batch_index + 1}</td>
                    <td>{b.frame_indices.length}</td>
                    <td>
                      {b.frame_indices[0]}–{b.frame_indices[b.frame_indices.length - 1]}
                    </td>
                    <td style={{ color: "var(--accent)" }}>
                      {b.bootstraps_in_batch ?? 0}
                    </td>
                    <td>{b.mae.toFixed(6)}</td>
                    <td>{b.mse.toFixed(8)}</td>
                    <td>{b.noise_units_used}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

/** Small labelled stat cell */
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
