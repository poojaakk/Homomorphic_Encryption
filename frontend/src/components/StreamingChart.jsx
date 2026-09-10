/**
 * StreamingChart
 * ==============
 * Displays the last 30 plaintext sample values from the encrypted stream.
 * Each data point carries its Kafka message_key which is shown in the tooltip
 * so the UI stays connected to the actual ciphertext transported over Kafka.
 */

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chartTooltip">
      <div>
        <span className="tooltipLabel">Value</span>
        <span className="tooltipValue">{d.value?.toFixed(4) ?? "—"}</span>
      </div>
      <div>
        <span className="tooltipLabel">Sample #</span>
        <span className="tooltipValue">{d.t}</span>
      </div>
      <div className="tooltipKey" title={d.key}>
        <span className="tooltipLabel">Kafka key</span>
        <span className="tooltipMono">{d.key ? d.key.slice(0, 12) + "…" : "—"}</span>
      </div>
    </div>
  );
}

export default function StreamingChart({ data }) {
  const count = data?.length ?? 0;

  return (
    <div className="card">
      <div className="cardHeader">
        <h2>Streaming data</h2>
        <span className="muted">last {count} encrypted samples</span>
      </div>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="t" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip content={<CustomTooltip />} />
            <Line
              dataKey="value"
              stroke="var(--accent)"
              dot={false}
              activeDot={{ r: 4 }}
              strokeWidth={2}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
