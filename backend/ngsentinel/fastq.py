"""FASTQ reading and validation.

Supports plain and gzip-compressed FASTQ (4-line records). Validation collects
problems instead of stopping at the first one, so the user gets a useful report.
"""
from __future__ import annotations

import gzip
import hashlib
import io
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, Optional

MAX_REPORTED_ERRORS = 20
VALID_BASES = set("ACGTNacgtn")
_STRIP_VALID = str.maketrans("", "", "ACGTNacgtn")  # deleting valid bases leaves only invalid ones


class FastqFormatError(ValueError):
    def __init__(self, line_no: int, message: str):
        super().__init__(f"line {line_no}: {message}")
        self.line_no = line_no
        self.message = message


@dataclass(slots=True)
class Read:
    name: str
    seq: str
    qual: str


def is_gzip(path: str | Path) -> bool:
    with open(path, "rb") as fh:
        return fh.read(2) == b"\x1f\x8b"


def open_text(path: str | Path) -> io.TextIOBase:
    """Open a FASTQ file (gzip auto-detected by magic bytes) as ASCII text."""
    if is_gzip(path):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="ascii", errors="strict", newline=None)
    return open(path, "r", encoding="ascii", errors="strict", newline=None)


def iter_reads(path: str | Path, max_reads: Optional[int] = None) -> Iterator[Read]:
    """Yield reads; raises FastqFormatError on a structurally broken record."""
    with open_text(path) as fh:
        n = 0
        line_no = 0
        while max_reads is None or n < max_reads:
            header = fh.readline()
            if not header:
                return
            line_no += 1
            if header.strip() == "":
                # allow trailing blank lines at EOF
                rest = fh.read().strip()
                if rest:
                    raise FastqFormatError(line_no, "blank line inside the file")
                return
            seq = fh.readline()
            plus = fh.readline()
            qual = fh.readline()
            if not qual:
                raise FastqFormatError(line_no, "truncated record (file ends before 4 lines are complete)")
            if not header.startswith("@"):
                raise FastqFormatError(line_no, f"header must start with '@' (found {header[:1]!r})")
            if not plus.startswith("+"):
                raise FastqFormatError(line_no + 2, "separator line must start with '+'")
            seq = seq.rstrip("\r\n")
            qual = qual.rstrip("\r\n")
            if len(seq) != len(qual):
                raise FastqFormatError(line_no + 3, f"sequence length {len(seq)} != quality length {len(qual)}")
            yield Read(header[1:].rstrip("\r\n"), seq, qual)
            line_no += 3
            n += 1


def read_id(name: str) -> str:
    """Read identifier without comment and without a trailing /1 or /2 mate suffix."""
    rid = name.split()[0] if name else ""
    if rid.endswith("/1") or rid.endswith("/2"):
        rid = rid[:-2]
    return rid


@dataclass
class ValidationReport:
    path: str
    ok: bool = True
    reads_checked: int = 0
    complete_scan: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    encoding: str = "unknown"
    min_quality_char: Optional[int] = None
    max_quality_char: Optional[int] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    compressed: bool = False

    def error(self, msg: str) -> None:
        self.ok = False
        if len(self.errors) < MAX_REPORTED_ERRORS:
            self.errors.append(msg)

    def to_dict(self) -> dict:
        return asdict(self)


def guess_encoding(min_q: Optional[int], max_q: Optional[int]) -> str:
    if min_q is None or max_q is None:
        return "unknown"
    if min_q < 33:
        return "invalid"
    if min_q < 59:
        return "Phred+33"  # Sanger / Illumina 1.8+
    if min_q >= 64:
        return "Phred+64 (legacy Illumina 1.3-1.7)"
    return "ambiguous (Phred+33 or Solexa)"


def validate_fastq(path: str | Path, max_reads: Optional[int] = None) -> ValidationReport:
    """Validate structure, alphabet, quality characters and lengths."""
    path = Path(path)
    rep = ValidationReport(path=str(path))
    if not path.exists():
        rep.error("file does not exist")
        return rep
    if path.stat().st_size == 0:
        rep.error("file is empty")
        return rep
    rep.compressed = is_gzip(path)
    names_seen = 0
    bad_alphabet = 0
    try:
        for i, r in enumerate(iter_reads(path, max_reads=max_reads)):
            rep.reads_checked += 1
            if not r.seq:
                rep.error(f"read {i + 1} ({read_id(r.name)}): empty sequence")
            if r.seq.translate(_STRIP_VALID):
                bad_alphabet += 1
                if bad_alphabet <= 5:
                    rep.error(f"read {i + 1} ({read_id(r.name)}): sequence contains characters other than A/C/G/T/N")
            if r.qual:
                qmin, qmax = ord(min(r.qual)), ord(max(r.qual))
                rep.min_quality_char = qmin if rep.min_quality_char is None else min(rep.min_quality_char, qmin)
                rep.max_quality_char = qmax if rep.max_quality_char is None else max(rep.max_quality_char, qmax)
                if qmin < 33 or qmax > 126:
                    rep.error(f"read {i + 1}: quality characters outside the printable range 33-126")
            L = len(r.seq)
            rep.min_length = L if rep.min_length is None else min(rep.min_length, L)
            rep.max_length = L if rep.max_length is None else max(rep.max_length, L)
            names_seen += 1
    except FastqFormatError as e:
        rep.error(str(e))
    except UnicodeDecodeError:
        rep.error("file is not ASCII text (binary or wrong encoding)")
    except (OSError, EOFError) as e:
        rep.error(f"could not read file: {e}")
    if max_reads is not None and rep.reads_checked >= max_reads:
        rep.complete_scan = False
        rep.warnings.append(f"only the first {max_reads:,} reads were validated")
    if rep.reads_checked == 0 and rep.ok:
        rep.error("no reads found")
    rep.encoding = guess_encoding(rep.min_quality_char, rep.max_quality_char)
    if rep.encoding.startswith("Phred+64"):
        rep.warnings.append("legacy Phred+64 encoding detected; quality values are interpreted as Phred+33 by this version")
    elif rep.encoding.startswith("ambiguous"):
        rep.warnings.append("quality encoding is ambiguous")
    elif rep.encoding == "invalid":
        rep.error("invalid quality encoding")
    if rep.max_quality_char is not None and rep.max_quality_char > 33 + 60:
        rep.warnings.append("unusually high quality characters (> Q60)")
    return rep


@dataclass
class PairReport:
    ok: bool = True
    reads_compared: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def validate_pair(r1: str | Path, r2: str | Path, max_reads: Optional[int] = None) -> PairReport:
    """Check that R1 and R2 have matching read IDs in the same order and the same count."""
    rep = PairReport()
    it1, it2 = iter_reads(r1, max_reads), iter_reads(r2, max_reads)
    try:
        while True:
            a = next(it1, None)
            b = next(it2, None)
            if a is None and b is None:
                break
            if a is None or b is None:
                rep.ok = False
                rep.errors.append(f"R1 and R2 have different read counts (diverge after {rep.reads_compared:,} reads)")
                break
            rep.reads_compared += 1
            if read_id(a.name) != read_id(b.name):
                rep.ok = False
                if len(rep.errors) < MAX_REPORTED_ERRORS:
                    rep.errors.append(f"read {rep.reads_compared}: ID mismatch {read_id(a.name)!r} vs {read_id(b.name)!r}")
                if len(rep.errors) >= 5:
                    break
    except FastqFormatError as e:
        rep.ok = False
        rep.errors.append(str(e))
    return rep


def sha256_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()
