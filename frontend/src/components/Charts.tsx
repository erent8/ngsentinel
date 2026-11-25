import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Metrics } from "../types";

const RAW = "#94a3b8";
const PROC = "#22d3ee";
const H = 290;

type Pair = { raw: Metrics; proc: Metrics | null };

const axisLabel = (value: string, angle = 0) => ({ value, angle, position: angle ? "insideLeft" : "insideBottom", offset: angle ? 12 : -4, fill: "#8197b5", fontSize: 11.5 } as const);

/** Per-base quality: mean lines + IQR areas, on FastQC-style green/amber/red bands. */
export function QualityChart({ raw, proc }: Pair) {
  const n = Math.max(raw.per_base_quality.position.length, proc?.per_base_quality.position.length ?? 0);
  const data = Array.from({ length: n }, (_, i) => {
    const r = raw.per_base_quality;
    const p = proc?.per_base_quality;
    return {
      pos: i + 1,
      rawMean: r.mean[i],
      rawIqr: r.p25[i] != null ? [r.p25[i], r.p75[i]] : undefined,
      procMean: p?.mean[i],
      procIqr: p && p.p25[i] != null ? [p.p25[i], p.p75[i]] : undefined,
    };
  });
  return (
    <ResponsiveContainer width="100%" height={H}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}>
        <ReferenceArea y1={28} y2={41} fill="#34d399" fillOpacity={0.07} />
        <ReferenceArea y1={20} y2={28} fill="#fbbf24" fillOpacity={0.08} />
        <ReferenceArea y1={0} y2={20} fill="#f87171" fillOpacity={0.07} />
        <CartesianGrid vertical={false} />
        <XAxis dataKey="pos" label={axisLabel("position in read (bp)")} tickCount={8} type="number" domain={[1, n]} />
        <YAxis domain={[0, 41]} ticks={[0, 10, 20, 28, 30, 40]} label={axisLabel("Phred", -90)} width={48} />
        <Tooltip formatter={(v: any) => (Array.isArray(v) ? `${v[0]}–${v[1]}` : Number(v).toFixed(1))} />
        <Legend verticalAlign="top" height={26} />
        <Area dataKey="rawIqr" name="raw IQR" stroke="none" fill={RAW} fillOpacity={0.16} isAnimationActive={false} legendType="none" />
        <Line dataKey="rawMean" name="raw mean" stroke={RAW} dot={false} strokeWidth={2} isAnimationActive={false} />
        {proc && <Area dataKey="procIqr" name="processed IQR" stroke="none" fill={PROC} fillOpacity={0.14} isAnimationActive={false} legendType="none" />}
        {proc && <Line dataKey="procMean" name="processed mean" stroke={PROC} dot={false} strokeWidth={2.2} isAnimationActive={false} />}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function GCChart({ raw, proc }: Pair) {
  const ref = proc ?? raw;
  const data = raw.gc_content.gc.map((g, i) => ({ gc: g, raw: raw.gc_content.pct[i], proc: proc?.gc_content.pct[i], normal: ref.gc_content.theoretical_pct[i] }));
  return (
    <ResponsiveContainer width="100%" height={H}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="gc" type="number" domain={[0, 100]} label={axisLabel("mean GC content per read (%)")} />
        <YAxis label={axisLabel("% of reads", -90)} width={48} />
        <Tooltip formatter={(v: any) => Number(v).toFixed(2) + " %"} />
        <Legend verticalAlign="top" height={26} />
        <Line dataKey="raw" name="raw" stroke={RAW} dot={false} strokeWidth={2} isAnimationActive={false} />
        {proc && <Line dataKey="proc" name="processed" stroke={PROC} dot={false} strokeWidth={2.2} isAnimationActive={false} />}
        <Line dataKey="normal" name="normal fit" stroke="#e2e8f0" strokeDasharray="5 4" dot={false} strokeWidth={1.2} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

const ADAPTER_COLORS = ["#e879f9", "#f472b6", "#a78bfa", "#fb923c", "#facc15"];

export function AdapterChart({ raw, proc }: Pair) {
  const types = Object.keys(raw.adapter_content.series).filter(
    (t) => t === "Illumina Universal Adapter" || Math.max(...raw.adapter_content.series[t], ...(proc?.adapter_content.series[t] ?? [0])) >= 0.05,
  );
  const n = raw.adapter_content.position.length;
  const data = Array.from({ length: n }, (_, i) => {
    const row: Record<string, number | undefined> = { pos: i + 1 };
    for (const t of types) {
      row[`raw:${t}`] = raw.adapter_content.series[t][i];
      if (proc) row[`proc:${t}`] = proc.adapter_content.series[t][i];
    }
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height={H}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="pos" type="number" domain={[1, n]} label={axisLabel("position in read (bp)")} />
        <YAxis label={axisLabel("% of reads (cumulative)", -90)} width={48} />
        <Tooltip formatter={(v: any) => Number(v).toFixed(2) + " %"} />
        <Legend verticalAlign="top" height={40} />
        {types.map((t, k) => (
          <Line key={`r${t}`} dataKey={`raw:${t}`} name={`raw · ${t}`} stroke={ADAPTER_COLORS[k % 5]} strokeOpacity={0.55} strokeDasharray="4 3" dot={false} strokeWidth={1.8} isAnimationActive={false} />
        ))}
        {proc &&
          types.map((t, k) => (
            <Line key={`p${t}`} dataKey={`proc:${t}`} name={`processed · ${t}`} stroke={ADAPTER_COLORS[k % 5]} dot={false} strokeWidth={2.2} isAnimationActive={false} />
          ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function LengthChart({ raw, proc }: Pair) {
  const lengths = Array.from(new Set([...raw.length_distribution.length, ...(proc?.length_distribution.length ?? [])])).sort((a, b) => a - b);
  const m = (x: Metrics | null) => new Map(x ? x.length_distribution.length.map((l, i) => [l, x.length_distribution.count[i]]) : []);
  const r = m(raw);
  const p = m(proc);
  const data = lengths.map((l) => ({ len: l, raw: r.get(l) ?? 0, proc: p.get(l) ?? 0 }));
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 16, left: 4 }} barGap={0}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="len" label={axisLabel("read length (bp)")} />
        <YAxis scale="sqrt" label={axisLabel("reads (√ scale)", -90)} width={60} />
        <Tooltip />
        <Legend verticalAlign="top" height={26} />
        <Bar dataKey="raw" name="raw" fill={RAW} isAnimationActive={false} />
        {proc && <Bar dataKey="proc" name="processed" fill={PROC} isAnimationActive={false} />}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DuplicationChart({ raw, proc }: Pair) {
  const data = raw.duplication_levels.map((d, i) => ({ level: d.level, raw: d.pct_of_reads, proc: proc?.duplication_levels[i]?.pct_of_reads }));
  return (
    <ResponsiveContainer width="100%" height={H}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="level" label={axisLabel("copies per sequence")} />
        <YAxis label={axisLabel("% of sampled reads", -90)} width={48} />
        <Tooltip formatter={(v: any) => Number(v).toFixed(2) + " %"} />
        <Legend verticalAlign="top" height={26} />
        <Bar dataKey="raw" name="raw" fill={RAW} isAnimationActive={false} />
        {proc && <Bar dataKey="proc" name="processed" fill={PROC} isAnimationActive={false} />}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function NChart({ raw, proc }: Pair) {
  const n = raw.per_base_n.position.length;
  const data = Array.from({ length: n }, (_, i) => ({ pos: i + 1, raw: raw.per_base_n.pct[i], proc: proc?.per_base_n.pct[i] }));
  return (
    <ResponsiveContainer width="100%" height={H}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 16, left: 4 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="pos" type="number" domain={[1, n]} label={axisLabel("position in read (bp)")} />
        <YAxis label={axisLabel("% N", -90)} width={48} />
        <Tooltip formatter={(v: any) => Number(v).toFixed(3) + " %"} />
        <Legend verticalAlign="top" height={26} />
        <Line dataKey="raw" name="raw" stroke={RAW} dot={false} strokeWidth={2} isAnimationActive={false} />
        {proc && <Line dataKey="proc" name="processed" stroke={PROC} dot={false} strokeWidth={2.2} isAnimationActive={false} />}
      </LineChart>
    </ResponsiveContainer>
  );
}
