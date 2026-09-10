/**
 * Logs
 * ====
 * Live, categorised log panel.
 *
 * Features:
 *  - Category filter tabs: All | api | compute | noise | kafka | error | system
 *  - Colour-coded badges per category
 *  - Auto-scrolls to the latest entry
 *  - Shows the last 100 entries maximum
 */

import { useEffect, useRef, useState } from "react";

const CATEGORIES = ["all", "api", "compute", "noise", "kafka", "error", "system"];

const CAT_COLORS = {
  api:     { bg: "rgba(99,102,241,0.15)",  text: "#818cf8" },
  compute: { bg: "rgba(34,197,94,0.15)",   text: "#4ade80" },
  noise:   { bg: "rgba(245,158,11,0.15)",  text: "#fbbf24" },
  kafka:   { bg: "rgba(14,165,233,0.15)",  text: "#38bdf8" },
  error:   { bg: "rgba(239,68,68,0.15)",   text: "#f87171" },
  system:  { bg: "rgba(156,163,175,0.15)", text: "#9ca3af" },
};

function catStyle(cat) {
  return CAT_COLORS[cat] ?? CAT_COLORS.system;
}

export default function Logs({ entries = [] }) {
  const [filter, setFilter] = useState("all");
  const bottomRef = useRef(null);

  const visible = (
    filter === "all" ? entries : entries.filter((e) => e.category === filter)
  ).slice(-100);

  // Auto-scroll whenever new entries arrive.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visible.length]);

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Logs</h2>
        <span className="muted">{visible.length} entries</span>
      </div>

      {/* Category filter tabs */}
      <div className="logTabs">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            className={`logTab${filter === cat ? " logTab--active" : ""}`}
            onClick={() => setFilter(cat)}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* Log entries */}
      <div className="logScroll">
        {visible.length === 0 ? (
          <div className="muted logEmpty">No log entries yet.</div>
        ) : (
          visible.map((entry, i) => {
            const style = catStyle(entry.category);
            return (
              <div key={i} className="logRow">
                <span className="logTime">{entry.time?.slice(11, 23) ?? ""}</span>
                <span
                  className="logCat"
                  style={{ background: style.bg, color: style.text }}
                >
                  {entry.category}
                </span>
                <span className="logMsg">{entry.message}</span>
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
