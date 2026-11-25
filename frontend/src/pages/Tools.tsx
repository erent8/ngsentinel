import { useState } from "react";
import { api } from "../api";
import { ErrorBox, PageHead } from "../components/common";
import { useData } from "../hooks";
import { STATIC } from "../config";

const HELP: Record<string, string> = {
  fastqc: "Needs a Java runtime. Download the FastQC zip from the Babraham Institute and unpack it to tools/FastQC (or put fastqc on PATH, or set NGSENTINEL_FASTQC).",
  fastp: "No official Windows build. Install WSL Ubuntu, then inside it: sudo apt install fastp (or bioconda). NGSentinel calls it through WSL automatically.",
  multiqc: "pip install multiqc",
  java: "Required by FastQC — e.g. Eclipse Temurin JRE 17+.",
  wsl: "Windows Subsystem for Linux: run `wsl --install -d Ubuntu-24.04` (may need administrator approval).",
};

export default function Tools() {
  const [refresh, setRefresh] = useState(0);
  const tools = useData(() => api.tools(refresh > 0), [refresh]);
  return (
    <>
      <PageHead eyebrow="ENVIRONMENT" title="Tools">
        {!STATIC && (
          <button className="btn" onClick={() => setRefresh((x) => x + 1)} disabled={tools.loading}>
            {tools.loading ? "Detecting…" : "Re-detect"}
          </button>
        )}
      </PageHead>
      <div className="alert info" style={{ marginBottom: 14 }}>
        NGSentinel always runs its built-in QC engine (FastQC-style metrics) and, when fastp is unavailable, a native trimmer implementing a documented subset of
        fastp's rules. With engine “Auto”, FastQC, fastp and MultiQC are used whenever they are installed. The report records the exact engine and version of every
        step.
        {STATIC && " The versions below are the environment the showcase results were produced with."}
      </div>
      <ErrorBox error={tools.error} />
      <div className="grid g2">
        {tools.data &&
          ["fastqc", "fastp", "multiqc", "java", "wsl"].map((k) => {
            const t = tools.data![k];
            return (
              <div key={k} className="card">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <h2 style={{ margin: 0 }}>{t.name}</h2>
                  {t.available ? <span className="chip done">{t.version ? `v${t.version}` : "available"}</span> : <span className="chip NA">not found</span>}
                </div>
                {t.available ? (
                  <p className="mono small muted">
                    {t.via} · {t.command.join(" ")}
                  </p>
                ) : (
                  <>
                    {t.note && <p className="small muted">{t.note}</p>}
                    <p className="small">{HELP[k]}</p>
                  </>
                )}
              </div>
            );
          })}
      </div>
    </>
  );
}
