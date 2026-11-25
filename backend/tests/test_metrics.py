import pytest
from conftest import write_fastq

from ngsentinel.metrics import compute_metrics

Q40, Q10 = "I", "+"  # chr(40+33), chr(10+33)


def test_basic_summary(tmp_path):
    p = write_fastq(tmp_path / "a.fq", [
        ("r1", "GGCC", Q40 * 4),          # GC 100 %, all Q40
        ("r2", "AATT", Q10 * 4),          # GC 0 %, all Q10
        ("r3", "ACGTNN", Q40 * 4 + "!!"),  # 2 N
    ])
    m = compute_metrics(p)
    s = m["summary"]
    assert s["total_reads"] == 3
    assert s["total_bases"] == 14
    assert s["min_length"] == 4 and s["max_length"] == 6
    assert s["q30_pct"] == pytest.approx(100 * 8 / 14, abs=1e-3)
    assert s["q20_pct"] == pytest.approx(100 * 8 / 14, abs=1e-3)
    assert s["mean_quality"] == pytest.approx((8 * 40 + 4 * 10) / 14, abs=1e-3)
    assert s["n_pct"] == pytest.approx(100 * 2 / 14, abs=1e-3)
    assert s["gc_pct"] == pytest.approx(100 * 6 / 12, abs=1e-3)  # N excluded from GC denominator
    assert m["length_distribution"] == {"length": [4, 6], "count": [2, 1]}
    pb = m["per_base_quality"]
    assert pb["mean"][0] == pytest.approx(30.0)
    assert pb["coverage"][4] == 1  # only the 6-bp read reaches position 5


def test_adapter_and_duplication(tmp_path):
    adapter_read = "TTTT" + "AGATCGGAAGAGC" + "AAA"
    recs = [(f"a{i}", adapter_read, Q40 * len(adapter_read)) for i in range(5)]
    recs += [(f"b{i}", "ACGTACGTACGTACGTACGT", Q40 * 20) for i in range(5)]
    m = compute_metrics(write_fastq(tmp_path / "d.fq", recs))
    ser = m["adapter_content"]["series"]["Illumina Universal Adapter"]
    assert ser[3] == 0.0           # adapter starts at position 5 (index 4)
    assert ser[4] == pytest.approx(50.0)
    assert m["summary"]["adapter_max_pct"] == pytest.approx(50.0)
    assert m["summary"]["duplication_pct"] == pytest.approx(80.0)  # 10 reads, 2 distinct
    over = m["overrepresented"]
    assert len(over) == 2
    assert {o["possible_source"] for o in over} == {"Illumina Universal Adapter", "No hit"}


def test_read_limit_and_multiple_files(tmp_path):
    a = write_fastq(tmp_path / "1.fq", [(f"r{i}", "ACGT", Q40 * 4) for i in range(10)])
    b = write_fastq(tmp_path / "2.fq", [(f"r{i}", "ACGT", Q40 * 4) for i in range(10)], gz=True)
    m = compute_metrics([a, b], max_reads=4)
    assert m["summary"]["total_reads"] == 8
    assert m["summary"]["truncated"] is True
    assert compute_metrics([a, b])["summary"]["truncated"] is False


def test_gc_deviation_small_for_uniform_random_reads(tmp_path):
    import random

    rnd = random.Random(1)
    recs = [(f"r{i}", "".join(rnd.choice("ACGT") for _ in range(100)), Q40 * 100) for i in range(3000)]
    m = compute_metrics(write_fastq(tmp_path / "g.fq", recs))
    assert m["summary"]["gc_deviation_pct"] < 10
    assert sum(m["gc_content"]["pct"]) == pytest.approx(100, abs=0.01)
