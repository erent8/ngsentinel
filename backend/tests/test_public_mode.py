import importlib


def test_public_mode_restrictions(tmp_path, monkeypatch):
    monkeypatch.setenv("NGSENTINEL_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("NGSENTINEL_PUBLIC", "1")
    monkeypatch.setenv("NGSENTINEL_SEED_EXAMPLES", "0")
    monkeypatch.setenv("NGSENTINEL_MAX_UPLOAD_MB", "1")
    import ngsentinel.api as api

    api = importlib.reload(api)
    from fastapi.testclient import TestClient

    c = TestClient(api.app)
    cfg = c.get("/api/config").json()
    assert cfg["public"] is True and cfg["max_upload_mb"] == 1

    # no access to the server's disk, no rule edits, no deletion
    assert c.post("/api/inputs/check", json={"path": str(api.DEFAULT_RULES)}).status_code == 403
    assert c.put("/api/rules", json={"text": c.get("/api/rules").json()["text"]}).status_code == 403
    assert c.delete("/api/rules").status_code == 403

    # inputs must be uploads or demo data
    outside = tmp_path / "x.fastq"
    outside.write_text("@r\nACGT\n+\nIIII\n")
    assert c.post("/api/runs", json={"sample": "S", "r1": str(outside)}).status_code == 403

    # upload size limit
    big = b"@r\n" + b"A" * (1024 * 1024 + 10) + b"\n+\n" + b"I" * 10 + b"\n"
    assert c.post("/api/uploads", files={"file": ("big.fastq", big)}).status_code == 413
    ok = c.post("/api/uploads", files={"file": ("small.fastq", b"@r\nACGT\n+\nIIII\n")})
    assert ok.status_code == 200
    assert c.delete("/api/runs/anything").status_code in (403, 404)

    # leave public mode for the other tests
    monkeypatch.setenv("NGSENTINEL_PUBLIC", "0")
    importlib.reload(api)
