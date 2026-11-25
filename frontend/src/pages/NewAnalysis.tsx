import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtBytes, type InputFile } from "../api";
import { ErrorBox, PageHead } from "../components/common";
import { useServerConfig } from "../hooks";

type Source = "upload" | "path";

function FileInput({ label, value, onChange }: { label: string; value: InputFile | null; onChange: (f: InputFile | null) => void }) {
  const cfg = useServerConfig();
  const [source, setSource] = useState<Source>("upload");
  const [path, setPath] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [over, setOver] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  const upload = async (file: File) => {
    setError(null);
    setProgress(0);
    try {
      onChange(await api.upload(file, setProgress));
    } catch (e) {
      setError(e);
      onChange(null);
    } finally {
      setProgress(null);
    }
  };
  const check = async () => {
    setError(null);
    try {
      onChange(await api.checkPath(path));
    } catch (e) {
      setError(e);
      onChange(null);
    }
  };

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{label}</h3>
        {!cfg?.public && (
          <div className="seg">
            <button type="button" className={source === "upload" ? "on" : ""} onClick={() => setSource("upload")}>
              Upload
            </button>
            <button type="button" className={source === "path" ? "on" : ""} onClick={() => setSource("path")}>
              Local path
            </button>
          </div>
        )}
      </div>
      {source === "upload" ? (
        <div
          className={`drop${over ? " over" : ""}`}
          onClick={() => ref.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            const f = e.dataTransfer.files[0];
            if (f) upload(f);
          }}
        >
          <input ref={ref} type="file" accept=".fastq,.fq,.gz" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          {progress != null ? `Uploading… ${(progress * 100).toFixed(0)} %` : "Drop a .fastq / .fastq.gz file here or click to choose"}
          {cfg?.max_upload_mb ? <div className="small muted">max {cfg.max_upload_mb} MB per file</div> : null}
        </div>
      ) : (
        <div className="row" style={{ flexWrap: "nowrap" }}>
          <input type="text" placeholder="C:\data\sample_R1.fastq.gz" value={path} onChange={(e) => setPath(e.target.value)} />
          <button type="button" className="btn" onClick={check} disabled={!path.trim()}>
            Use
          </button>
        </div>
      )}
      {source === "path" && <div className="muted small">Large files: give the path instead of uploading — the file is read in place, never copied.</div>}
      {value && (
        <div className="row small">
          <span style={{ color: "var(--pass)" }}>✓</span>
          <span className="mono">{value.name}</span>
          <span className="muted">{fmtBytes(value.size_bytes)}</span>
          <button type="button" className="btn sm" onClick={() => onChange(null)}>
            Clear
          </button>
        </div>
      )}
      <ErrorBox error={error} />
    </div>
  );
}

const DEFAULT_TRIM = {
  trim_adapters: true,
  adapter_r1: "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA",
  adapter_r2: "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT",
  cut_tail: true,
  cut_window: 4,
  cut_mean_quality: 20,
  qualified_quality: 15,
  unqualified_percent_limit: 40,
  n_base_limit: 5,
  length_required: 15,
};

export default function NewAnalysis() {
  const nav = useNavigate();
  const [sample, setSample] = useState("");
  const [paired, setPaired] = useState(true);
  const [r1, setR1] = useState<InputFile | null>(null);
  const [r2, setR2] = useState<InputFile | null>(null);
  const [engine, setEngine] = useState("auto");
  const [limit, setLimit] = useState("");
  const [trim, setTrim] = useState(DEFAULT_TRIM);
  const [busy, setBusy] = useState(false);
  const [demoNote, setDemoNote] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const setT = (k: keyof typeof DEFAULT_TRIM, v: string | number | boolean) => setTrim((t) => ({ ...t, [k]: v }));
  const ready = sample.trim() && r1 && (!paired || r2) && !busy;

  const demo = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await api.demoData(20000);
      setSample("SYNTHETIC_DEMO");
      setPaired(true);
      setR1(await api.checkPath(d.r1));
      setR2(await api.checkPath(d.r2));
      setDemoNote(d.note);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await api.startRun({
        sample: sample.trim(),
        r1: r1!.path,
        r2: paired ? r2!.path : null,
        engine,
        qc_max_reads: limit ? Number(limit) : null,
        trim,
      });
      nav(`/runs/${run_id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  const num = (k: keyof typeof DEFAULT_TRIM, label: string, min = 0, max = 1000) => (
    <label className="field">
      {label}
      <input type="number" min={min} max={max} value={trim[k] as number} onChange={(e) => setT(k, Number(e.target.value))} />
    </label>
  );

  return (
    <>
      <PageHead eyebrow="FASTQ → QC → PREPROCESSING → QC → DECISION → REPORT" title="New analysis">
        <button className="btn" onClick={demo} disabled={busy}>
          Generate synthetic demo data
        </button>
      </PageHead>
      {demoNote && (
        <div className="alert warn" style={{ marginBottom: 14 }}>
          <b>Synthetic dataset loaded.</b> {demoNote} Results from this data are illustrative and are not experimental findings.
        </div>
      )}
      <div className="grid split" style={{ gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)", alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="card grid g2">
            <label className="field">
              Sample name
              <input type="text" value={sample} maxLength={80} onChange={(e) => setSample(e.target.value)} placeholder="e.g. SRR000001" />
            </label>
            <label className="field">
              Library layout
              <div className="seg">
                <button type="button" className={paired ? "on" : ""} onClick={() => setPaired(true)}>
                  Paired-end
                </button>
                <button type="button" className={!paired ? "on" : ""} onClick={() => setPaired(false)}>
                  Single-end
                </button>
              </div>
            </label>
          </div>
          <FileInput label={paired ? "Read 1 (R1)" : "Reads"} value={r1} onChange={setR1} />
          {paired && <FileInput label="Read 2 (R2)" value={r2} onChange={setR2} />}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <h2 style={{ margin: 0 }}>Processing</h2>
            <label className="field">
              Engine
              <select value={engine} onChange={(e) => setEngine(e.target.value)}>
                <option value="auto">Auto — FastQC / fastp / MultiQC when installed, otherwise built-in</option>
                <option value="native">Built-in only (NGSentinel QC + native trimmer)</option>
                <option value="external">External tools required (fail if missing)</option>
              </select>
            </label>
            <label className="field">
              QC read limit per file (blank = all reads)
              <input type="number" min={1000} placeholder="all reads" value={limit} onChange={(e) => setLimit(e.target.value)} />
            </label>
            <details>
              <summary>Trimming &amp; filtering parameters (fastp-compatible)</summary>
              <div className="grid g2" style={{ marginTop: 12 }}>
                <label className="check">
                  <input type="checkbox" checked={trim.trim_adapters} onChange={(e) => setT("trim_adapters", e.target.checked)} /> Adapter trimming
                </label>
                <label className="check">
                  <input type="checkbox" checked={trim.cut_tail} onChange={(e) => setT("cut_tail", e.target.checked)} /> 3′ quality trimming
                </label>
                {num("cut_window", "Window size (bp)", 1, 50)}
                {num("cut_mean_quality", "Window mean quality", 1, 40)}
                {num("qualified_quality", "Qualified base quality", 1, 40)}
                {num("unqualified_percent_limit", "Max unqualified bases (%)", 0, 100)}
                {num("n_base_limit", "Max N bases per read", 0, 1000)}
                {num("length_required", "Minimum length (bp)", 1, 10000)}
              </div>
              <label className="field" style={{ marginTop: 10 }}>
                Adapter R1
                <input type="text" className="mono" value={trim.adapter_r1} onChange={(e) => setT("adapter_r1", e.target.value.toUpperCase())} />
              </label>
              <label className="field" style={{ marginTop: 10 }}>
                Adapter R2
                <input type="text" className="mono" value={trim.adapter_r2} onChange={(e) => setT("adapter_r2", e.target.value.toUpperCase())} />
              </label>
            </details>
          </div>
          <ErrorBox error={error} />
          <button className="btn primary" style={{ justifyContent: "center", padding: 12 }} onClick={start} disabled={!ready}>
            {busy ? "Working…" : "Start analysis"}
          </button>
          <p className="muted small">QC thresholds are configured on the QC rules page. NGSentinel is a research tool; it does not produce clinical results.</p>
        </div>
      </div>
    </>
  );
}
