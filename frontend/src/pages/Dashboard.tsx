import { Link, useNavigate } from "react-router-dom";
import { api, fmtDate, fmtInt, fmtNum } from "../api";
import { ErrorBox, Kpi, PageHead, StateChip, StatusChip } from "../components/common";
import { useData } from "../hooks";

export default function Dashboard() {
  const nav = useNavigate();
  const runs = useData(api.runs, [], 3000, (rs) => rs.some((r) => r.state === "running" || r.state === "queued"));
  const tools = useData(() => api.tools(), []);
  const rs = runs.data ?? [];
  const done = rs.filter((r) => r.state === "done");
  const count = (s: string) => done.filter((r) => r.overall === s).length;
  const reads = done.reduce((a, r) => a + (r.reads_before ?? 0), 0);
  const avgRet = done.length ? done.reduce((a, r) => a + (r.retention_pct ?? 0), 0) / done.length : null;

  return (
    <>
      <PageHead eyebrow="OVERVIEW" title="Dashboard">
        <Link className="btn primary" to="/new">
          ＋ New analysis
        </Link>
      </PageHead>
      <ErrorBox error={runs.error} />
      <div className="grid g5" style={{ marginBottom: 14 }}>
        <Kpi label="Analyses" value={rs.length} sub={`${done.length} completed`} />
        <Kpi label="PASS" value={count("PASS")} color="var(--pass)" />
        <Kpi label="REVIEW" value={count("REVIEW")} color="var(--review)" />
        <Kpi label="FAIL" value={count("FAIL")} color="var(--fail)" />
        <Kpi label="Reads processed" value={fmtInt(reads)} sub={avgRet != null ? `mean retention ${avgRet.toFixed(1)} %` : "—"} />
      </div>
      <div className="grid split" style={{ gridTemplateColumns: "minmax(0, 2.2fr) minmax(0, 1fr)" }}>
        <div className="card">
          <h2>Recent analyses</h2>
          {rs.length === 0 && !runs.loading ? (
            <div className="empty">
              No analyses yet. <Link to="/new">Start one</Link> — you can use your own FASTQ files or generate a synthetic demo dataset.
            </div>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Sample</th>
                  <th>Started</th>
                  <th>State</th>
                  <th className="num">Reads in → out</th>
                  <th className="num">Q30 raw → processed</th>
                  <th>QC</th>
                </tr>
              </thead>
              <tbody>
                {rs.slice(0, 8).map((r) => (
                  <tr key={r.run_id} className="clickable" onClick={() => nav(`/runs/${r.run_id}`)}>
                    <td>
                      <b style={{ color: "var(--white)" }}>{r.sample}</b>
                      <div className="muted small">{r.paired ? "paired-end" : "single-end"}</div>
                    </td>
                    <td className="small">{fmtDate(r.created_at)}</td>
                    <td>
                      <StateChip state={r.state} />
                    </td>
                    <td className="num mono">
                      {fmtInt(r.reads_before)} → {fmtInt(r.reads_after)}
                    </td>
                    <td className="num mono">
                      {fmtNum(r.q30_before, 1)} → {fmtNum(r.q30_after, 1)} %
                    </td>
                    <td>
                      <StatusChip status={r.overall} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="card">
          <h2>Pipeline tools</h2>
          <ErrorBox error={tools.error} />
          {tools.data &&
            ["fastqc", "fastp", "multiqc", "java", "wsl"].map((k) => {
              const t = tools.data![k];
              return (
                <div key={k} className="row" style={{ justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
                  <span>{t.name}</span>
                  {t.available ? (
                    <span className="chip done">{t.version ? `v${t.version}` : "available"}</span>
                  ) : (
                    <span className="chip NA">not found</span>
                  )}
                </div>
              );
            })}
          {tools.loading && <div className="muted">Detecting tools…</div>}
          <p className="muted small" style={{ marginTop: 12 }}>
            When FastQC/fastp/MultiQC are missing, NGSentinel uses its built-in QC engine and native trimmer. Every report states which engine ran.{" "}
            <Link to="/tools">Details</Link>
          </p>
        </div>
      </div>
    </>
  );
}
