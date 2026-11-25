import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, fmtBytes, fmtDate, fmtInt, fmtNum } from "../api";
import { AdapterChart, DuplicationChart, GCChart, LengthChart, NChart, QualityChart } from "../components/Charts";
import { ErrorBox, Kpi, PageHead, StateChip, StatusChip } from "../components/common";
import { useData, useServerConfig } from "../hooks";
import { STATIC } from "../config";
import type { Metrics, RuleResult, RunDetail, Summary } from "../types";

const STEPS = ["validation", "raw_qc", "preprocessing", "processed_qc", "multiqc", "decision", "report"];
const STEP_LABEL: Record<string, string> = {
  validation: "Validation",
  raw_qc: "Raw QC",
  preprocessing: "Preprocessing",
  processed_qc: "Post-processing QC",
  multiqc: "MultiQC",
  decision: "QC decision",
  report: "Report",
};

const ROWS: [keyof Summary, string, number][] = [
  ["total_reads", "Total reads", 0],
  ["total_bases", "Total bases", 0],
  ["mean_length", "Mean read length (bp)", 1],
  ["mean_quality", "Mean base quality (Phred)", 2],
  ["q20_pct", "Bases ≥ Q20 (%)", 2],
  ["q30_pct", "Bases ≥ Q30 (%)", 2],
  ["gc_pct", "GC content (%)", 2],
  ["n_pct", "N bases (%)", 3],
  ["adapter_max_pct", "Max adapter content (%)", 2],
  ["duplication_pct", "Duplicate reads, sampled (%)", 2],
  ["gc_deviation_pct", "GC deviation from normal (%)", 2],
];

const fmtVal = (v: number | null | undefined, d: number) => (v == null ? "—" : d === 0 ? fmtInt(v) : fmtNum(v, d));

function RuleCard({ r }: { r: RuleResult }) {
  const col = r.status === "PASS" ? "var(--pass)" : r.status === "REVIEW" ? "var(--review)" : r.status === "FAIL" ? "var(--fail)" : "var(--na)";
  return (
    <div className="rule" style={{ borderColor: r.status === "PASS" || r.status === "N/A" ? undefined : col }}>
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "nowrap" }}>
        <b style={{ color: "var(--white)", fontSize: 13.5 }}>{r.label}</b>
        <StatusChip status={r.status} />
      </div>
      <div className="val" style={{ color: col }}>
        {r.value == null ? "—" : Math.abs(r.value) >= 1000 ? fmtInt(r.value) : fmtNum(r.value, 2)}
        <span className="muted" style={{ fontSize: 13, fontWeight: 500 }}>
          {r.value == null ? "" : r.unit}
        </span>
      </div>
      <div className="mono muted" style={{ fontSize: 11.5 }}>
        PASS {r.direction === "higher" ? "≥" : "≤"} {r.pass_threshold}
        {r.unit} · REVIEW {r.direction === "higher" ? "≥" : "≤"} {r.review_threshold}
        {r.unit}
      </div>
      <div className="small">{r.explanation}</div>
      <div className="small muted">
        <b>Why it matters:</b> {r.rationale}
      </div>
    </div>
  );
}

function Progress({ d }: { d: RunDetail }) {
  const st = d.status;
  if (!st) return null;
  const idx = st.step ? STEPS.indexOf(st.step) : -1;
  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 14 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>{st.state === "failed" ? "Analysis failed" : "Analysis in progress"}</h2>
        <span className="mono muted">{Math.round((st.progress ?? 0) * 100)} %</span>
      </div>
      <div className="progress">
        <div style={{ width: `${(st.progress ?? 0) * 100}%`, background: st.state === "failed" ? "var(--fail)" : undefined }} />
      </div>
      <div className="steps">
        {STEPS.map((s, i) => (
          <span key={s} className={i < idx || st.state === "done" ? "done" : i === idx ? "now" : ""}>
            {STEP_LABEL[s]}
          </span>
        ))}
      </div>
      {st.error && <div className="alert err">{st.error}</div>}
      <div className="log">{st.log.join("\n")}</div>
    </div>
  );
}

export default function RunDetailPage() {
  const { id = "" } = useParams();
  const cfg = useServerConfig();
  const nav = useNavigate();
  const run = useData(() => api.run(id), [id], 1500, (d) => !d.status || d.status.state === "running" || d.status.state === "queued");
  const [raw, setRaw] = useState<Metrics | null>(null);
  const [proc, setProc] = useState<Metrics | null>(null);
  const [tab, setTab] = useState("quality");
  const [err, setErr] = useState<unknown>(null);
  const d = run.data;
  const done = d?.status?.state === "done";

  useEffect(() => {
    if (!done) return;
    Promise.all([api.metrics(id, "raw"), api.metrics(id, "processed")])
      .then(([a, b]) => {
        setRaw(a);
        setProc(b);
      })
      .catch(setErr);
  }, [id, done]);

  if (run.error) return <ErrorBox error={run.error} />;
  if (!d) return <div className="muted">Loading…</div>;
  const m = d.manifest;
  const dec = d.decision;
  const t = d.trimming;
  const synthetic = m?.inputs.some((i) => /SYNTHETIC/i.test(i.path)) ?? false;

  const remove = async () => {
    if (!confirm(`Delete analysis "${d.record.sample}" and all its output files? This cannot be undone.`)) return;
    try {
      await api.deleteRun(id);
      nav("/runs");
    } catch (e) {
      setErr(e);
    }
  };

  return (
    <>
      <PageHead
        eyebrow={`RUN ${d.record.run_id}`}
        title={
          <span className="row" style={{ gap: 12 }}>
            {d.record.sample} <StateChip state={d.status?.state ?? d.record.state} />
            {synthetic && <span className="tag-synth">SYNTHETIC DATA</span>}
          </span>
        }
      >
        {d.files.report && (
          <a className="btn primary" href={api.fileUrl(id, "report.html")} target="_blank" rel="noreferrer">
            Open HTML report
          </a>
        )}
        {d.files.multiqc && (
          <a className="btn" href={api.fileUrl(id, "multiqc/multiqc_report.html")} target="_blank" rel="noreferrer">
            MultiQC
          </a>
        )}
        {d.files.fastp && (
          <a className="btn" href={api.fileUrl(id, "processed/fastp.html")} target="_blank" rel="noreferrer">
            fastp
          </a>
        )}
        {!STATIC && cfg && !cfg.public && (d.status?.state === "done" || d.status?.state === "failed") && (
          <button className="btn danger" onClick={remove}>
            Delete
          </button>
        )}
      </PageHead>
      <ErrorBox error={err} />
      {!done && <Progress d={d} />}
      {d.status?.state === "failed" && m?.validation && (
        <div className="card">
          <h2>Validation details</h2>
          {Object.entries(m.validation).map(([k, v]: [string, any]) =>
            v ? (
              <div key={k} className="small" style={{ marginBottom: 8 }}>
                <b>{k.toUpperCase()}</b> {v.ok ? "✓ valid" : "✕ invalid"}
                {(v.errors ?? []).map((e: string) => (
                  <div key={e} style={{ color: "var(--fail)" }}>
                    {e}
                  </div>
                ))}
              </div>
            ) : null,
          )}
        </div>
      )}

      {done && dec && t && m && (
        <>
          <div className="card" style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 14, flexWrap: "wrap" }}>
            <StatusChip status={dec.overall} big />
            <div style={{ flex: "1 1 240px", minWidth: 0 }}>
              <div style={{ color: "var(--white)", fontWeight: 600, fontSize: 15 }}>QC decision</div>
              <div className="muted">{dec.summary}</div>
            </div>
            <div className="row small mono">
              <span style={{ color: "var(--pass)" }}>{dec.counts.PASS} PASS</span>
              <span style={{ color: "var(--review)" }}>{dec.counts.REVIEW} REVIEW</span>
              <span style={{ color: "var(--fail)" }}>{dec.counts.FAIL} FAIL</span>
            </div>
          </div>
          <div className="grid g4" style={{ marginBottom: 14 }}>
            <Kpi label="Reads in → out" value={fmtInt(t.reads_out)} sub={`of ${fmtInt(t.reads_in)} · ${fmtInt(t.reads_in - t.reads_out)} removed`} />
            <Kpi label="Read retention" value={`${t.retention_pct.toFixed(1)} %`} sub={`bases retained ${t.base_retention_pct.toFixed(1)} %`} />
            <Kpi label="Q30 raw → processed" value={`${fmtNum(raw?.summary.q30_pct, 1)} → ${fmtNum(proc?.summary.q30_pct, 1)}`} sub="% of bases ≥ Q30" />
            <Kpi label="Adapter raw → processed" value={`${fmtNum(raw?.summary.adapter_max_pct, 1)} → ${fmtNum(proc?.summary.adapter_max_pct, 2)}`} sub="% of reads, max over adapter types" />
          </div>

          <div className="card" style={{ marginBottom: 14 }}>
            <h2>Rule evaluation</h2>
            <div className="grid g3">{dec.results.map((r) => <RuleCard key={r.id} r={r} />)}</div>
          </div>

          {raw && proc && (
            <div className="card" style={{ marginBottom: 14 }}>
              <div className="tabs">
                {[
                  ["quality", "Per-base quality"],
                  ["gc", "GC content"],
                  ["adapter", "Adapter content"],
                  ["length", "Read length"],
                  ["dup", "Duplication"],
                  ["n", "N content"],
                ].map(([k, l]) => (
                  <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
                    {l}
                  </button>
                ))}
              </div>
              {tab === "quality" && <QualityChart raw={raw} proc={proc} />}
              {tab === "gc" && <GCChart raw={raw} proc={proc} />}
              {tab === "adapter" && <AdapterChart raw={raw} proc={proc} />}
              {tab === "length" && <LengthChart raw={raw} proc={proc} />}
              {tab === "dup" && <DuplicationChart raw={raw} proc={proc} />}
              {tab === "n" && <NChart raw={raw} proc={proc} />}
              {raw.summary.truncated && <div className="alert info small">QC metrics were computed on a read subset (read limit) and are estimates.</div>}
            </div>
          )}

          <div className="grid g2" style={{ marginBottom: 14, alignItems: "start" }}>
            <div className="card">
              <h2>Before / after preprocessing</h2>
              {raw && proc && (
                <table>
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th className="num">Raw</th>
                      <th className="num">Processed</th>
                      <th className="num">Δ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ROWS.map(([k, label, dp]) => {
                      const a = raw.summary[k] as number | null;
                      const b = proc.summary[k] as number | null;
                      const delta = a != null && b != null ? b - a : null;
                      return (
                        <tr key={k}>
                          <td>{label}</td>
                          <td className="num mono">{fmtVal(a, dp)}</td>
                          <td className="num mono">{fmtVal(b, dp)}</td>
                          <td className="num mono muted">{delta == null ? "—" : (delta > 0 ? "+" : "") + fmtVal(delta, dp)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
            <div className="card">
              <h2>Preprocessing — {t.engine}</h2>
              <table>
                <tbody>
                  {[
                    ["Reads in", t.reads_in],
                    ["Reads out", t.reads_out],
                    ["Adapter-trimmed reads", t.adapter_trimmed_reads],
                    ["Quality-trimmed reads", t.quality_trimmed_reads],
                    ["Removed: too short", t.filtered_too_short],
                    ["Removed: too many N", t.filtered_too_many_n],
                    ["Removed: low quality", t.filtered_low_quality],
                  ].map(([k, v]) => (
                    <tr key={k as string}>
                      <td>{k}</td>
                      <td className="num mono">{fmtInt(v as number)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {t.pairs && <p className="muted small">Paired-end: a pair is removed when either mate fails a filter.</p>}
            </div>
          </div>

          <div className="grid g2" style={{ alignItems: "start" }}>
            <div className="card">
              <h2>Tools &amp; engines</h2>
              <table>
                <thead>
                  <tr>
                    <th>Step</th>
                    <th>Engine</th>
                    <th>Version</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {m.steps.map((s, i) => (
                    <tr key={i}>
                      <td>{s.step}</td>
                      <td>{s.engine}</td>
                      <td className="mono">{s.version ?? "—"}</td>
                      <td>
                        {s.status}
                        {s.note && <div className="muted small">{s.note}</div>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {d.files.fastqc.length > 0 && (
                <div className="row small" style={{ marginTop: 10 }}>
                  FastQC reports:
                  {d.files.fastqc.map((f) => (
                    <a key={f} href={api.fileUrl(id, f)} target="_blank" rel="noreferrer" className="mono">
                      {f.split("/").pop()}
                    </a>
                  ))}
                </div>
              )}
            </div>
            <div className="card">
              <h2>Provenance</h2>
              <table>
                <tbody>
                  <tr>
                    <td>Started / finished</td>
                    <td className="small">
                      {fmtDate(m.started_at)} → {fmtDate(m.finished_at)}
                    </td>
                  </tr>
                  {m.inputs.map((i) => (
                    <tr key={i.path}>
                      <td className="mono small" style={{ wordBreak: "break-all" }}>
                        {i.path.split(/[\\/]/).pop()} <span className="muted">({fmtBytes(i.size_bytes)})</span>
                      </td>
                      <td className="mono" style={{ fontSize: 11, wordBreak: "break-all" }}>
                        sha256 {i.sha256}
                      </td>
                    </tr>
                  ))}
                  <tr>
                    <td>Engine mode</td>
                    <td className="mono">{m.config.engine}</td>
                  </tr>
                  <tr>
                    <td>Platform</td>
                    <td className="small">
                      {m.platform} · Python {m.python} · NGSentinel {m.ngsentinel_version}
                    </td>
                  </tr>
                </tbody>
              </table>
              <details style={{ marginTop: 10 }}>
                <summary>Parameters</summary>
                <pre className="log">{JSON.stringify(m.config, null, 2)}</pre>
              </details>
              <details style={{ marginTop: 8 }}>
                <summary>Pipeline log</summary>
                <pre className="log">{d.status?.log.join("\n")}</pre>
              </details>
            </div>
          </div>
        </>
      )}
    </>
  );
}
