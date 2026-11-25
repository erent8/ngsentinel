export type Status = "PASS" | "REVIEW" | "FAIL" | "N/A";
export type RunState = "queued" | "running" | "done" | "failed";

export interface RunRecord {
  run_id: string;
  sample: string;
  created_at: string;
  finished_at: string | null;
  state: RunState;
  overall: Status | null;
  paired: boolean;
  reads_before: number | null;
  reads_after: number | null;
  q30_before: number | null;
  q30_after: number | null;
  retention_pct: number | null;
  engines: Record<string, string>;
  run_dir: string;
  error: string | null;
  progress?: number;
}

export interface RunStatus {
  state: RunState;
  step: string | null;
  progress: number;
  log: string[];
  error: string | null;
  updated_at: string;
}

export interface RuleResult {
  id: string;
  label: string;
  metric: string;
  value: number | null;
  status: Status;
  pass_threshold: number;
  review_threshold: number;
  direction: "higher" | "lower";
  unit: string;
  explanation: string;
  rationale: string;
}

export interface Decision {
  overall: Exclude<Status, "N/A">;
  summary: string;
  drivers: string[];
  counts: Record<Status, number>;
  results: RuleResult[];
}

export interface Trimming {
  engine: string;
  reads_in: number;
  reads_out: number;
  bases_in: number;
  bases_out: number;
  adapter_trimmed_reads: number;
  quality_trimmed_reads: number;
  filtered_too_short: number;
  filtered_too_many_n: number;
  filtered_low_quality: number;
  retention_pct: number;
  base_retention_pct: number;
  pairs: boolean;
}

export interface Summary {
  total_reads: number;
  total_bases: number;
  min_length: number;
  max_length: number;
  mean_length: number;
  gc_pct: number;
  n_pct: number;
  mean_quality: number;
  q20_pct: number;
  q30_pct: number;
  adapter_max_pct: number;
  adapter_by_type_pct: Record<string, number>;
  duplication_pct: number;
  gc_deviation_pct: number | null;
  truncated: boolean;
  reads_sampled_for_duplication: number;
}

export interface Metrics {
  summary: Summary;
  per_base_quality: { position: number[]; mean: number[]; p10: number[]; p25: number[]; median: number[]; p75: number[]; p90: number[] };
  gc_content: { gc: number[]; pct: number[]; theoretical_pct: number[] };
  per_base_n: { position: number[]; pct: number[] };
  length_distribution: { length: number[]; count: number[] };
  adapter_content: { position: number[]; series: Record<string, number[]> };
  duplication_levels: { level: string; pct_of_reads: number }[];
  overrepresented: { sequence: string; count: number; pct: number; possible_source: string }[];
}

export interface Step {
  step: string;
  engine: string;
  version: string | null;
  status: string;
  note: string;
}

export interface Manifest {
  run_id: string;
  sample: string;
  paired: boolean;
  ngsentinel_version: string;
  started_at: string;
  finished_at: string | null;
  config: Record<string, unknown> & { trim: Record<string, unknown>; qc_max_reads: number | null; engine: string };
  inputs: { path: string; size_bytes: number; sha256: string | null }[];
  validation: Record<string, any>;
  steps: Step[];
  commands: string[];
  platform: string;
  python: string;
  error?: string;
}

export interface RunDetail {
  record: RunRecord;
  status: RunStatus | null;
  manifest: Manifest | null;
  decision: Decision | null;
  trimming: Trimming | null;
  files: { report: boolean; multiqc: boolean; fastp: boolean; fastqc: string[] };
}

export interface ToolInfo {
  name: string;
  available: boolean;
  version: string | null;
  command: string[];
  via: string;
  note: string;
}

export interface RulesResponse {
  text: string;
  custom: boolean;
  parsed: { rules: { id: string; metric: string; label: string; direction: string; pass: number; review: number; unit?: string }[] };
}
