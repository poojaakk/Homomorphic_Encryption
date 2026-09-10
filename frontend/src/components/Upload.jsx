/**
 * Upload
 * ======
 * CSV upload panel. Sends the file + column name to POST /upload,
 * then the backend enqueues each row for encryption and Kafka streaming.
 *
 * The optional `onNewLog` prop lets it push log entries back up to App.
 */

import { useState } from "react";
import { uploadCsv } from "../api";

export default function Upload({ onNewLog }) {
  const [file, setFile]     = useState(null);
  const [column, setColumn] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy]     = useState(false);
  const [isError, setIsError] = useState(false);

  const handleUpload = async () => {
    if (!file || !column.trim()) {
      setStatus("Choose a CSV file and enter a column name.");
      setIsError(true);
      return;
    }
    setBusy(true);
    setIsError(false);
    setStatus("Uploading…");
    try {
      const res = await uploadCsv(file, column.trim());
      const msg = `Uploaded ${res.data.rows} rows from "${res.data.column_used}".`;
      setStatus(msg);
      if (onNewLog) {
        onNewLog({ time: new Date().toISOString(), category: "api", message: msg });
      }
    } catch (err) {
      const msg =
        err?.response?.data?.detail ??
        "Upload failed. Check that the backend is running and the column name is correct.";
      setStatus(msg);
      setIsError(true);
      if (onNewLog) {
        onNewLog({ time: new Date().toISOString(), category: "error", message: msg });
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Upload CSV</h2>
        <span className="muted">streams encrypted samples via Kafka</span>
      </div>

      <div className="row">
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="input"
          aria-label="CSV file"
        />
        <input
          type="text"
          placeholder='Column name (e.g. "temperature")'
          value={column}
          onChange={(e) => setColumn(e.target.value)}
          className="input"
          aria-label="Column name"
        />
        <button onClick={handleUpload} className="btn" disabled={busy}>
          {busy ? "Uploading…" : "Upload & stream"}
        </button>
      </div>

      <div className={`uploadStatus${isError ? " uploadStatus--error" : ""}`}>
        {status || "Tip: upload a CSV and pick one numeric column to stream."}
      </div>
    </div>
  );
}
