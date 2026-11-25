"""Export selected analyses into a static, read-only showcase.

    python scripts/export_showcase.py <out_dir> <run_id> [<run_id> ...]

Writes <out_dir>/index.html (the single-file React build, VITE_STATIC=1) and
<out_dir>/data/... (runs.json, tools.json, rules.json, per-run detail/metrics and
the HTML reports). Local file paths are removed from every exported file: only
file names remain, and the export fails if any absolute local path survives.
MultiQC is re-run on copies of its inputs with analysis paths hidden, because its
report stores data compressed (so it cannot be cleaned by text replacement).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

from ngsentinel.decision import parse_rules  # noqa: E402
from ngsentinel.history import History  # noqa: E402
from ngsentinel.tools import detect_all  # noqa: E402

DATA = PROJECT / "data"
HOME = Path.home()

# Only paths under the user's home folder are removed (they reveal the account name);
# matching a fixed prefix never touches URLs or minified JavaScript in the reports.
_drive, _rest = str(HOME)[:2], str(HOME)[3:].replace("\\", "/")  # "C:", "Users/<name>"
_parts = _rest.split("/")
_sep = r"(?:\\\\|\\|/)"  # JSON-escaped backslash, backslash or slash
_home_any = re.escape(_drive) + _sep + _sep.join(re.escape(p) for p in _parts)
_wsl_home = "/mnt/" + re.escape(_drive[0].lower()) + "/" + "/".join(re.escape(p) for p in _parts)
PATH_PATTERNS = [
    re.compile(f"(?:{_home_any}|{_wsl_home})(?:{_sep}[^\\s\"'<>|*?\\\\/]+)*{_sep}", re.IGNORECASE),
]
FORBIDDEN = [str(HOME), str(HOME).replace("\\", "/"), str(HOME).replace("\\", "\\\\"), "/mnt/c/Users/" + HOME.name, HOME.name + "\\", HOME.name + "/"]


def strip_paths(text: str) -> str:
    """Remove directory prefixes, keep the file name: C:\\a\\b\\x.fq.gz -> x.fq.gz"""
    for pat in PATH_PATTERNS:
        text = pat.sub("", text)
    return text


def clean(obj):
    if isinstance(obj, str):
        return strip_paths(obj)
    if isinstance(obj, list):
        return [clean(x) for x in obj]
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    return obj


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(data), ensure_ascii=False), encoding="utf-8")


def copy_text(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(strip_paths(src.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")


def rerun_multiqc(run_dir: Path, dst_html: Path) -> bool:
    mq = detect_all()["multiqc"]
    if not mq.available:
        return False
    inputs = list(run_dir.glob("fastqc_*/*_fastqc.zip")) + list((run_dir / "processed").glob("fastp.json"))
    if not inputs:
        return False
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        for f in inputs:
            sub = tdp / f.parent.name
            sub.mkdir(exist_ok=True)
            if f.name == "fastp.json":
                d = json.loads(f.read_text(encoding="utf-8"))
                d["command"] = strip_paths(d.get("command", ""))
                (sub / f.name).write_text(json.dumps(d), encoding="utf-8")
            else:
                shutil.copy(f, sub / f.name)
        out = tdp / "_out"
        cmd = mq.command + [".", "--outdir", str(out), "--force", "--no-data-dir", "--no-ansi", "--filename", "multiqc_report.html",
                            "--cl-config", "show_analysis_paths: False", "--cl-config", "show_analysis_time: False",
                            "--title", run_dir.name.split("_", 1)[-1]]
        p = subprocess.run(cmd, cwd=tdp, capture_output=True, text=True, errors="replace")
        html = out / "multiqc_report.html"
        if p.returncode != 0 or not html.exists():
            print("MultiQC re-run failed:", p.stdout[-500:], p.stderr[-500:])
            return False
        dst_html.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(html, dst_html)
    return True


def export_run(run_id: str, hist: History, out: Path) -> dict:
    rec = hist.get(run_id)
    if not rec or rec["state"] != "done":
        raise SystemExit(f"run {run_id} not found or not finished")
    rd = Path(rec["run_dir"])
    dst = out / "data" / "runs" / run_id
    load = lambda n: json.loads((rd / n).read_text(encoding="utf-8"))  # noqa: E731
    files = {"report": True, "multiqc": False, "fastp": (rd / "processed" / "fastp.html").exists(),
             "fastqc": sorted(str(p.relative_to(rd)).replace("\\", "/") for p in rd.glob("fastqc_*/*_fastqc.html"))}
    manifest = load("manifest.json")
    manifest.pop("tools_detected", None)
    manifest.pop("traceback", None)
    rec_out = {k: v for k, v in rec.items() if k != "run_dir"}
    rec_out["run_dir"] = ""
    write_json(dst / "metrics_raw.json", load("metrics_raw.json"))
    write_json(dst / "metrics_processed.json", load("metrics_processed.json"))
    copy_text(rd / "report.html", dst / "files" / "report.html")
    if os.environ.get("TOOL_REPORTS", "1") == "0":
        # third-party tool reports left out (e.g. for a public showcase)
        files.update(fastp=False, fastqc=[], multiqc=False)
    else:
        if files["fastp"]:
            copy_text(rd / "processed" / "fastp.html", dst / "files" / "processed" / "fastp.html")
        for f in files["fastqc"]:
            copy_text(rd / f, dst / "files" / f)
        files["multiqc"] = rerun_multiqc(rd, dst / "files" / "multiqc" / "multiqc_report.html")
    write_json(dst / "detail.json", {"record": rec_out, "status": load("status.json"), "manifest": manifest,
                                     "decision": load("decision.json"), "trimming": load("trimming.json"), "files": files})
    return rec_out


def build_frontend(out: Path, repo_url: str, live_url: str) -> None:
    env = dict(os.environ, VITE_STATIC="1", VITE_REPO_URL=repo_url, VITE_LIVE_URL=live_url)
    npx = "npx.cmd" if os.name == "nt" else "npx"
    subprocess.run([npx, "vite", "build"], cwd=PROJECT / "frontend", env=env, check=True)
    html = (PROJECT / "frontend" / "dist-static" / "index.html").read_text(encoding="utf-8")
    (out / "index.html").write_text(page_fragment(html), encoding="utf-8")


def page_fragment(html: str) -> str:
    """Turn a full HTML document into a page fragment (title, styles and scripts from
    <head>, then the <body> content), as expected by hosts that add their own
    document skeleton (e.g. Claude Artifacts). Plain browsers render it fine too."""
    head = re.search(r"<head[^>]*>(.*?)</head>", html, re.S | re.I).group(1)
    body = re.search(r"<body[^>]*>(.*?)</body>", html, re.S | re.I).group(1)
    # keep charset + viewport so the page also works on plain static hosts
    head = re.sub(r"<meta[^>]*name=\"viewport\"[^>]*>", '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">', head)
    head = re.sub(r"<link[^>]*rel=\"icon\"[^>]*>\s*", "", head)
    return head.strip() + "\n" + body.strip() + "\n"


def scan(out: Path) -> list[str]:
    problems = []
    for p in out.rglob("*"):
        if p.is_file() and p.suffix in (".html", ".json"):
            t = p.read_text(encoding="utf-8", errors="replace")
            for f in FORBIDDEN:
                if f in t:
                    problems.append(f"{p.relative_to(out)} contains a local path ({f!r})")
                    break
    return problems


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    out = Path(sys.argv[1]).resolve()
    run_ids = sys.argv[2:]
    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)
    hist = History(DATA / "runs" / "history.sqlite")
    runs = [export_run(r, hist, out) for r in run_ids]
    write_json(out / "data" / "runs.json", runs)
    tools = {k: v.to_dict() for k, v in detect_all().items()}
    for t in tools.values():
        t["command"] = [Path(c).name if ("\\" in c or "/" in c) else c for c in t["command"] if not c.startswith("-cp") and ";" not in c]
    write_json(out / "data" / "tools.json", tools)
    rules_text = (PROJECT / "config" / "qc_rules.yaml").read_text(encoding="utf-8")
    write_json(out / "data" / "rules.json", {"text": rules_text, "custom": False, "parsed": parse_rules(rules_text)})
    build_frontend(out, os.environ.get("REPO_URL", ""), os.environ.get("LIVE_URL", ""))
    problems = scan(out)
    if problems:
        print("\n".join(problems))
        raise SystemExit("export contains local paths — not safe to publish")
    files = [p for p in out.rglob("*") if p.is_file()]
    print(f"exported {len(runs)} runs, {len(files)} files, {sum(p.stat().st_size for p in files) / 1e6:.1f} MB -> {out}")


if __name__ == "__main__":
    main()
