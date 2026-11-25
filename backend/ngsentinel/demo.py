"""Synthetic paired-end FASTQ generator for demos and tests.

The data is SIMULATED (random reference, simulated qualities) and is labelled
as such everywhere. It reproduces common artefacts through their real causes:
  * adapter read-through when the insert is shorter than the read length,
  * 3' quality decline, a fraction of degraded reads and occasional N calls,
  * PCR-like duplicates.
"""
from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np

from .trimming import DEFAULT_ADAPTER_R1, DEFAULT_ADAPTER_R2

COMP = str.maketrans("ACGTN", "TGCAN")


def revcomp(s: str) -> str:
    return s.translate(COMP)[::-1]


def _qual_string(rng: np.random.Generator, n: int, degraded: bool) -> np.ndarray:
    pos = np.arange(n) / max(n - 1, 1)
    mean = 36.5 - 1.8 * np.exp(-np.arange(n) / 2.5) - (16 if degraded else 7) * pos ** 2.3
    q = np.clip(np.rint(mean + rng.normal(0, 2.2 if not degraded else 4.0, n)), 2, 41).astype(int)
    return q


def make_demo_pair(out_dir: str | Path, n_pairs: int = 20000, read_len: int = 150, seed: int = 7,
                   sample: str = "SYNTHETIC_DEMO") -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    genome = "".join(rng.choice(list("ACGT"), size=200_000, p=[0.28, 0.22, 0.22, 0.28]))
    p1 = out_dir / f"{sample}_R1.fastq.gz"
    p2 = out_dir / f"{sample}_R2.fastq.gz"
    pool: list[tuple[int, int]] = []
    pad = "A" * read_len  # polyA after the adapter (no further library sequence)
    with gzip.open(p1, "wt", encoding="ascii", newline="\n") as f1, gzip.open(p2, "wt", encoding="ascii", newline="\n") as f2:
        for i in range(n_pairs):
            if pool and rng.random() < 0.08:  # PCR duplicate of an earlier fragment
                start, ins = pool[int(rng.integers(len(pool)))]
            else:
                ins = int(np.clip(rng.normal(260, 70), 60, 600))
                if rng.random() < 0.015:  # adapter dimer / very short insert
                    ins = int(rng.integers(0, 12))
                start = int(rng.integers(0, len(genome) - ins))
                if len(pool) < 5000:
                    pool.append((start, ins))
            frag = genome[start:start + ins] if ins else ""
            r1 = (frag + DEFAULT_ADAPTER_R1 + pad)[:read_len]
            r2 = (revcomp(frag) + DEFAULT_ADAPTER_R2 + pad)[:read_len]
            u = rng.random()
            degraded = u < 0.07
            failed = u < 0.02  # very poor cluster: low quality along the whole read
            name = f"SYNTH:1:FC000:1:{1101 + i // 4000}:{int(rng.integers(1000, 30000))}:{i}"
            for fh, seq, mate in ((f1, r1, 1), (f2, r2, 2)):
                q = _qual_string(rng, read_len, degraded) - (2 if mate == 2 else 0) - (20 if failed else 0)
                q = np.clip(q, 2, 41)
                s = list(seq)
                for j in np.nonzero(q < 6)[0]:
                    if rng.random() < 0.5:
                        s[j] = "N"
                        q[j] = 2
                fh.write(f"@{name} {mate}:N:0:ACGTAC\n{''.join(s)}\n+\n{''.join(chr(int(x) + 33) for x in q)}\n")
    return p1, p2
