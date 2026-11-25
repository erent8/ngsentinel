"""NGSentinel analysis pipeline.

FASTQ input → validation → raw QC (native + FastQC if available) → preprocessing
(fastp if available, otherwise the native trimmer) → post-processing QC →
MultiQC (if available) → QC decision → HTML report. Every step, engine,
version, command, parameter and input checksum is written to manifest.json.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from . import __version__
from .decision import evaluate, load_rules
from .fastq import sha256_file, validate_fastq, validate_pair
from .history import History
from .metrics import compute_metrics
from .report import build_report
from .tools import detect_all, parse_fastp_json, run_fastp, run_fastqc, run_multiqc
from .trimming import TrimParams, TrimStats, trim_reads

ENGINES = ("auto", "native", "external")


@dataclass
class RunConfig:
    sample: str
    r1: str
    r2: Optional[str] = None
    engine: str = "auto"  # auto: use external tools when available; native: never; external: require them
    qc_max_reads: Optional[int] = None  # None = all reads
    validate_max_reads: Optional[int] = None
    run_fastqc: bool = True
    run_multiqc: bool = True
    threads: int = 4
    trim: TrimParams = field(default_factory=TrimParams)
    rules_file: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trim"] = self.trim.to_dict()
        return d


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_name(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s.strip())[:60].strip("._")
    return s or "sample"


def new_run_id(sample: str) -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3] + "_" + safe_name(sample)


class Status:
    """status.json inside the run folder; polled by the web UI."""

    STEPS = ["validation", "raw_qc", "preprocessing", "processed_qc", "multiqc", "decision", "report"]

    def __init__(self, run_dir: Path, cb: Optional[Callable[[dict], None]] = None):
        self.path = run_dir / "status.json"
        self.cb = cb
        self.data = {"state": "queued", "step": None, "progress": 0.0, "log": [], "error": None, "updated_at": now()}
        self._write()

    def _write(self) -> None:
        self.data["updated_at"] = now()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        # On Windows os.replace fails while another thread/process has the target open
        # (the web UI polls this file), so retry briefly instead of crashing the run.
        for attempt in range(50):
            try:
                os.replace(tmp, self.path)
                break
            except PermissionError:
                time.sleep(0.02 * (attempt + 1))
        else:
            raise PermissionError(f"could not update {self.path}")
        if self.cb:
            self.cb(self.data)

    def step(self, name: str, msg: str) -> None:
        self.data.update(state="running", step=name, progress=round(self.STEPS.index(name) / len(self.STEPS), 3))
        self.log(msg)

    def log(self, msg: str) -> None:
        self.data["log"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        self._write()

    def finish(self, state: str, error: Optional[str] = None) -> None:
        self.data.update(state=state, progress=1.0 if state == "done" else self.data["progress"], error=error)
        self._write()


class PipelineError(RuntimeError):
    pass


def run_pipeline(cfg: RunConfig, runs_root: Path, history: Optional[History] = None, run_id: Optional[str] = None,
                 status_cb: Optional[Callable[[dict], None]] = None) -> Path:
    """Execute a full analysis. Returns the run directory (also on failure)."""
    run_id = run_id or new_run_id(cfg.sample)
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    st = Status(run_dir, status_cb)
    if history and not history.get(run_id):
        history.add(run_id, cfg.sample, now(), cfg.r2 is not None, str(run_dir))
    manifest: dict = {
        "run_id": run_id, "sample": cfg.sample, "paired": cfg.r2 is not None, "ngsentinel_version": __version__,
        "started_at": now(), "finished_at": None, "config": cfg.to_dict(), "rules_file": cfg.rules_file,
        "platform": platform.platform(), "python": sys.version.split()[0],
        "inputs": [], "validation": {}, "steps": [], "commands": [], "tools_detected": {},
    }

    def save_manifest() -> None:
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def step_record(step: str, engine: str, version: Optional[str], status: str, note: str = "") -> None:
        manifest["steps"].append({"step": step, "engine": engine, "version": version, "status": status, "note": note})
        save_manifest()

    try:
        if cfg.engine not in ENGINES:
            raise PipelineError(f"unknown engine {cfg.engine!r}")
        tools = detect_all()
        manifest["tools_detected"] = {k: v.to_dict() for k, v in tools.items()}
        use_ext = cfg.engine != "native"
        if cfg.engine == "external":
            missing = [n for n in ("fastqc", "fastp") if not tools[n].available]
            if missing:
                raise PipelineError("engine 'external' requested but not available: " + ", ".join(missing))
        inputs = [Path(cfg.r1)] + ([Path(cfg.r2)] if cfg.r2 else [])
        rules = load_rules(cfg.rules_file)

        # 1. validation ---------------------------------------------------------
        st.step("validation", "Validating FASTQ input and computing checksums")
        for p in inputs:
            manifest["inputs"].append({"path": str(p), "size_bytes": p.stat().st_size if p.exists() else 0,
                                       "sha256": sha256_file(p) if p.exists() else None})
        v1 = validate_fastq(inputs[0], cfg.validate_max_reads)
        manifest["validation"]["r1"] = v1.to_dict()
        ok = v1.ok
        if cfg.r2:
            v2 = validate_fastq(inputs[1], cfg.validate_max_reads)
            manifest["validation"]["r2"] = v2.to_dict()
            ok = ok and v2.ok
            if ok:
                pr = validate_pair(inputs[0], inputs[1], cfg.validate_max_reads)
                manifest["validation"]["pair"] = pr.to_dict()
                ok = pr.ok
        step_record("Input validation", "ngsentinel-native", __version__, "ok" if ok else "failed")
        if not ok:
            raise PipelineError("input validation failed — see the validation section")
        st.log(f"Validation passed ({v1.reads_checked:,} reads in R1, encoding {v1.encoding})")

        # 2. raw QC ---------------------------------------------------------------
        st.step("raw_qc", "Computing raw-data QC metrics")
        raw = compute_metrics(inputs, cfg.qc_max_reads, progress=lambda n: None)
        (run_dir / "metrics_raw.json").write_text(json.dumps(raw), encoding="utf-8")
        step_record("Raw QC metrics", "ngsentinel-native", __version__, "ok")
        if use_ext and cfg.run_fastqc and tools["fastqc"].available:
            st.log(f"Running FastQC {tools['fastqc'].version} on raw reads")
            fr = run_fastqc(tools["fastqc"], inputs, run_dir / "fastqc_raw", cfg.threads)
            manifest["commands"].append(" ".join(fr.command))
            step_record("FastQC (raw)", "FastQC", tools["fastqc"].version, "ok" if fr.returncode == 0 else "failed",
                        "" if fr.returncode == 0 else f"exit code {fr.returncode}, see fastqc_raw/fastqc.log")
        elif cfg.run_fastqc:
            step_record("FastQC (raw)", "FastQC", None, "skipped", tools["fastqc"].note or "disabled")

        # 3. preprocessing ----------------------------------------------------------
        st.step("preprocessing", "Preprocessing reads (adapter & quality trimming, filtering)")
        pdir = run_dir / "processed"
        pdir.mkdir(exist_ok=True)
        out1 = pdir / f"{safe_name(cfg.sample)}_R1.trimmed.fastq.gz"
        out2 = pdir / f"{safe_name(cfg.sample)}_R2.trimmed.fastq.gz" if cfg.r2 else None
        if use_ext and tools["fastp"].available:
            st.log(f"Running fastp {tools['fastp'].version}")
            fp = run_fastp(tools["fastp"], inputs[0], out1, pdir / "fastp.json", pdir / "fastp.html", cfg.trim.to_dict(),
                           inputs[1] if cfg.r2 else None, out2, cfg.threads)
            manifest["commands"].append(" ".join(fp.command))
            if fp.returncode != 0:
                raise PipelineError(f"fastp failed (exit code {fp.returncode}); see processed/fastp.log")
            ts = TrimStats(pairs=cfg.r2 is not None, engine="fastp", **parse_fastp_json(pdir / "fastp.json"))
            step_record("Preprocessing", "fastp", tools["fastp"].version, "ok")
        else:
            note = "" if cfg.engine == "native" else (tools["fastp"].note or "")
            st.log("Running the NGSentinel native trimmer" + (" (fastp not available)" if cfg.engine != "native" else ""))
            ts = trim_reads(inputs[0], out1, inputs[1] if cfg.r2 else None, out2, cfg.trim)
            step_record("Preprocessing", "ngsentinel-native trimmer", __version__, "ok", note)
        trimming = ts.to_dict()
        (run_dir / "trimming.json").write_text(json.dumps(trimming, indent=1), encoding="utf-8")
        st.log(f"Preprocessing kept {ts.reads_out:,} of {ts.reads_in:,} reads ({ts.retention_pct:.1f} %)")
        outputs = [out1] + ([out2] if out2 else [])
        if ts.reads_out == 0:
            raise PipelineError("no reads remained after preprocessing; check the trimming parameters")

        # 4. processed QC ---------------------------------------------------------
        st.step("processed_qc", "Computing post-processing QC metrics")
        proc = compute_metrics(outputs, cfg.qc_max_reads)
        (run_dir / "metrics_processed.json").write_text(json.dumps(proc), encoding="utf-8")
        step_record("Post-processing QC metrics", "ngsentinel-native", __version__, "ok")
        if use_ext and cfg.run_fastqc and tools["fastqc"].available:
            fr = run_fastqc(tools["fastqc"], outputs, run_dir / "fastqc_processed", cfg.threads)
            manifest["commands"].append(" ".join(fr.command))
            step_record("FastQC (processed)", "FastQC", tools["fastqc"].version, "ok" if fr.returncode == 0 else "failed")

        # 5. MultiQC ------------------------------------------------------------------
        st.step("multiqc", "Aggregating reports")
        if use_ext and cfg.run_multiqc and tools["multiqc"].available:
            mq = run_multiqc(tools["multiqc"], run_dir, run_dir / "multiqc")
            manifest["commands"].append(" ".join(mq.command))
            step_record("MultiQC", "MultiQC", tools["multiqc"].version, "ok" if mq.returncode == 0 else "failed",
                        "" if mq.returncode == 0 else "see multiqc/multiqc.log")
        else:
            step_record("MultiQC", "MultiQC", None, "skipped", tools["multiqc"].note if cfg.run_multiqc else "disabled")

        # 6. decision -------------------------------------------------------------------
        st.step("decision", "Evaluating QC rules")
        decision = evaluate(rules, {"before": raw["summary"], "after": proc["summary"], "trimming": trimming})
        (run_dir / "decision.json").write_text(json.dumps(decision, indent=1), encoding="utf-8")
        shutil.copyfile(cfg.rules_file, run_dir / "qc_rules.used.yaml")
        step_record("QC decision", "ngsentinel rules engine", __version__, "ok")
        st.log(f"QC decision: {decision['overall']}")

        # 7. report --------------------------------------------------------------------------
        st.step("report", "Writing HTML report")
        manifest["finished_at"] = now()
        build_report(manifest, raw, proc, trimming, decision, run_dir / "report.html")
        step_record("HTML report", "ngsentinel", __version__, "ok")
        save_manifest()
        if history:
            history.update(run_id, state="done", finished_at=manifest["finished_at"], overall=decision["overall"],
                           reads_before=trimming["reads_in"], reads_after=trimming["reads_out"],
                           q30_before=raw["summary"]["q30_pct"], q30_after=proc["summary"]["q30_pct"],
                           retention_pct=trimming["retention_pct"],
                           engines={s["step"]: s["engine"] for s in manifest["steps"] if s["status"] == "ok"})
        st.finish("done")
    except Exception as e:  # noqa: BLE001 — every failure is recorded for the user
        msg = str(e) if isinstance(e, PipelineError) else f"{type(e).__name__}: {e}"
        manifest["finished_at"] = now()
        manifest["error"] = msg
        manifest["traceback"] = traceback.format_exc()
        # record the failure even if writing one of the files fails again
        for action in (save_manifest, lambda: st.log("ERROR: " + msg), lambda: st.finish("failed", msg)):
            try:
                action()
            except Exception:  # noqa: BLE001
                pass
        if history:
            history.update(run_id, state="failed", finished_at=manifest["finished_at"], error=msg)
    return run_dir
