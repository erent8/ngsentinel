import gzip
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "config" / "qc_rules.yaml"


def write_fastq(path: Path, records: list[tuple[str, str, str]], gz: bool = False) -> Path:
    text = "".join(f"@{n}\n{s}\n+\n{q}\n" for n, s, q in records)
    if gz:
        with gzip.open(path, "wt", encoding="ascii", newline="\n") as fh:
            fh.write(text)
    else:
        path.write_text(text, encoding="ascii", newline="\n")
    return path


@pytest.fixture
def rules_file() -> Path:
    return RULES
