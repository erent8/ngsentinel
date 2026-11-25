import importlib
import json
import time

from conftest import write_fastq

from ngsentinel.demo import make_demo_pair
from ngsentinel.history import History
from ngsentinel.pipeline import RunConfig, run_pipeline


def test_pipeline_end_to_end_native(tmp_path, rules_file):
    r1, r2 = make_demo_pair(tmp_path / "demo", n_pairs=3000)
    cfg = RunConfig("DEMO", str(r1), str(r2), engine="native", rules_file=str(rules_file))
    hist = History(tmp_path / "runs" / "h.sqlite")
    rd = run_pipeline(cfg, tmp_path / "runs", hist)
    status = json.loads((rd / "status.json").read_text())
    assert status["state"] == "done", status
    manifest = json.loads((rd / "manifest.json").read_text())
    assert manifest["inputs"][0]["sha256"] and len(manifest["inputs"]) == 2
    assert any(s["engine"] == "ngsentinel-native trimmer" for s in manifest["steps"])
    decision = json.loads((rd / "decision.json").read_text())
    assert decision["overall"] in ("PASS", "REVIEW", "FAIL")
    trimming = json.loads((rd / "trimming.json").read_text())
    assert 0 < trimming["reads_out"] <= trimming["reads_in"] == 6000
    raw = json.loads((rd / "metrics_raw.json").read_text())["summary"]
    proc = json.loads((rd / "metrics_processed.json").read_text())["summary"]
    assert proc["adapter_max_pct"] < raw["adapter_max_pct"]
    html = (rd / "report.html").read_text(encoding="utf-8")
    assert "QC decision" in html and "Provenance" in html and "not provide clinical" in html
    rec = hist.get(rd.name)
    assert rec["state"] == "done" and rec["overall"] == decision["overall"]


def test_pipeline_rejects_invalid_input(tmp_path, rules_file):
    bad = write_fastq(tmp_path / "bad.fq", [("r1", "ACGT", "III")])
    rd = run_pipeline(RunConfig("BAD", str(bad), rules_file=str(rules_file)), tmp_path / "runs")
    status = json.loads((rd / "status.json").read_text())
    assert status["state"] == "failed" and "validation failed" in status["error"]
    assert not (rd / "report.html").exists()


def test_api(tmp_path, monkeypatch):
    monkeypatch.setenv("NGSENTINEL_DATA", str(tmp_path / "data"))
    import ngsentinel.api as api

    api = importlib.reload(api)
    from fastapi.testclient import TestClient

    c = TestClient(api.app)
    assert c.get("/api/health").json()["status"] == "ok"
    assert "fastp" in c.get("/api/tools").json()

    rules = c.get("/api/rules").json()
    assert rules["custom"] is False
    assert c.put("/api/rules", json={"text": "rules: []"}).status_code == 422
    assert c.put("/api/rules", json={"text": rules["text"]}).json()["custom"] is True
    assert c.delete("/api/rules").json()["custom"] is False

    up = c.post("/api/uploads", files={"file": ("x.txt", b"hello")})
    assert up.status_code == 422
    demo = c.post("/api/demo-data?pairs=1000").json()
    assert demo["synthetic"] is True

    bad = c.post("/api/runs", json={"sample": "S", "r1": str(tmp_path / "nope.fq")})
    assert bad.status_code == 422
    run_id = c.post("/api/runs", json={"sample": "API demo", "r1": demo["r1"], "r2": demo["r2"], "engine": "native"}).json()["run_id"]
    for _ in range(900):  # tool detection (Java/MultiQC start-up) can take a while
        st = c.get(f"/api/runs/{run_id}").json()["status"]
        if st and st["state"] in ("done", "failed"):
            break
        time.sleep(0.2)
    assert st["state"] == "done", st
    detail = c.get(f"/api/runs/{run_id}").json()
    assert detail["files"]["report"] and detail["decision"]["overall"]
    assert c.get(f"/api/runs/{run_id}/metrics/processed").json()["summary"]["total_reads"] > 0
    assert c.get(f"/api/runs/{run_id}/files/report.html").status_code == 200
    assert c.get(f"/api/runs/{run_id}/files/..%2F..%2Fqc_rules.yaml").status_code == 404
    assert c.get("/api/runs/..%2Fx").status_code == 404
    assert any(r["run_id"] == run_id for r in c.get("/api/runs").json())
    assert c.delete(f"/api/runs/{run_id}").json()["deleted"] == run_id
