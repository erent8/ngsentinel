import { Link } from "react-router-dom";
import { PageHead } from "../components/common";
import { LIVE_URL, REPO_URL } from "../config";

/** Shown instead of the analysis form in the read-only showcase build. */
export default function TryIt() {
  return (
    <>
      <PageHead eyebrow="RUN YOUR OWN DATA" title="New analysis" />
      <div className="grid split" style={{ gridTemplateColumns: "minmax(0, 1.3fr) minmax(0, 1fr)", alignItems: "start" }}>
        <div className="card">
          <h2>Run NGSentinel on your computer</h2>
          <div className="steps-list">
            <div>
              <span className="n">1</span>
              <div>
                Get the code and install the dependencies (Python ≥ 3.10, Node.js ≥ 18).
                <pre className="cmd">
                  {`git clone ${REPO_URL || "<repository URL>"}\ncd ngsentinel\npip install -r requirements.txt`}
                </pre>
              </div>
            </div>
            <div>
              <span className="n">2</span>
              <div>
                Start the app. It builds the web interface on first run and opens at <span className="mono">http://127.0.0.1:8000</span>.
                <pre className="cmd">{`./start.ps1          # Windows\npython -m uvicorn ngsentinel.api:app --app-dir backend   # any OS`}</pre>
              </div>
            </div>
            <div>
              <span className="n">3</span>
              <div>Upload paired-end or single-end FASTQ (.fastq / .fastq.gz), or generate the synthetic demo dataset, and start the analysis.</div>
            </div>
            <div>
              <span className="n">4</span>
              <div>
                Optional: install FastQC (Java), fastp (Linux or WSL) and MultiQC. NGSentinel detects and uses them automatically; without them its built-in QC engine and
                trimmer run, and the report says which engine was used.
              </div>
            </div>
          </div>
        </div>
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <h2 style={{ margin: 0 }}>In this showcase</h2>
          <p className="muted" style={{ margin: 0 }}>
            This page is a read-only copy of the app. Open the analyses to see exactly what a run produces: the QC decision with explanations, before/after charts,
            preprocessing statistics, tool versions, provenance and the full HTML, FastQC, fastp and MultiQC reports.
          </p>
          <Link className="btn primary" to="/runs" style={{ justifyContent: "center" }}>
            Browse the analyses
          </Link>
          {LIVE_URL && (
            <a className="btn" href={LIVE_URL} target="_blank" rel="noreferrer" style={{ justifyContent: "center" }}>
              Open the live app to upload your own FASTQ
            </a>
          )}
          <p className="muted small" style={{ margin: 0 }}>
            Research and education tool. Not for clinical diagnosis.
          </p>
        </div>
      </div>
    </>
  );
}
