"""Download a public sequencing run from the European Nucleotide Archive (ENA)
and verify each FASTQ file against the MD5 checksum published by ENA."""
from __future__ import annotations

import hashlib
import re
import urllib.request
from pathlib import Path

PORTAL = "https://www.ebi.ac.uk/ena/portal/api/filereport?accession={acc}&result=read_run&fields=fastq_ftp,fastq_md5,fastq_bytes&format=tsv"
ACC_RE = re.compile(r"^[SED]RR\d{5,10}$")


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_files(acc: str) -> list[tuple[str, str, int]]:
    """[(https url, md5, bytes)] for the paired (_1/_2) or single FASTQ files of a run."""
    if not ACC_RE.match(acc):
        raise ValueError(f"not a run accession: {acc!r}")
    with urllib.request.urlopen(PORTAL.format(acc=acc), timeout=60) as r:
        lines = r.read().decode().strip().splitlines()
    if len(lines) < 2:
        raise ValueError(f"run {acc} not found in ENA")
    head = lines[0].split("\t")
    row = dict(zip(head, lines[1].split("\t")))
    urls, md5s, sizes = (row[k].split(";") for k in ("fastq_ftp", "fastq_md5", "fastq_bytes"))
    files = [("https://" + u, m, int(s)) for u, m, s in zip(urls, md5s, sizes)]
    paired = [f for f in files if re.search(r"_[12]\.fastq\.gz$", f[0])]
    return paired or files


def download_run(acc: str, dest: Path, retries: int = 5) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for url, md5, size in run_files(acc):
        path = dest / url.rsplit("/", 1)[-1]
        for _ in range(retries):
            if path.exists() and path.stat().st_size == size and _md5(path) == md5:
                break
            have = path.stat().st_size if path.exists() and path.stat().st_size < size else 0
            req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
            try:
                with urllib.request.urlopen(req, timeout=120) as r, open(path, "ab" if have else "wb") as fh:
                    for chunk in iter(lambda: r.read(1 << 20), b""):
                        fh.write(chunk)
            except OSError:
                continue
        else:
            raise IOError(f"could not download {url} with a matching MD5")
        out.append(path)
    return out
