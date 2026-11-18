export type Scalar = string | null;
export type Data = Record<string, unknown>;
export type Query = Record<string, string | number | undefined>;
export type Family = "p1" | "p2" | "p21";

export interface Artifact { sha256: string; bytes: number; classification: string }
export interface Dataset {
  id: Family; classification: string; declared_code_sha: string; manifest_sha256: Scalar;
  verification: string; experiment: string; scenarios: string[]; row_count: number | null;
  metric_versions: string[]; artifacts: Record<string, Artifact>;
}
export interface Row<T> { ordinal: number; data: T }
export interface Provenance { dataset: Family; table: string; source_experiment: string; artifact: string;
  artifact_sha256: string; manifest_sha256: Scalar; metric_versions: string[]; classification: string }
export interface Page<T> extends Provenance {
  filters: Query; total: number; offset: number; limit: number; rows: Row<T>[]
}
export interface EventStats {
  eligible_truth: number; detected: number; missed: number; false_detections: number;
  sample_left_censored: number; sample_right_censored: number; recall: Scalar; recall_unavailable: Scalar;
}
export interface Tail {
  oracle_duration: Scalar; sampled_duration: Scalar; sampled_snapshot: Scalar;
  duration_to_duration: Scalar; snapshot_vs_duration_weighting: Scalar; original_cross_estimand: Scalar;
  duration_unavailable: Scalar; weighting_unavailable: Scalar; cross_unavailable: Scalar;
}
export interface Stream {
  source_id: string; session_id: string; events: EventStats; coverage: Scalar; missing_ns: string;
  eligible_polls?: number; available_polls?: number; total_polls: number;
  revisions: { recall?: Scalar; matched: number; true: number; recall_unavailable?: Scalar };
  tails?: Record<"p95" | "p99", Tail>;
}
export interface Configuration {
  scenario: string; interval_ms: number; tolerance_ms?: number; phase_percent: number;
  duration_ms?: number; transport_ms?: number; processing_ms?: number; input_sha256?: string;
  streams: Stream[]; broker: {coverage: Scalar; consensus_coverage: Scalar; tolerance_ms?: number; consensus_points: number; pairwise_points: number; decisions?: number; points?: unknown[]; unmatched?: number; unmatched_slots?: number};
}
export interface HistoryRow { event_ns: string; truth_exclusion: Scalar; arrival: Quote }
export interface Quote { received_wall_ns: string; bid_text: Scalar; ask_text: Scalar; instrument_spec_version: string }
export interface Counterexample {
  id: string; interval_ms: number; phase_percent: number; sample_sha256: string; tail_percentile: number;
  quiet: TruthMember; hidden: TruthMember; shared_sample: {stream: {observations: Quote[]}};
}
interface TruthMember { episodes: number; oracle_tail: Scalar; truth_sha256: string; truth: {events: HistoryRow[]} }
export interface Evidence {
  version: string; research_id: string; code_sha: string; metric_versions: string[]; question: string;
  inputs: Data[]; findings: Claim[]; candidate_explanations: Claim[];
  clock_assumptions: string[]; limitations: string[]; falsifiers: string[];
}
interface Claim {status: string; statement: string; value: string | number | null; unit: Scalar}
