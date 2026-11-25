from conftest import write_fastq

from ngsentinel.fastq import guess_encoding, iter_reads, read_id, validate_fastq, validate_pair


def test_valid_plain_and_gzip(tmp_path):
    recs = [("r1 1:N:0", "ACGTN", "IIII#"), ("r2 1:N:0", "GGCC", "IIII")]
    for gz in (False, True):
        p = write_fastq(tmp_path / f"a{gz}.fq", recs, gz=gz)
        rep = validate_fastq(p)
        assert rep.ok, rep.errors
        assert rep.reads_checked == 2
        assert rep.compressed is gz
        assert rep.min_length == 4 and rep.max_length == 5
        assert rep.encoding == "Phred+33"


def test_length_mismatch(tmp_path):
    p = write_fastq(tmp_path / "x.fq", [("r1", "ACGT", "III")])
    rep = validate_fastq(p)
    assert not rep.ok
    assert "sequence length 4 != quality length 3" in rep.errors[0]


def test_bad_header_and_separator(tmp_path):
    p = tmp_path / "x.fq"
    p.write_text("r1\nACGT\n+\nIIII\n")
    assert "must start with '@'" in validate_fastq(p).errors[0]
    p.write_text("@r1\nACGT\nIIII\nIIII\n")
    assert "separator" in validate_fastq(p).errors[0]


def test_truncated_and_empty(tmp_path):
    p = tmp_path / "t.fq"
    p.write_text("@r1\nACGT\n+\n")
    assert "truncated" in validate_fastq(p).errors[0]
    e = tmp_path / "e.fq"
    e.write_text("")
    assert validate_fastq(e).errors == ["file is empty"]
    assert validate_fastq(tmp_path / "missing.fq").errors == ["file does not exist"]


def test_invalid_alphabet(tmp_path):
    p = write_fastq(tmp_path / "x.fq", [("r1", "ACGU", "IIII")])
    rep = validate_fastq(p)
    assert not rep.ok and "other than A/C/G/T/N" in rep.errors[0]


def test_crlf_and_trailing_blank_lines(tmp_path):
    p = tmp_path / "w.fq"
    p.write_bytes(b"@r1\r\nACGT\r\n+\r\nIIII\r\n\r\n")
    reads = list(iter_reads(p))
    assert reads[0].seq == "ACGT" and reads[0].qual == "IIII"


def test_encoding_guess():
    assert guess_encoding(35, 74) == "Phred+33"
    assert guess_encoding(66, 104).startswith("Phred+64")
    assert guess_encoding(None, None) == "unknown"


def test_read_id_and_pairing(tmp_path):
    assert read_id("abc/1 extra") == "abc"
    assert read_id("abc 1:N:0") == "abc"
    a = write_fastq(tmp_path / "1.fq", [("x/1", "A", "I"), ("y/1", "C", "I")])
    b = write_fastq(tmp_path / "2.fq", [("x/2", "A", "I"), ("y/2", "C", "I")])
    assert validate_pair(a, b).ok
    c = write_fastq(tmp_path / "3.fq", [("x/2", "A", "I"), ("z/2", "C", "I")])
    rep = validate_pair(a, c)
    assert not rep.ok and "ID mismatch" in rep.errors[0]
    d = write_fastq(tmp_path / "4.fq", [("x/2", "A", "I")])
    assert "different read counts" in validate_pair(a, d).errors[0]
