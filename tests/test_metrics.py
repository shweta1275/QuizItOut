import dataclasses

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app import main as main_module
from app import metrics

client = TestClient(main_module.app)


def _count(path, status, method="GET", version="testsha"):
    labels = {"method": method, "path": path, "status": status, "version": version}
    return REGISTRY.get_sample_value("http_requests_total", labels) or 0.0


def test_counter_increments_with_route_template_and_version(lab_mode):
    before = _count("/health", "200")
    client.get("/health")
    assert _count("/health", "200") == before + 1


def test_path_label_is_template_not_raw_url(lab_mode):
    before = _count("/api/quiz/sample", "200")
    client.get("/api/quiz/sample?count=1")
    client.get("/api/quiz/sample?count=2")
    assert _count("/api/quiz/sample", "200") == before + 2


def test_metrics_endpoint_is_not_counted_and_has_text_format(lab_mode):
    client.get("/health")
    first = client.get("/metrics")
    assert first.status_code == 200
    assert "http_requests_total{" in first.text and 'version="testsha"' in first.text
    client.get("/metrics")
    assert "/metrics" not in client.get("/metrics").text.split("http_requests_total")[-1]
    assert REGISTRY.get_sample_value(
        "http_requests_total",
        {"method": "GET", "path": "/metrics", "status": "200", "version": "testsha"},
    ) is None


def test_unmatched_path_becomes_other(lab_mode):
    before = _count("other", "404")
    assert client.get("/definitely/not/here").status_code == 404
    assert _count("other", "404") == before + 1


def test_unhandled_error_is_counted_as_500_with_json_body(lab_mode, monkeypatch):
    monkeypatch.setattr(
        metrics,
        "diag",
        type("D", (), {"record_error": staticmethod(lambda exc, path: None)}),
    )
    monkeypatch.setattr(
        main_module,
        "pick_questions",
        lambda q, p: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    before = _count("/api/quiz/sample", "500")
    r = client.get("/api/quiz/sample")
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal Server Error"}
    assert "Traceback" not in r.text
    assert _count("/api/quiz/sample", "500") == before + 1


def test_version_comes_from_settings(monkeypatch):
    monkeypatch.setattr(
        main_module, "settings", dataclasses.replace(main_module.settings, app_version="abc1234")
    )
    assert client.get("/health").json()["version"] == "abc1234"
