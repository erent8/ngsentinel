from conftest import write_fastq

from ngsentinel.fastq import iter_reads
from ngsentinel.trimming import TrimParams, cut_tail, find_adapter, trim_reads

AD = "AGATCGGAAGAGCACACGTC"


def test_find_adapter_full_and_partial():
    assert find_adapter("ACGTACGT" + AD, AD, 5) == 8
    assert find_adapter("ACGTACGT" + AD[:6], AD, 5) == 8   # adapter runs off the 3' end
    assert find_adapter("ACGTACGT" + AD[:4], AD, 5) == -1  # below minimum overlap
    assert find_adapter("ACGTACGTACGT", AD, 5) == -1
    assert find_adapter("acgt" + AD.lower(), AD, 5) == 4


def test_cut_tail():
    q = "I" * 10 + "#" * 6  # Q40 x10 then Q2 x6
    # like fastp --cut_tail: stop at the first window (from the 3' end) whose mean >= threshold;
    # window [8,12) = 40,40,2,2 has mean 21, so two low bases remain inside it
    assert cut_tail(q, 4, 20) == 12
    assert cut_tail(q, 4, 25) == 11  # window [7,11) mean 30.5
    assert cut_tail("I" * 8, 4, 20) == 8
    assert cut_tail("#" * 8, 4, 20) < 4


def test_single_end_filters(tmp_path):
    recs = [
        ("keep", "ACGTACGTACGTACGTACGT" + AD, "I" * (20 + len(AD))),  # adapter removed, 20 bp kept
        ("short", "ACGT" + AD, "I" * (4 + len(AD))),                  # 4 bp after trimming -> too short
        ("nnn", "ACGTNNNNNNACGTACGTAC", "I" * 20),                    # 6 N > limit 5
        ("lowq", "ACGTACGTACGTACGTACGT", "+" * 9 + "I" * 11),         # 45 % bases < Q15 -> low quality
    ]
    src = write_fastq(tmp_path / "in.fq", recs)
    out = tmp_path / "out.fq.gz"
    st = trim_reads(src, out, params=TrimParams(adapter_r1=AD, cut_tail=False))
    kept = list(iter_reads(out))
    assert [r.name for r in kept] == ["keep"]
    assert kept[0].seq == "ACGTACGTACGTACGTACGT"
    assert st.reads_in == 4 and st.reads_out == 1
    assert st.filtered_too_short == 1 and st.filtered_too_many_n == 1 and st.filtered_low_quality == 1
    assert st.adapter_trimmed_reads == 2
    assert st.to_dict()["retention_pct"] == 25.0


def test_paired_end_drops_both_mates(tmp_path):
    good = "ACGTACGTACGTACGTACGTACGT"
    r1 = write_fastq(tmp_path / "1.fq", [("a/1", good, "I" * 24), ("b/1", good, "I" * 24)])
    r2 = write_fastq(tmp_path / "2.fq", [("a/2", good, "I" * 24), ("b/2", "ACG", "III")])
    o1, o2 = tmp_path / "o1.fq.gz", tmp_path / "o2.fq.gz"
    st = trim_reads(r1, o1, r2, o2, TrimParams())
    assert [r.name for r in iter_reads(o1)] == ["a/1"]
    assert [r.name for r in iter_reads(o2)] == ["a/2"]
    assert st.reads_in == 4 and st.reads_out == 2
