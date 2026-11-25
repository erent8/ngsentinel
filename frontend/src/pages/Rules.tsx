import { useEffect, useState } from "react";
import { api } from "../api";
import { ErrorBox, PageHead } from "../components/common";
import { useData } from "../hooks";
import { STATIC } from "../config";
import { useServerConfig } from "../hooks";

export default function Rules() {
  const cfg = useServerConfig();
  const readOnly = STATIC || !!cfg?.public;
  const rules = useData(api.rules, []);
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (rules.data) setText(rules.data.text);
  }, [rules.data]);

  const save = async () => {
    setError(null);
    setSaved(false);
    try {
      await api.saveRules(text);
      await rules.refresh();
      setSaved(true);
    } catch (e) {
      setError(e);
    }
  };
  const reset = async () => {
    if (!confirm("Discard your custom rules and restore the defaults?")) return;
    setError(null);
    await api.resetRules();
    await rules.refresh();
  };
  const dirty = rules.data && text !== rules.data.text;

  return (
    <>
      <PageHead eyebrow="QC DECISION ENGINE" title="QC rules">
        {!readOnly && rules.data?.custom && (
          <button className="btn" onClick={reset}>
            Restore defaults
          </button>
        )}
        {!readOnly && (
          <button className="btn primary" onClick={save} disabled={!dirty}>
            Save rules
          </button>
        )}
      </PageHead>
      <div className="alert info" style={{ marginBottom: 14 }}>
        Each rule compares one metric with a PASS and a REVIEW threshold. The overall decision is the worst rule status. Defaults are general starting points for
        short-read Illumina data, not universal standards — adjust them to your assay. New rules apply to analyses started after saving; each run keeps a copy of
        the rules it used.
      </div>
      <ErrorBox error={rules.error || error} />
      {saved && !dirty && <div className="alert info" style={{ marginBottom: 14 }}>Rules saved.</div>}
      <div className="grid split" style={{ gridTemplateColumns: "minmax(0, 1.2fr) minmax(0, 1fr)", alignItems: "start" }}>
        <div className="card">
          <h2>
            qc_rules.yaml <span className="muted small">{rules.data?.custom ? "(custom)" : "(default)"}</span>
          </h2>
          <textarea id="rules-yaml" rows={34} value={text} spellCheck={false} readOnly={readOnly} onChange={(e) => setText(e.target.value)} />
        </div>
        <div className="card">
          <h2>Active rules</h2>
          <table>
            <thead>
              <tr>
                <th>Rule</th>
                <th>Metric</th>
                <th className="num">PASS</th>
                <th className="num">REVIEW</th>
              </tr>
            </thead>
            <tbody>
              {rules.data?.parsed.rules.map((r) => (
                <tr key={r.id}>
                  <td>{r.label}</td>
                  <td className="mono muted" style={{ fontSize: 11.5 }}>
                    {r.metric}
                  </td>
                  <td className="num mono" style={{ color: "var(--pass)" }}>
                    {r.direction === "higher" ? "≥" : "≤"} {r.pass}
                  </td>
                  <td className="num mono" style={{ color: "var(--review)" }}>
                    {r.direction === "higher" ? "≥" : "≤"} {r.review}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small" style={{ marginTop: 12 }}>
            Available metrics: <span className="mono">before.* / after.*</span> (total_reads, mean_quality, q20_pct, q30_pct, gc_pct, n_pct, adapter_max_pct,
            duplication_pct, gc_deviation_pct, mean_length) and <span className="mono">trimming.*</span> (retention_pct, base_retention_pct, reads_out).
          </p>
        </div>
      </div>
    </>
  );
}
