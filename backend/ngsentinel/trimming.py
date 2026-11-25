"""Native read preprocessing (fallback when fastp is not available).

Implements a documented subset of fastp-style processing:
  1. 3' adapter trimming (exact match of the adapter, or of an adapter prefix
     at the read end with a minimum overlap),
  2. 3' sliding-window quality trimming (like fastp --cut_tail),
  3. read filters: N-base limit, unqualified-base percentage, minimum length.
For paired-end data, a pair is kept only if both mates pass.
This is NOT fastp and does not reproduce fastp results exactly; the report
always states which engine was used.
"""
from __future__ import annotations

import gzip
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .fastq import Read, iter_reads

DEFAULT_ADAPTER_R1 = "AGATCGGAAGAGCACACGTCTGAACTCCAGTCA"  # Illumina TruSeq read 1
DEFAULT_ADAPTER_R2 = "AGATCGGAAGAGCGTCGTGTAGGGAAAGAGTGT"  # Illumina TruSeq read 2


@dataclass
class TrimParams:
    adapter_r1: str = DEFAULT_ADAPTER_R1
    adapter_r2: str = DEFAULT_ADAPTER_R2
    adapter_min_overlap: int = 5
    trim_adapters: bool = True
    cut_tail: bool = True
    cut_window: int = 4
    cut_mean_quality: int = 20
    qualified_quality: int = 15
    unqualified_percent_limit: int = 40
    n_base_limit: int = 5
    length_required: int = 15

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrimStats:
    reads_in: int = 0
    reads_out: int = 0
    bases_in: int = 0
    bases_out: int = 0
    adapter_trimmed_reads: int = 0
    quality_trimmed_reads: int = 0
    filtered_too_short: int = 0
    filtered_too_many_n: int = 0
    filtered_low_quality: int = 0
    pairs: bool = False
    engine: str = "ngsentinel-native"
    extra: dict = field(default_factory=dict)

    @property
    def retention_pct(self) -> float:
        return round(100.0 * self.reads_out / self.reads_in, 3) if self.reads_in else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["retention_pct"] = self.retention_pct
        d["base_retention_pct"] = round(100.0 * self.bases_out / self.bases_in, 3) if self.bases_in else 0.0
        return d


def find_adapter(seq: str, adapter: str, min_overlap: int) -> int:
    """Return the cut position (index where the adapter starts) or -1."""
    if not adapter:
        return -1
    s = seq.upper()
    a = adapter.upper()
    probe = a[: min(len(a), 12)]
    p = s.find(probe)
    if p >= 0:
        return p
    # adapter prefix running off the 3' end of the read
    for k in range(min(len(a), len(s)) - 1, min_overlap - 1, -1):
        if k < len(probe) and s.endswith(a[:k]):
            return len(s) - k
    return -1


def cut_tail(qual: str, window: int, threshold: int) -> int:
    """Return the new read length after 3' sliding-window trimming."""
    q = [ord(c) - 33 for c in qual]
    end = len(q)
    if end < window:
        return end if (sum(q) / max(end, 1)) >= threshold else 0
    s = sum(q[end - window : end])
    while end >= window and s < threshold * window:
        end -= 1
        if end >= window:
            s += q[end - window] - q[end]
    return end


class _ReadProcessor:
    def __init__(self, p: TrimParams):
        self.p = p
        lim = p.qualified_quality + 33
        self.low_table = bytes((0 if i < lim else 1) for i in range(256))

    def process(self, r: Read, adapter: str, st: TrimStats) -> tuple[Optional[Read], str]:
        p = self.p
        seq, qual = r.seq, r.qual
        if p.trim_adapters:
            cut = find_adapter(seq, adapter, p.adapter_min_overlap)
            if cut >= 0:
                seq, qual = seq[:cut], qual[:cut]
                st.adapter_trimmed_reads += 1
        if p.cut_tail and qual:
            end = cut_tail(qual, p.cut_window, p.cut_mean_quality)
            if end < len(qual):
                seq, qual = seq[:end], qual[:end]
                st.quality_trimmed_reads += 1
        if len(seq) < p.length_required:
            return None, "short"
        if seq.upper().count("N") > p.n_base_limit:
            return None, "n"
        if qual:
            low = qual.encode("ascii").translate(self.low_table).count(0)
            if 100.0 * low / len(qual) > p.unqualified_percent_limit:
                return None, "lowq"
        return Read(r.name, seq, qual), ""


def _write(fh, r: Read) -> None:
    fh.write(f"@{r.name}\n{r.seq}\n+\n{r.qual}\n")


def _count_reason(st: TrimStats, reason: str, n: int = 1) -> None:
    if reason == "short":
        st.filtered_too_short += n
    elif reason == "n":
        st.filtered_too_many_n += n
    elif reason == "lowq":
        st.filtered_low_quality += n


def trim_reads(
    r1: str | Path,
    out1: str | Path,
    r2: Optional[str | Path] = None,
    out2: Optional[str | Path] = None,
    params: Optional[TrimParams] = None,
    progress: Optional[Callable[[int], None]] = None,
) -> TrimStats:
    p = params or TrimParams()
    proc = _ReadProcessor(p)
    st = TrimStats(pairs=r2 is not None)
    open_out = lambda path: gzip.open(path, "wt", compresslevel=4, encoding="ascii", newline="\n")  # noqa: E731
    if r2 is None:
        with open_out(out1) as o1:
            for i, a in enumerate(iter_reads(r1)):
                st.reads_in += 1
                st.bases_in += len(a.seq)
                ta, why = proc.process(a, p.adapter_r1, st)
                if ta is None:
                    _count_reason(st, why)
                    continue
                _write(o1, ta)
                st.reads_out += 1
                st.bases_out += len(ta.seq)
                if progress and i % 100_000 == 0:
                    progress(i)
        return st

    assert out2 is not None
    with open_out(out1) as o1, open_out(out2) as o2:
        it2 = iter_reads(r2)
        for i, a in enumerate(iter_reads(r1)):
            b = next(it2, None)
            if b is None:
                raise ValueError("R2 has fewer reads than R1")
            st.reads_in += 2
            st.bases_in += len(a.seq) + len(b.seq)
            ta, wa = proc.process(a, p.adapter_r1, st)
            tb, wb = proc.process(b, p.adapter_r2, st)
            if ta is None or tb is None:
                # the pair is discarded; attribute both reads to the failing reason(s)
                _count_reason(st, wa or wb, 1)
                _count_reason(st, wb or wa, 1)
                continue
            _write(o1, ta)
            _write(o2, tb)
            st.reads_out += 2
            st.bases_out += len(ta.seq) + len(tb.seq)
            if progress and i % 100_000 == 0:
                progress(i)
        if next(it2, None) is not None:
            raise ValueError("R2 has more reads than R1")
    return st
