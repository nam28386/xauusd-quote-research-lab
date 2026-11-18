import type { Configuration, Query, Row, Scalar, Stream } from "./types.ts";

export const intervals = [100, 250, 500, 1000];
export const widths = [25, 50, 100, 250, 500, 1000];
export const metrics = {
  recall: {label: "Widening recall", version: "p2-sampling-metrics-v1", unit: "fraction"},
  revisions: {label: "Revision recall", version: "p2-sampling-metrics-v1", unit: "fraction"},
  coverage: {label: "Broker coverage", version: "broker-comparison-v1.1", unit: "fraction"},
  consensus: {label: "Consensus coverage", version: "broker-comparison-v1.1", unit: "fraction"}
} as const;
export type Metric = keyof typeof metrics;
export const contrasts = [
  {key: "duration_to_duration", label: "D − O · Duration", reason: "duration_unavailable", color: "#526ee7"},
  {key: "snapshot_vs_duration_weighting", label: "S − D · Weighting", reason: "weighting_unavailable", color: "#27a98c"},
  {key: "original_cross_estimand", label: "S − O · Cross-estimand", reason: "cross_unavailable", color: "#d59039"},
] as const;

export function params(query: Query): string {
  const result = new URLSearchParams();
  for (const name of Object.keys(query).sort()) {
    const value = query[name];
    if (value !== undefined && value !== "") result.set(name, String(value));
  }
  return result.toString();
}

// The sole conversion boundary for Plotly coordinates. Tables, exports and hover text use the wire value.
export function plotNumber(value: Scalar): number | null {
  if (value === null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function display(value: Scalar, reason?: Scalar): string {
  return value === null ? (reason ? `Unavailable (${reason})` : "Unavailable") : value;
}

export function lookup(row: Configuration, stream: Stream | undefined, metric: Metric) {
  switch (metric) {
    case "recall": return {value: stream?.events.recall ?? null, reason: stream?.events.recall_unavailable ?? null, support: stream?.events.eligible_truth};
    case "revisions": return {value: stream?.revisions.recall ?? null, reason: stream?.revisions.recall_unavailable ?? "not_published_in_this_table", support: stream?.revisions.true};
    case "coverage": return {value: row.broker.coverage, reason: "no_source_decisions", support: row.broker.decisions ?? row.broker.points?.length};
    case "consensus": return {value: row.broker.consensus_coverage, reason: "no_broker_decisions", support: row.broker.decisions ?? row.broker.points?.length};
  }
}

export function heatmap(rows: Row<Configuration>[], streamId: string, metric: Metric) {
  const axes = {x: [...new Set(rows.map(row => row.data.interval_ms))].sort((a, b) => a - b),
    y: [...new Set(rows.flatMap(row => row.data.duration_ms === undefined ? [] : [row.data.duration_ms]))].sort((a, b) => a - b)};
  const byCell = new Map<string, Row<Configuration>>();
  for (const row of rows) {
    const label = `${row.data.interval_ms}/${row.data.duration_ms}`;
    if (byCell.has(label)) throw new Error("Choose exact scenario, delays and phase before plotting.");
    byCell.set(label, row);
  }
  const cells = axes.y.map(duration => axes.x.map(interval => {
    const row = byCell.get(`${interval}/${duration}`);
    if (!row) return {value: null, text: "No matching configuration", ordinal: null};
    const stream = row.data.streams.find(item => item.session_id === streamId);
    const selected = lookup(row.data, stream, metric);
    return {value: selected.value, ordinal: row.ordinal,
      text: `${display(selected.value, selected.reason)} · support ${selected.support ?? "unavailable"}`};
  }));
  return {axes, cells};
}
