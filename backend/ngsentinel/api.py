"""FastAPI backend for the NGSentinel web interface.

Run:  uvicorn ngsentinel.api:app --app-dir backend --port 8000
The built React app (frontend/dist) is served at / when present.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .decision import RulesError, parse_rules
from .demo import make_demo_pair
from .history import History
from .pipeline import RunConfig, new_run_id, run_pipeline
from .tools import detect_all
from .trimming import TrimParams

PROJECT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("NGSENTINEL_DATA", PROJECT / "data")).resolve()
RUNS = DATA / "runs"
UPLOADS = DATA / "uploads"
DEFAULT_RULES = PROJECT / "config" / "qc_rules.yaml"
USER_RULES = DATA / "qc_rules.yaml"
FASTQ_RE = re.compile(r"\.(fastq|fq)(\.gz)?$", re.IGNORECASE)

# Public mode: for a server that anyone on the internet can open (e.g. a Hugging
# Face Space). Local file paths, rule editing and deletion are disabled; uploads,
# queue length and run lifetime are limited.
PUBLIC = os.environ.get("NGSENTINEL_PUBLIC", "0") == "1"
MAX_UPLOAD_MB = int(os.environ.get("NGSENTINEL_MAX_UPLOAD_MB", "150" if PUBLIC else "0"))  # 0 = unlimited
MAX_QUEUE = int(os.environ.get("NGSENTINEL_MAX_QUEUE", "4" if PUBLIC else "1000"))
RUN_TTL_HOURS = float(os.environ.get("NGSENTINEL_RUN_TTL_HOURS", "24" if PUBLIC else "0"))  # 0 = keep forever
KEEP_PREFIX = "example_"  # example runs are never cleaned up

for d in (RUNS, UPLOADS):
    d.mkdir(parents=True, exist_ok=True)

history = History(RUNS / "history.sqlite")
# runs that were in progress when the server stopped can never finish: mark them
for _r in history.list(10_000):
    if _r["state"] in ("queued", "running"):
        history.update(_r["run_id"], state="failed", error="interrupted (server stopped during the run)")
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ngsentinel-run")
app = FastAPI(title="NGSentinel API", version=__version__)


def forbid_in_public(what: str) -> None:
    if PUBLIC:
        raise HTTPException(403, f"{what} is disabled on the public server. Run NGSentinel locally to use it.")


def cleanup_old_runs() -> None:
    """Delete finished runs and uploads older than RUN_TTL_HOURS (public mode)."""
    if RUN_TTL_HOURS <= 0:
        return
    cutoff = time.time() - RUN_TTL_HOURS * 3600
    for r in history.list(10_000):
        d = Path(r["run_dir"])
        if r["run_id"].split("_", 1)[-1].startswith(KEEP_PREFIX) or r["state"] in ("queued", "running"):
            continue
        if d.exists() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            history.delete(r["run_id"])
    for f in UPLOADS.glob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


def rules_path() -> Path:
    return USER_RULES if USER_RULES.exists() else DEFAULT_RULES


def run_dir_of(run_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
        raise HTTPException(400, "invalid run id")
    rec = history.get(run_id)
    if not rec:
        raise HTTPException(404, "run not found")
    return Path(rec["run_dir"])


def read_json(p: Path) -> Optional[dict]:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ------------------------------------------------------------------ system
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/config")
def config() -> dict:
    return {"public": PUBLIC, "max_upload_mb": MAX_UPLOAD_MB, "run_ttl_hours": RUN_TTL_HOURS, "version": __version__}


@app.get("/api/tools")
def tools(refresh: bool = False) -> dict:
    return {k: v.to_dict() for k, v in detect_all(refresh=refresh).items()}


# ------------------------------------------------------------------ rules
class RulesBody(BaseModel):
    text: str


@app.get("/api/rules")
def get_rules() -> dict:
    p = rules_path()
    text = p.read_text(encoding="utf-8")
    return {"text": text, "custom": p == USER_RULES, "parsed": parse_rules(text)}


@app.put("/api/rules")
def put_rules(body: RulesBody) -> dict:
    forbid_in_public("Editing the QC rules")
    try:
        parsed = parse_rules(body.text)
    except RulesError as e:
        raise HTTPException(422, str(e)) from e
    USER_RULES.write_text(body.text, encoding="utf-8")
    return {"text": body.text, "custom": True, "parsed": parsed}


@app.delete("/api/rules")
def reset_rules() -> dict:
    forbid_in_public("Editing the QC rules")
    USER_RULES.unlink(missing_ok=True)
    return get_rules()


# ------------------------------------------------------------------ inputs
@app.post("/api/uploads")
async def upload(file: UploadFile = File(...)) -> dict:
    name = Path(file.filename or "").name
    if not FASTQ_RE.search(name):
        raise HTTPException(422, "only .fastq, .fq, .fastq.gz or .fq.gz files are accepted")
    dest = UPLOADS / f"{uuid.uuid4().hex[:8]}_{re.sub(r'[^A-Za-z0-9._-]+', '_', name)}"
    limit = MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1 << 20):
            written += len(chunk)
            if limit and written > limit:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"file is larger than the {MAX_UPLOAD_MB} MB limit of this server")
            out.write(chunk)
    return {"path": str(dest), "name": name, "size_bytes": dest.stat().st_size}


class PathCheck(BaseModel):
    path: str


@app.post("/api/inputs/check")
def check_path(body: PathCheck) -> dict:
    forbid_in_public("Reading files from the server's disk")
    p = Path(body.path.strip().strip('"'))
    if not p.is_file():
        raise HTTPException(404, "file not found")
    if not FASTQ_RE.search(p.name):
        raise HTTPException(422, "expected a .fastq/.fq(.gz) file")
    return {"path": str(p.resolve()), "name": p.name, "size_bytes": p.stat().st_size}


@app.post("/api/demo-data")
def demo_data(pairs: int = 20000) -> dict:
    pairs = max(1000, min(pairs, 20_000 if PUBLIC else 200_000))
    d = DATA / "demo"
    p1, p2 = make_demo_pair(d, n_pairs=pairs)
    return {"r1": str(p1), "r2": str(p2), "pairs": pairs, "synthetic": True,
            "note": "Simulated reads (random reference, simulated qualities) — for demonstration only."}


# ------------------------------------------------------------------ runs
class TrimBody(BaseModel):
    trim_adapters: bool = True
    adapter_r1: str = TrimParams().adapter_r1
    adapter_r2: str = TrimParams().adapter_r2
    cut_tail: bool = True
    cut_window: int = Field(4, ge=1, le=50)
    cut_mean_quality: int = Field(20, ge=1, le=40)
    qualified_quality: int = Field(15, ge=1, le=40)
    unqualified_percent_limit: int = Field(40, ge=0, le=100)
    n_base_limit: int = Field(5, ge=0, le=1000)
    length_required: int = Field(15, ge=1, le=10000)


class RunBody(BaseModel):
    sample: str = Field(..., min_length=1, max_length=80)
    r1: str
    r2: Optional[str] = None
    engine: str = Field("auto", pattern="^(auto|native|external)$")
    qc_max_reads: Optional[int] = Field(None, ge=1000)
    run_fastqc: bool = True
    run_multiqc: bool = True
    threads: int = Field(4, ge=1, le=64)
    trim: TrimBody = TrimBody()


@app.post("/api/runs")
def start_run(body: RunBody) -> dict:
    inputs = [body.r1] + ([body.r2] if body.r2 else [])
    if PUBLIC:
        # only files uploaded to this server or the generated demo data may be analysed
        allowed = (UPLOADS.resolve(), (DATA / "demo").resolve())
        for p in inputs:
            rp = Path(p).resolve()
            if not any(a in rp.parents for a in allowed):
                raise HTTPException(403, "on the public server only uploaded files or the demo data can be analysed")
        active = sum(1 for r in history.list(200) if r["state"] in ("queued", "running"))
        if active >= MAX_QUEUE:
            raise HTTPException(429, "the server is busy; please try again in a few minutes")
        body.threads = min(body.threads, 2)
        cleanup_old_runs()
    for p in inputs:
        if not Path(p).is_file():
            raise HTTPException(422, f"input file not found: {p}")
    if body.r2 and Path(body.r1).resolve() == Path(body.r2).resolve():
        raise HTTPException(422, "R1 and R2 must be different files")
    cfg = RunConfig(sample=body.sample, r1=body.r1, r2=body.r2 or None, engine=body.engine,
                    qc_max_reads=body.qc_max_reads, run_fastqc=body.run_fastqc, run_multiqc=body.run_multiqc,
                    threads=body.threads, trim=TrimParams(**body.trim.model_dump()), rules_file=str(rules_path()))
    run_id = new_run_id(body.sample)
    from .pipeline import now

    history.add(run_id, body.sample, now(), body.r2 is not None, str(RUNS / run_id))
    def job() -> None:
        try:
            run_pipeline(cfg, RUNS, history, run_id)
        except Exception as e:  # noqa: BLE001 — last-resort guard: the run must not stay "running"
            history.update(run_id, state="failed", error=f"internal error: {e}")

    executor.submit(job)
    return {"run_id": run_id}


@app.get("/api/runs")
def list_runs() -> list[dict]:
    out = []
    for r in history.list():
        if r["state"] in ("queued", "running"):
            st = read_json(Path(r["run_dir"]) / "status.json")
            if st:
                r["state"] = st["state"] if st["state"] != "queued" else r["state"]
                r["progress"] = st.get("progress")
        out.append(r)
    return out


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    d = run_dir_of(run_id)
    rec = history.get(run_id)
    files = {
        "report": (d / "report.html").exists(),
        "multiqc": (d / "multiqc" / "multiqc_report.html").exists(),
        "fastp": (d / "processed" / "fastp.html").exists(),
        "fastqc": sorted(str(p.relative_to(d)).replace("\\", "/") for p in d.glob("fastqc_*/*_fastqc.html")),
    }
    return {"record": rec, "status": read_json(d / "status.json"), "manifest": read_json(d / "manifest.json"),
            "decision": read_json(d / "decision.json"), "trimming": read_json(d / "trimming.json"), "files": files}


@app.get("/api/runs/{run_id}/metrics/{which}")
def get_metrics(run_id: str, which: str) -> JSONResponse:
    if which not in ("raw", "processed"):
        raise HTTPException(404)
    d = run_dir_of(run_id)
    data = read_json(d / f"metrics_{which}.json")
    if data is None:
        raise HTTPException(404, "metrics not available yet")
    return JSONResponse(data)


@app.get("/api/runs/{run_id}/files/{path:path}")
def get_file(run_id: str, path: str) -> FileResponse:
    d = run_dir_of(run_id).resolve()
    target = (d / path).resolve()
    if d not in target.parents or not target.is_file():
        raise HTTPException(404, "file not found")
    if target.suffix.lower() not in (".html", ".json", ".log", ".yaml", ".txt", ".zip", ".gz"):
        raise HTTPException(403, "file type not served")
    return FileResponse(target)


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str) -> dict:
    forbid_in_public("Deleting analyses")
    d = run_dir_of(run_id)
    rec = history.get(run_id)
    if rec and rec["state"] in ("queued", "running"):
        raise HTTPException(409, "cannot delete a run that is still running")
    if d.resolve().parent == RUNS.resolve():
        shutil.rmtree(d, ignore_errors=True)
    history.delete(run_id)
    return {"deleted": run_id}


# ------------------------------------------------------------------ examples
def seed_examples() -> None:
    """On an empty public server, analyse the synthetic demo so visitors see a result
    immediately. Optionally (NGSENTINEL_SEED_ENA=<run accession>) also download a
    public ENA run, verify its MD5 checksums and analyse it."""
    if any(r["sample"].startswith(KEEP_PREFIX) for r in history.list(10_000)):
        return
    try:
        r1, r2 = make_demo_pair(DATA / "demo", n_pairs=20000)
        _submit(RunConfig(sample=KEEP_PREFIX + "SYNTHETIC_DEMO", r1=str(r1), r2=str(r2), threads=2, rules_file=str(rules_path())))
        acc = os.environ.get("NGSENTINEL_SEED_ENA", "").strip()
        if acc:
            from .ena import download_run

            files = download_run(acc, DATA / "public" / acc)
            _submit(RunConfig(sample=KEEP_PREFIX + acc, r1=str(files[0]), r2=str(files[1]) if len(files) > 1 else None,
                              threads=2, rules_file=str(rules_path())))
    except Exception as e:  # noqa: BLE001 — examples are optional
        print(f"[NGSentinel] could not seed examples: {e}")


def _submit(cfg: RunConfig) -> str:
    from .pipeline import now

    run_id = new_run_id(cfg.sample)
    history.add(run_id, cfg.sample, now(), cfg.r2 is not None, str(RUNS / run_id))
    executor.submit(run_pipeline, cfg, RUNS, history, run_id)
    return run_id


if PUBLIC:
    cleanup_old_runs()
    if os.environ.get("NGSENTINEL_SEED_EXAMPLES", "1") == "1":
        threading.Thread(target=seed_examples, daemon=True, name="ngsentinel-seed").start()


# ------------------------------------------------------------------ frontend
DIST = PROJECT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(404, "unknown API endpoint")
        f = (DIST / full_path).resolve()
        if full_path and DIST.resolve() in f.parents and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
