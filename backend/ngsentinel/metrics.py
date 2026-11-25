"""Native quality-control metrics for FASTQ data (FastQC-style modules).

Implemented in numpy so that the core QC always works, even when FastQC
(which needs Java) is not installed. The metric definitions follow FastQC's
conventions where one exists; differences are documented per metric.
"""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .fastq import iter_reads

MAX_Q = 60          # Phred values are clipped to 0..60
MAX_POS = 1000      # per-position modules track the first 1000 bp
DUP_SAMPLE = 200_000
OVERREP_MIN_FRACTION = 0.001  # 0.1 %, as in FastQC

# Adapter / artefact probes (first 12 bp, as used by FastQC's adapter module)
ADAPTERS: dict[str, str] = {
    "Illumina Universal Adapter": "AGATCGGAAGAGC",
    "Illumina Small RNA 3' Adapter": "TGGAATTCTCGG",
    "Nextera Transposase Sequence": "CTGTCTCTTATA",
    "polyA": "AAAAAAAAAAAA",
    "polyG": "GGGGGGGGGGGG",
}


class _Acc:
    def __init__(self) -> None:
        self.n_reads = 0
        self.n_bases = 0
        self.max_len = 0
        self.min_len: Optional[int] = None
        self.qhist = np.zeros((MAX_POS, MAX_Q + 1), dtype=np.int64)
        self.cov = np.zeros(MAX_POS, dtype=np.int64)
        self.n_pos = np.zeros(MAX_POS, dtype=np.int64)
        self.base_pos = {b: np.zeros(MAX_POS, dtype=np.int64) for b in "ACGT"}
        self.len_hist: Counter[int] = Counter()
        self.read_q_hist = np.zeros(MAX_Q + 1, dtype=np.int64)
        self.gc_hist = np.zeros(101, dtype=np.int64)
        self.gc_pairs: Counter[int] = Counter()  # key = gc_count * 100000 + called_bases
        self.gc_bases = 0
        self.acgt_bases = 0
        self.n_bases_total = 0
        self.q_sum = 0
        self.q20 = 0
        self.q30 = 0
        self.adapter_pos = {name: np.zeros(MAX_POS, dtype=np.int64) for name in ADAPTERS}
        self.dup_counter: Counter[str] = Counter()
        self.dup_n = 0

    def add(self, seqs: list[str], quals: list[str]) -> None:
        n = len(seqs)
        if n == 0:
            return
        lens = np.fromiter((len(s) for s in seqs), dtype=np.int64, count=n)
        total = int(lens.sum())
        self.n_reads += n
        self.n_bases += total
        for L, c in zip(*np.unique(lens, return_counts=True)):
            self.len_hist[int(L)] += int(c)
        self.max_len = max(self.max_len, int(lens.max()))
        mn = int(lens.min())
        self.min_len = mn if self.min_len is None else min(self.min_len, mn)

        # duplication sample + adapter search (string operations run in C)
        for s in seqs:
            su = s.upper()
            for name, probe in ADAPTERS.items():
                p = su.find(probe)
                if p >= 0:
                    self.adapter_pos[name][min(p, MAX_POS - 1)] += 1
            if self.dup_n < DUP_SAMPLE:
                self.dup_counter[su[:50] if len(su) > 75 else su] += 1
                self.dup_n += 1
        if total == 0:
            return

        sb = np.frombuffer("".join(seqs).encode("ascii"), dtype=np.uint8).copy()
        sb[(sb >= 97) & (sb <= 122)] -= 32  # upper-case
        qb = np.frombuffer("".join(quals).encode("ascii"), dtype=np.uint8).astype(np.int64) - 33
        np.clip(qb, 0, MAX_Q, out=qb)
        starts = np.concatenate(([0], np.cumsum(lens)[:-1]))
        pos = np.arange(total, dtype=np.int64) - np.repeat(starts, lens)
        np.minimum(pos, MAX_POS - 1, out=pos)

        self.qhist += np.bincount(pos * (MAX_Q + 1) + qb, minlength=MAX_POS * (MAX_Q + 1)).reshape(MAX_POS, MAX_Q + 1)
        self.cov += np.bincount(pos, minlength=MAX_POS)
        is_n = sb == ord("N")
        is_gc = (sb == ord("G")) | (sb == ord("C"))
        self.n_pos += np.bincount(pos[is_n], minlength=MAX_POS)
        for b in "ACGT":
            self.base_pos[b] += np.bincount(pos[sb == ord(b)], minlength=MAX_POS)
        self.q_sum += int(qb.sum())
        self.q20 += int((qb >= 20).sum())
        self.q30 += int((qb >= 30).sum())
        self.gc_bases += int(is_gc.sum())
        self.n_bases_total += int(is_n.sum())
        self.acgt_bases += int(total - is_n.sum())

        nz = lens > 0
        st = starts[nz]
        ln = lens[nz]
        read_q = np.add.reduceat(qb, st) / ln
        self.read_q_hist += np.bincount(np.clip(np.rint(read_q).astype(np.int64), 0, MAX_Q), minlength=MAX_Q + 1)
        gc_r = np.add.reduceat(is_gc.astype(np.int64), st)
        n_r = np.add.reduceat(is_n.astype(np.int64), st)
        called = ln - n_r
        ok = called > 0
        gc_pct = np.rint(100.0 * gc_r[ok] / called[ok]).astype(np.int64)
        self.gc_hist += np.bincount(gc_pct, minlength=101)
        keys, cnt = np.unique(gc_r[ok] * 100000 + called[ok], return_counts=True)
        for k, c in zip(keys.tolist(), cnt.tolist()):
            self.gc_pairs[k] += c


def _percentile_from_hist(h: np.ndarray, p: float) -> float:
    tot = h.sum()
    if tot == 0:
        return float("nan")
    c = np.cumsum(h)
    return float(np.searchsorted(c, p * tot, side="left"))


def _fractional_gc_hist(pairs: Counter) -> np.ndarray:
    """Spread each read's GC fraction over the percentage bins it could belong to.

    A read of length L can only take L+1 GC values, so short or variable-length reads
    give a spiky integer histogram. Like FastQC's GC model, each read's
    [gc - 0.5, gc + 0.5] / L interval is distributed over the overlapping 1 % bins."""
    h = np.zeros(101, dtype=np.float64)
    for key, c in pairs.items():
        gc, called = divmod(key, 100000)
        lo = max(0.0, (gc - 0.5) / called * 100.0)
        hi = min(100.0, (gc + 0.5) / called * 100.0)
        span = hi - lo
        b0, b1 = int(np.floor(lo + 0.5)), int(np.floor(hi + 0.5))
        for b in range(b0, min(b1, 100) + 1):
            left, right = max(lo, b - 0.5), min(hi, b + 0.5)
            if right > left:
                h[b] += c * (right - left) / span
    return h


def _gc_deviation(gc_hist: np.ndarray) -> tuple[float, list[float]]:
    """Sum of absolute deviations from a normal fitted to the observed distribution,
    as a percentage of reads (FastQC's 'per sequence GC content' logic)."""
    total = gc_hist.sum()
    if total == 0:
        return float("nan"), [0.0] * 101
    x = np.arange(101)
    mean = float((gc_hist * x).sum() / total)
    var = float((gc_hist * (x - mean) ** 2).sum() / total)
    sd = math.sqrt(var) if var > 0 else 1.0
    theo = np.exp(-((x - mean) ** 2) / (2 * sd * sd))
    theo = theo / theo.sum() * total
    dev = float(np.abs(gc_hist - theo).sum() / total * 100.0)
    return dev, (theo / total * 100.0).round(4).tolist()


DUP_BINS = [("1", 1, 1), ("2", 2, 2), ("3", 3, 3), ("4", 4, 4), ("5", 5, 5), ("6", 6, 6), ("7", 7, 7), ("8", 8, 8), ("9", 9, 9),
            (">10", 10, 49), (">50", 50, 99), (">100", 100, 499), (">500", 500, 999), (">1k", 1000, 4999), (">5k", 5000, 9999), (">10k", 10000, 10**12)]


def _finalize(acc: _Acc, truncated: bool) -> dict:
    L = max(1, min(acc.max_len, MAX_POS))
    qh = acc.qhist[:L]
    cov = np.maximum(acc.cov[:L], 1)
    qvals = np.arange(MAX_Q + 1)
    per_base = {
        "position": list(range(1, L + 1)),
        "mean": ((qh * qvals).sum(axis=1) / cov).round(3).tolist(),
        "p10": [_percentile_from_hist(r, 0.10) for r in qh],
        "p25": [_percentile_from_hist(r, 0.25) for r in qh],
        "median": [_percentile_from_hist(r, 0.50) for r in qh],
        "p75": [_percentile_from_hist(r, 0.75) for r in qh],
        "p90": [_percentile_from_hist(r, 0.90) for r in qh],
        "coverage": acc.cov[:L].tolist(),
    }
    n_reads = max(acc.n_reads, 1)
    adapter = {
        name: (np.cumsum(acc.adapter_pos[name][:L]) / n_reads * 100.0).round(4).tolist() for name in ADAPTERS
    }
    adapter_max = {name: (vals[-1] if vals else 0.0) for name, vals in adapter.items()}
    gc_frac = _fractional_gc_hist(acc.gc_pairs) if acc.gc_pairs else acc.gc_hist.astype(np.float64)
    gc_dev, gc_theo = _gc_deviation(gc_frac)
    gc_total = max(gc_frac.sum(), 1)

    # duplication
    counts = Counter(acc.dup_counter.values())  # copies -> number of distinct sequences
    dup_levels = []
    for label, lo, hi in DUP_BINS:
        reads_in_bin = sum(c * k for c, k in counts.items() if lo <= c <= hi)
        dup_levels.append({"level": label, "pct_of_reads": round(100.0 * reads_in_bin / max(acc.dup_n, 1), 4)})
    distinct = len(acc.dup_counter)
    duplication_pct = 100.0 * (1 - distinct / acc.dup_n) if acc.dup_n else 0.0

    overrep = []
    for seq, c in acc.dup_counter.most_common(25):
        frac = c / max(acc.dup_n, 1)
        if frac < OVERREP_MIN_FRACTION or c < 2:
            break
        src = next((name for name, probe in ADAPTERS.items() if probe in seq), "No hit")
        overrep.append({"sequence": seq, "count": c, "pct": round(100 * frac, 4), "possible_source": src})
        if len(overrep) >= 10:
            break

    per_pos_n = (acc.n_pos[:L] / cov * 100).round(4).tolist()
    content = {b: (acc.base_pos[b][:L] / cov * 100).round(3).tolist() for b in "ACGT"}
    lengths = sorted(acc.len_hist.items())
    summary = {
        "total_reads": acc.n_reads,
        "total_bases": acc.n_bases,
        "min_length": acc.min_len or 0,
        "max_length": acc.max_len,
        "mean_length": round(acc.n_bases / n_reads, 3) if acc.n_reads else 0,
        "gc_pct": round(100.0 * acc.gc_bases / max(acc.acgt_bases, 1), 3),
        "n_pct": round(100.0 * acc.n_bases_total / max(acc.n_bases, 1), 4),
        "mean_quality": round(acc.q_sum / max(acc.n_bases, 1), 3),
        "q20_pct": round(100.0 * acc.q20 / max(acc.n_bases, 1), 3),
        "q30_pct": round(100.0 * acc.q30 / max(acc.n_bases, 1), 3),
        "adapter_max_pct": round(max(adapter_max.values()) if adapter_max else 0.0, 4),
        "adapter_by_type_pct": {k: round(v, 4) for k, v in adapter_max.items()},
        "duplication_pct": round(duplication_pct, 3),
        "gc_deviation_pct": round(gc_dev, 3) if not math.isnan(gc_dev) else None,
        "overrepresented_count": len(overrep),
        "reads_sampled_for_duplication": acc.dup_n,
        "truncated": truncated,
    }
    return {
        "summary": summary,
        "per_base_quality": per_base,
        "per_sequence_quality": {"quality": list(range(MAX_Q + 1)), "count": acc.read_q_hist.tolist()},
        "gc_content": {"gc": list(range(101)), "pct": (gc_frac / gc_total * 100).round(4).tolist(), "theoretical_pct": gc_theo},
        "per_base_n": {"position": list(range(1, L + 1)), "pct": per_pos_n},
        "per_base_content": {"position": list(range(1, L + 1)), **content},
        "length_distribution": {"length": [k for k, _ in lengths], "count": [v for _, v in lengths]},
        "adapter_content": {"position": list(range(1, L + 1)), "series": adapter},
        "duplication_levels": dup_levels,
        "overrepresented": overrep,
    }


def compute_metrics(
    paths: str | Path | list[str | Path],
    max_reads: Optional[int] = None,
    chunk: int = 50_000,
    progress: Optional[Callable[[int], None]] = None,
) -> dict:
    """Stream one or more FASTQ files (e.g. R1 and R2 of a sample) and return all
    QC modules as a JSON-serialisable dict. `max_reads` applies per file."""
    if isinstance(paths, (str, Path)):
        paths = [paths]
    acc = _Acc()
    n_total = 0
    truncated = False
    for path in paths:
        seqs: list[str] = []
        quals: list[str] = []
        n = 0
        for r in iter_reads(path, max_reads=max_reads):
            seqs.append(r.seq)
            quals.append(r.qual)
            n += 1
            if len(seqs) >= chunk:
                acc.add(seqs, quals)
                seqs, quals = [], []
                if progress:
                    progress(n_total + n)
        acc.add(seqs, quals)
        n_total += n
        truncated = truncated or (max_reads is not None and n >= max_reads)
        if progress:
            progress(n_total)
    return _finalize(acc, truncated)
