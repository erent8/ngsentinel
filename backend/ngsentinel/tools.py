"""Detection and execution of external bioinformatics tools.

FastQC (Java), fastp (native Linux/macOS binary; on Windows via WSL) and MultiQC
(Python) are optional. NGSentinel records exactly which tool and version ran.
Tool locations can be overridden with environment variables:
  NGSENTINEL_FASTQC   path to `fastqc` / `run_fastqc.bat`
  NGSENTINEL_FASTP    path to `fastp`
  NGSENTINEL_MULTIQC  path to `multiqc`
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

IS_WINDOWS = os.name == "nt"
PROJECT_TOOLS = Path(__file__).resolve().parents[2] / "tools"
FASTQC_MAIN = "uk.ac.babraham.FastQC.FastQCApplication"


@dataclass
class ToolInfo:
    name: str
    available: bool = False
    version: Optional[str] = None
    command: list[str] = field(default_factory=list)
    via: str = ""  # "native", "wsl", "python-module"
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def _version(text: str) -> Optional[str]:
    m = re.search(r"v?(\d+\.\d+(?:\.\d+)?)", text)
    return m.group(1) if m else None


@lru_cache(maxsize=1)
def wsl_available() -> bool:
    if not IS_WINDOWS or not shutil.which("wsl"):
        return False
    code, out = _run(["wsl", "-e", "true"], timeout=20)
    return code == 0


def find_java() -> Optional[str]:
    """java on PATH, in JAVA_HOME, or in common Windows install folders (a fresh
    install is not on the PATH of an already running process)."""
    exe = shutil.which("java")
    if exe:
        return exe
    cands = []
    if os.environ.get("JAVA_HOME"):
        cands.append(Path(os.environ["JAVA_HOME"]) / "bin" / ("java.exe" if IS_WINDOWS else "java"))
    if IS_WINDOWS:
        for base in (r"C:\Program Files\Eclipse Adoptium", r"C:\Program Files\Java", r"C:\Program Files\Microsoft",
                     r"C:\Program Files\Zulu", r"C:\Program Files\Amazon Corretto"):
            cands += sorted(Path(base).glob("*/bin/java.exe"), reverse=True)
    return next((str(c) for c in cands if c.is_file()), None)


def find_fastqc_dir() -> Optional[Path]:
    """A FastQC distribution folder (contains uk/ classes or the jar files)."""
    env = os.environ.get("NGSENTINEL_FASTQC")
    cands = []
    if env:
        e = Path(env)
        cands.append(e if e.is_dir() else e.parent)
    cands.append(PROJECT_TOOLS / "FastQC")
    for c in cands:
        if (c / "uk" / "ac" / "babraham" / "FastQC").is_dir() or (c / "fastqc").is_file() and (c / "htsjdk.jar").is_file():
            return c
    return None


def detect_java() -> ToolInfo:
    t = ToolInfo("java")
    exe = find_java()
    if exe:
        code, out = _run([exe, "-version"])
        t.available = code == 0
        t.version = _version(out)
        t.command = [exe]
        t.via = "native"
    else:
        t.note = "Java runtime not found (required by FastQC)."
    return t


def detect_fastqc() -> ToolInfo:
    t = ToolInfo("FastQC")
    # 1) a FastQC folder run directly with Java (works on Windows, where the .bat
    #    launcher cannot pass --outdir/--threads)
    d = find_fastqc_dir()
    java = find_java()
    if d and java:
        sep = ";" if IS_WINDOWS else ":"
        cp = sep.join([str(d)] + [str(j) for j in sorted(d.glob("*.jar"))])
        cmd = [java, "-Xmx1g", "-Djava.awt.headless=true", "-cp", cp]
        code, out = _run(cmd + ["-Dfastqc.show_version=true", FASTQC_MAIN], timeout=60)
        if code == 0 and "FastQC" in out:
            t.available, t.version, t.command, t.via = True, _version(out), cmd, "java"
            return t
        t.note = f"FastQC found in {d} but did not start: {out.strip()[:200]}"
    elif d and not java:
        t.note = f"FastQC found in {d} but no Java runtime was found."
    cand = (os.environ.get("NGSENTINEL_FASTQC") if os.environ.get("NGSENTINEL_FASTQC", "").endswith(("fastqc", ".pl")) else None)         or shutil.which("fastqc")
    if cand and not (IS_WINDOWS and cand.lower().endswith(".bat")):
        cmd = [cand]
        if cand.lower().endswith(".pl") or (not IS_WINDOWS and not os.access(cand, os.X_OK)):
            cmd = ["perl", cand]
        code, out = _run(cmd + ["--version"], timeout=60)
        if code == 0:
            t.available, t.version, t.command, t.via = True, _version(out), cmd, "native"
            return t
        t.note = f"FastQC found at {cand} but did not run: {out.strip()[:200]}"
    if wsl_available():
        code, out = _run(["wsl", "fastqc", "--version"], timeout=60)
        if code == 0:
            t.available, t.version, t.command, t.via = True, _version(out), ["wsl", "fastqc"], "wsl"
            return t
    if not t.note:
        t.note = "FastQC not found. Install Java + FastQC and add it to PATH (or set NGSENTINEL_FASTQC)."
    return t


def detect_fastp() -> ToolInfo:
    t = ToolInfo("fastp")
    cand = os.environ.get("NGSENTINEL_FASTP") or shutil.which("fastp")
    if cand:
        code, out = _run([cand, "--version"])
        if code == 0:
            t.available, t.version, t.command, t.via = True, _version(out), [cand], "native"
            return t
    if wsl_available():
        code, out = _run(["wsl", "fastp", "--version"])
        if code == 0:
            t.available, t.version, t.command, t.via = True, _version(out), ["wsl", "fastp"], "wsl"
            return t
    t.note = (
        "fastp not found. On Windows install it inside WSL (e.g. `sudo apt install fastp` or `conda install -c bioconda fastp`). "
        "The NGSentinel native trimmer is used instead."
    )
    return t


def detect_multiqc() -> ToolInfo:
    t = ToolInfo("MultiQC")
    cand = os.environ.get("NGSENTINEL_MULTIQC") or shutil.which("multiqc")
    if cand:
        code, out = _run([cand, "--version"], timeout=120)
        if code == 0:
            t.available, t.version, t.command, t.via = True, _version(out), [cand], "native"
            return t
    code, out = _run([sys.executable, "-m", "multiqc", "--version"], timeout=120)
    if code == 0:
        t.available, t.version, t.command, t.via = True, _version(out), [sys.executable, "-m", "multiqc"], "python-module"
        return t
    t.note = "MultiQC not found. Install with `pip install multiqc`."
    return t


def detect_all(refresh: bool = False) -> dict[str, ToolInfo]:
    if refresh:
        _cache.clear()
        wsl_available.cache_clear()
    if not _cache:
        _cache.update({"java": detect_java(), "fastqc": detect_fastqc(), "fastp": detect_fastp(), "multiqc": detect_multiqc()})
        _cache["wsl"] = ToolInfo("WSL", available=wsl_available(), via="native" if wsl_available() else "",
                                 note="" if wsl_available() else "No WSL distribution installed.")
    return dict(_cache)


_cache: dict[str, ToolInfo] = {}


# ----------------------------------------------------------------- execution
def to_tool_path(path: str | Path, tool: ToolInfo) -> str:
    """Translate a Windows path for tools running inside WSL."""
    p = str(Path(path).resolve())
    if tool.via != "wsl":
        return p
    m = re.match(r"^([A-Za-z]):\\(.*)$", p)
    if not m:
        return p
    return f"/mnt/{m.group(1).lower()}/" + m.group(2).replace("\\", "/")


@dataclass
class ToolRun:
    tool: str
    version: Optional[str]
    command: list[str]
    returncode: int
    log_file: str

    def to_dict(self) -> dict:
        return asdict(self)


def run_tool(tool: ToolInfo, args: list[str], log_file: Path, timeout: int = 6 * 3600) -> ToolRun:
    cmd = tool.command + args
    with open(log_file, "w", encoding="utf-8", errors="replace") as log:
        log.write("$ " + " ".join(cmd) + "\n\n")
        log.flush()
        try:
            p = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            code = p.returncode
        except (OSError, subprocess.TimeoutExpired) as e:
            log.write(f"\n[NGSentinel] failed to run: {e}\n")
            code = -1
    return ToolRun(tool.name, tool.version, cmd, code, str(log_file))


def run_fastqc(tool: ToolInfo, files: list[Path], outdir: Path, threads: int = 2) -> ToolRun:
    outdir.mkdir(parents=True, exist_ok=True)
    if tool.via == "java":
        args = [f"-Dfastqc.output_dir={outdir.resolve()}", "-Dfastqc.quiet=true", f"-Dfastqc.threads={threads}",
                FASTQC_MAIN] + [str(Path(f).resolve()) for f in files]
        return run_tool(tool, args, outdir / "fastqc.log")
    args = ["--outdir", to_tool_path(outdir, tool), "--threads", str(threads), "--quiet"] + [to_tool_path(f, tool) for f in files]
    return run_tool(tool, args, outdir / "fastqc.log")


def run_fastp(tool: ToolInfo, r1: Path, out1: Path, json_out: Path, html_out: Path, params: dict,
              r2: Optional[Path] = None, out2: Optional[Path] = None, threads: int = 4) -> ToolRun:
    tp = lambda p: to_tool_path(p, tool)  # noqa: E731
    args = ["-i", tp(r1), "-o", tp(out1), "-j", tp(json_out), "-h", tp(html_out), "-w", str(threads),
            "--length_required", str(params["length_required"]),
            "--n_base_limit", str(params["n_base_limit"]),
            "--qualified_quality_phred", str(params["qualified_quality"]),
            "--unqualified_percent_limit", str(params["unqualified_percent_limit"])]
    if params.get("cut_tail"):
        args += ["--cut_tail", "--cut_window_size", str(params["cut_window"]), "--cut_mean_quality", str(params["cut_mean_quality"])]
    if not params.get("trim_adapters", True):
        args += ["--disable_adapter_trimming"]
    if r2 is not None and out2 is not None:
        args += ["-I", tp(r2), "-O", tp(out2), "--detect_adapter_for_pe"]
    else:
        args += ["--adapter_sequence", params["adapter_r1"]]
    return run_tool(tool, args, json_out.parent / "fastp.log")


def parse_fastp_json(path: Path) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    s = d.get("summary", {})
    fr = d.get("filtering_result", {})
    return {
        "reads_in": s.get("before_filtering", {}).get("total_reads", 0),
        "reads_out": s.get("after_filtering", {}).get("total_reads", 0),
        "bases_in": s.get("before_filtering", {}).get("total_bases", 0),
        "bases_out": s.get("after_filtering", {}).get("total_bases", 0),
        "filtered_too_short": fr.get("too_short_reads", 0),
        "filtered_too_many_n": fr.get("too_many_N_reads", 0),
        "filtered_low_quality": fr.get("low_quality_reads", 0),
        "adapter_trimmed_reads": d.get("adapter_cutting", {}).get("adapter_trimmed_reads", 0),
    }


def run_multiqc(tool: ToolInfo, analysis_dir: Path, outdir: Path) -> ToolRun:
    outdir.mkdir(parents=True, exist_ok=True)
    args = [to_tool_path(analysis_dir, tool), "--outdir", to_tool_path(outdir, tool), "--force", "--no-ansi",
            "--filename", "multiqc_report.html"]
    return run_tool(tool, args, outdir / "multiqc.log")
