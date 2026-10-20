from fastapi.testclient import TestClient

from app import main as main_module

client = TestClient(main_module.app)


def test_chaos_is_404_when_disabled():
    assert client.post("/admin/chaos", json={"fail_rate": 0.5}).status_code == 404


def test_fail_rate_bounds_are_rejected(lab_mode):
    assert client.post("/admin/chaos", json={"fail_rate": 1.5}).status_code == 422
    assert client.post("/admin/chaos", json={"fail_rate": -0.1}).status_code == 422


def test_rate_one_fails_sample_and_rate_zero_restores_it(lab_mode):
    assert client.post("/admin/chaos", json={"fail_rate": 1.0}).json() == {"fail_rate": 1.0}
    assert client.get("/api/quiz/sample?count=2").status_code == 500
    client.post("/admin/chaos", json={"fail_rate": 0.0})
    assert client.get("/api/quiz/sample?count=2").status_code == 200


def test_chaos_failure_leaves_chaos_py_as_evidence(lab_mode):
    client.post("/admin/chaos", json={"fail_rate": 1.0})
    client.get("/api/quiz/sample?count=2")
    err = client.get("/internal/recent-errors").json()["errors"][-1]
    assert err["file"] == "chaos.py" and err["exc"].startswith("UpstreamUnavailable")
