import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, fmtDate, fmtInt, fmtNum } from "../api";
import { ErrorBox, PageHead, StateChip, StatusChip } from "../components/common";
import { useData } from "../hooks";

export default function Runs() {
  const nav = useNavigate();
  const runs = useData(api.runs, [], 3000, (rs) => rs.some((r) => r.state === "running" || r.state === "queued"));
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const rows = (runs.data ?? []).filter(
    (r) => (!q || r.sample.toLowerCase().includes(q.toLowerCase())) && (status === "all" || r.overall === status || r.state === status),
  );
  return (
    <>
      <PageHead eyebrow="ANALYSIS HISTORY" title="All analyses">
        <Link className="btn primary" to="/new">
          ＋ New analysis
        </Link>
      </PageHead>
      <ErrorBox error={runs.error} />
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <input type="text" placeholder="Filter by sample…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 280 }} />
          <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ maxWidth: 180 }}>
            <option value="all">All</option>
            <option value="PASS">PASS</option>
            <option value="REVIEW">REVIEW</option>
            <option value="FAIL">FAIL</option>
            <option value="running">Running</option>
            <option value="failed">Errored</option>
          </select>
          <span className="muted small">{rows.length} analyses</span>
        </div>
        {rows.length === 0 ? (
          <div className="empty">{runs.loading ? "Loading…" : "No analyses match."}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Sample</th>
                <th>Run ID</th>
                <th>Started</th>
                <th>State</th>
                <th className="num">Reads in</th>
                <th className="num">Retention</th>
                <th className="num">Q30 processed</th>
                <th>Preprocessing</th>
                <th>QC</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.run_id} className="clickable" onClick={() => nav(`/runs/${r.run_id}`)}>
                  <td>
                    <b style={{ color: "var(--white)" }}>{r.sample}</b>
                    {r.error && <div className="small" style={{ color: "var(--fail)" }}>{r.error}</div>}
                  </td>
                  <td className="mono muted" style={{ fontSize: 11.5 }}>
                    {r.run_id}
                  </td>
                  <td className="small">{fmtDate(r.created_at)}</td>
                  <td>
                    <StateChip state={r.state} />
                  </td>
                  <td className="num mono">{fmtInt(r.reads_before)}</td>
                  <td className="num mono">{r.retention_pct == null ? "—" : `${fmtNum(r.retention_pct, 1)} %`}</td>
                  <td className="num mono">{r.q30_after == null ? "—" : `${fmtNum(r.q30_after, 1)} %`}</td>
                  <td className="small">{r.engines?.["Preprocessing"] ?? "—"}</td>
                  <td>
                    <StatusChip status={r.overall} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
