# NGSentinel — NGS Quality Control & Genomic Analysis Platform

NGSentinel takes raw sequencing reads (FASTQ), checks their quality, cleans them, checks them again,
decides with configurable and explained rules whether the data is fit for downstream analysis
(**PASS / REVIEW / FAIL**), and writes a self-contained scientific HTML report with full provenance.

```
FASTQ (R1/R2, .gz) ─► validation ─► raw QC ─► preprocessing ─► post-processing QC ─► MultiQC ─► QC decision ─► HTML report
                                     FastQC*     fastp*                 FastQC*         (optional)   rules.yaml
                                     native QC   native trimmer         native QC
```
\* used automatically when installed; otherwise the built-in engines run, and the report says which engine ran.

> Research and education tool. NGSentinel does not provide clinical or diagnostic results.

**🔗 Interactive showcase:** https://erent8.github.io/ngsentinel/ — a read-only copy of the app with real results
from the public *E. coli* run [SRR2589044](https://www.ebi.ac.uk/ena/browser/view/SRR2589044) and a synthetic demo
(works on phones too).

## Features

| Area | What it does |
|---|---|
| **Input validation** | 4-line FASTQ structure, `@`/`+` lines, sequence/quality length, A/C/G/T/N alphabet, quality range, Phred+33/+64 detection, R1/R2 read-ID pairing, gzip detection, SHA-256 checksums |
| **QC metrics** (built-in, numpy) | per-base quality (mean, quartiles, deciles), Q20/Q30, per-sequence quality, GC content vs. fitted normal (FastQC-style fractional binning), per-base N, base composition, length distribution, adapter content (Illumina Universal, small-RNA, Nextera, polyA, polyG), sequence duplication levels, overrepresented sequences |
| **Preprocessing** | fastp when available; otherwise a native trimmer implementing a documented subset of fastp's rules: 3′ adapter trimming (incl. partial adapters at the read end), `--cut_tail` sliding-window quality trimming, N-base limit, unqualified-base %, minimum length; pairs are kept only if both mates pass |
| **Before/after comparison** | every metric raw vs. processed, reads/bases retained, the reasons reads were removed — improvement *and its cost* |
| **QC decision engine** | YAML rules (`config/qc_rules.yaml`, editable in the UI) with PASS/REVIEW thresholds and direction; overall = worst rule; every rule shows value, thresholds, a plain-language explanation and why the metric matters |
| **Report** | single offline HTML file: decision, metadata, tool versions, validation, before/after table, 6 interactive charts, interpretation derived from the run's own numbers, provenance (checksums, parameters, commands, platform) |
| **History** | every run stored in SQLite with its folder (`data/runs/<run_id>/`): manifest, status, metrics JSON, decision, rules used, processed FASTQ, report |
| **Web interface** | React + TypeScript dashboard: overview, new analysis (upload or local path), live progress, results with charts, history, rule editor, tool status |

## Quick start (Windows)

Requirements: Python ≥ 3.10, Node.js ≥ 18.

```powershell
pip install -r requirements.txt
./start.ps1          # builds the UI on first run, then serves everything at http://127.0.0.1:8000
```

No data at hand? On **New analysis** click **Generate synthetic demo data**. It simulates 20,000 read pairs
whose artefacts arise from their real causes (short inserts → adapter read-through, 3′ quality decline,
degraded clusters, PCR duplicates). Synthetic results are labelled as such and are not experimental findings.

Development mode (hot reload):

```powershell
python -m uvicorn ngsentinel.api:app --app-dir backend --reload --port 8000
cd frontend; npm run dev     # http://localhost:5173 (proxies /api to :8000)
```

## External tools (optional)

| Tool | How to make it available | Used for |
|---|---|---|
| FastQC | a Java runtime (e.g. `winget install EclipseAdoptium.Temurin.21.JRE`) + the official FastQC zip unpacked to `tools/FastQC/` (or `NGSENTINEL_FASTQC`, or `fastqc` on `PATH`). On Windows NGSentinel starts FastQC through Java directly, because `run_fastqc.bat` cannot pass `--outdir`/`--threads` | raw and processed FastQC reports |
| fastp | no official Windows build — install WSL Ubuntu (`wsl --install -d Ubuntu-24.04`), then `sudo apt install fastp` (or bioconda); called via `wsl` automatically with Windows paths translated to `/mnt/...`. Or `NGSENTINEL_FASTP` | preprocessing |
| MultiQC | `pip install multiqc` | aggregated report |

Tested setup: Java 21 (Temurin) · FastQC 0.12.1 · fastp 0.23.4 (Ubuntu 24.04, WSL 2) · MultiQC 1.35.
`tools/` is git-ignored; FastQC is distributed under GPL v3 by the Babraham Institute.

Engine modes per analysis: **auto** (use tools when present), **native** (built-in only), **external**
(fail if FastQC/fastp are missing). The **Tools** page shows what was detected.

## Project layout

```
ngsentinel/
├── backend/ngsentinel/
│   ├── fastq.py       reading (plain/gzip) & validation
│   ├── metrics.py     FastQC-style QC modules (numpy, streaming, chunked)
│   ├── trimming.py    native fastp-style trimmer
│   ├── tools.py       FastQC / fastp / MultiQC detection & execution (native or WSL)
│   ├── decision.py    rule engine
│   ├── report.py      HTML report (Jinja2 + Plotly, offline)
│   ├── pipeline.py    orchestration, status, provenance manifest
│   ├── history.py     SQLite run history
│   ├── demo.py        synthetic data generator
│   └── api.py         FastAPI app (serves the built UI too)
├── backend/tests/     pytest suite (38 tests)
├── config/qc_rules.yaml
├── frontend/          React + TypeScript + Vite + Recharts
├── data/              runs, uploads, history (created at runtime, git-ignored)
└── start.ps1
```

## Tests

```powershell
cd backend; python -m pytest -q
```

## Scientific notes and limits

- Default thresholds are general starting points for short-read Illumina data, not universal standards.
  Amplicon, small-RNA and RNA-seq libraries legitimately show high duplication; adjust the rules.
- Duplication and overrepresented sequences are estimated from the first 200,000 reads per sample
  (FastQC uses a similar sampling approach). An optional read limit makes all QC metrics estimates; the UI and report say so.
- The native trimmer is **not** fastp and will not reproduce fastp's numbers exactly (e.g. no overlap-based
  adapter detection for pairs, no polyG trimming). Use fastp for production analyses.
- Phred+64 input is detected and flagged but not converted in this version.
- NGSentinel complements but does not replace wet-lab QC (library QC, instrument run metrics).

## Deployment

- **Showcase website (static, read-only):** `python scripts/export_showcase.py <out_dir> <run_id> ...` exports finished
  analyses (local paths removed) plus a single-file build of the interface; the result is served by GitHub Pages.
- **Live server:** the `Dockerfile` builds an image with FastQC, fastp and MultiQC and starts NGSentinel in public mode
  (`NGSENTINEL_PUBLIC=1`: no access to the server's disk, no rule editing or deletion, 150 MB upload limit, analyses
  removed after 24 h). It is ready for Hugging Face Spaces (`deploy/huggingface/README.md`), Render or any Docker host.

## License

[MIT](LICENSE)
