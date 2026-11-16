/**
 * Controls
 * ========
 * Allows the user to trigger HE operations on the encrypted store.
 *
 * Each button shows a spinner while the request is in-flight and
 * renders the JSON response in a formatted code block. Errors are
 * surfaced with a red tint.
 *
 * The optional `onNewLog` prop lets Controls push entries into the
 * parent's in-memory log list so the Logs panel stays in sync
 * without needing a polling round-trip.
 */

import { useState } from "react";
import { add, bootstrap, decrypt, encrypt, multiply } from "../api";

const BUTTONS = [
  { id: "encrypt",  label: "Encrypt sample",     fn: encrypt,  variant: ""       },
  { id: "add",      label: "Add last two",        fn: add,      variant: ""       },
  { id: "multiply", label: "Multiply last two",   fn: multiply, variant: ""       },
  { id: "boot",     label: "Bootstrap",           fn: bootstrap,variant: "warn"   },
  { id: "decrypt",  label: "Decrypt last",        fn: decrypt,  variant: "danger" },
];

export default function Controls({ onNewLog }) {
  const [output, setOutput]   = useState(null);
  const [busy, setBusy]       = useState(null);   // id of the in-flight button
  const [isError, setIsError] = useState(false);

  const call = async (id, fn) => {
    setBusy(id);
    setIsError(false);
    try {
      const res = await fn();
      setOutput(res.data);
      if (onNewLog) {
        onNewLog({
          time: new Date().toISOString(),
          category: "api",
          message: `${id} → ${JSON.stringify(res.data).slice(0, 120)}`,
        });
      }
    } catch (err) {
      const msg = err?.response?.data?.detail ?? err?.message ?? "Request failed";
      setOutput({ error: msg });
      setIsError(true);
      if (onNewLog) {
        onNewLog({
          time: new Date().toISOString(),
          category: "error",
          message: `${id} failed: ${msg}`,
        });
      }
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Controls</h2>
        <span className="muted">operates on the uploaded CSV column</span>
      </div>

      <div className="row">
        {BUTTONS.map(({ id, label, fn, variant }) => (
          <button
            key={id}
            className={`btn${variant ? ` ${variant}` : ""}`}
            disabled={busy !== null}
            onClick={() => call(id, fn)}
            aria-busy={busy === id}
          >
            {busy === id ? <span className="spinner" aria-hidden="true" /> : null}
            {busy === id ? "Working…" : label}
          </button>
        ))}
      </div>

      {output !== null && (
        <div className="output">
          <div className="muted">Result</div>
          <pre className={`pre${isError ? " pre--error" : ""}`}>
            {JSON.stringify(output, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
