import dataclasses

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, deploys, diag_client, evidence, incidents, jenkins, prom
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_record_deploy_validates_sha_and_lists(client):
    assert client.post("/deploys", data={"sha": "bad; rm"}).status_code == 422
    assert client.post("/deploys", data={"sha": "abc1234", "kind": "weird"}).status_code == 422
    r = client.post("/deploys", data={"sha": "abc1234", "files_changed": "app/a.py", "commit_message": "m"})
    assert r.status_code == 200
    assert client.get("/deploys").json()[0]["sha"] == "abc1234"
    assert "abc1234" in client.get("/").text


def test_replay_creates_incident_page_with_banner_and_badge(client):
    r = client.post("/dev/replay/bad_release")
    assert r.status_code == 200
    page = client.get(r.json()["url"]).text
    assert "Replay of a recorded incident" in page and "bbbbbbb" in page and "Template report" in page
    assert "Approve rollback" in page


def test_replay_disabled_unknown_and_traversal(client, monkeypatch):
    assert client.post("/dev/replay/nope").status_code == 404
    assert client.post("/dev/replay/..%2Fapp%2Fmain").status_code == 404
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, enable_replay=False))
    assert client.post("/dev/replay/bad_release").status_code == 404


def test_approval_flow_over_http(client, monkeypatch):
    monkeypatch.setattr(jenkins, "trigger_rollback", lambda *a: pytest.fail("replay must not call Jenkins"))
    iid = client.post("/dev/replay/bad_release").json()["id"]
    client.get(f"/incidents/{iid}")  # first view
    short = client.post(f"/incidents/{iid}/approve", data={"reason": "short"})
    assert "at least 15" in short.text
    fast = client.post(f"/incidents/{iid}/approve", data={"reason": "reason that is long enough"})
    assert "under 10 seconds" in fast.text and incidents.decisions_for(iid) == []
    ok = client.post(f"/incidents/{iid}/approve", data={"reason": "reason that is long enough", "confirm": "yes"},
                     follow_redirects=False)
    assert ok.status_code == 303
    page = client.get(f"/incidents/{iid}").text
    assert "rollback_skipped_replay" in page and "reason that is long enough" in page
    assert client.post(f"/incidents/{iid}/bogus", data={"reason": "x" * 20}).status_code == 404


def test_html_escapes_untrusted_log_text(client):
    iid = incidents.create_incident(
        "HighErrorRate", evidence.REPLAY_REF,
        type("S", (), {"collect": lambda self, t: _evil()})(), is_replay=True, replay_name="x")
    assert "<script>alert(1)</script>" not in client.get(f"/incidents/{iid}").text


def _evil():
    raw = evidence.ReplaySource(__import__("tests.conftest", fromlist=["x"]).load_incident("bad_release")).collect(evidence.REPLAY_REF)
    raw.errors[0]["msg"] = "<script>alert(1)</script>"
    raw.errors[0]["exc"] = "<script>alert(1)</script>"
    return raw


def test_rollback_result_endpoint(client):
    assert client.post("/incidents/999/rollback-result", data={"status": "ok"}).status_code == 404


def test_incident_json_and_missing(client):
    iid = client.post("/dev/replay/bad_release").json()["id"]
    assert client.get(f"/incidents/{iid}/json").json()["suspect_sha"] == "bbbbbbb"
    assert client.get("/incidents/999").status_code == 404
    assert client.get("/incidents/999/json").status_code == 404


def test_alert_webhook_creates_one_incident_and_resolves(client, monkeypatch):
    class Src:
        def collect(self, alert_start):
            return evidence.ReplaySource(__import__("tests.conftest", fromlist=["x"]).load_incident("bad_release")).collect(alert_start)

    monkeypatch.setattr("app.main.LiveSource", Src)
    body = {"alerts": [{"status": "firing", "labels": {"alertname": "HighErrorRate"},
                        "startsAt": "2026-10-20T10:00:00.123456789Z"}]}
    first = client.post("/alert", json=body).json()["created"]
    second = client.post("/alert", json=body).json()["created"]
    assert len(first) == 1 and second == []  # repeated notifications do not duplicate
    client.post("/alert", json={"alerts": [{"status": "resolved", "labels": {"alertname": "HighErrorRate"}}]})
    assert incidents.get_incident(first[0])["alert_resolved_at"] is not None
    assert len(client.post("/alert", json=body).json()["created"]) == 1  # new firing after resolve
    assert client.post("/alert", json={"alerts": [{"status": "firing", "startsAt": "garbage"}]}).status_code == 200


def test_live_source_survives_unreachable_prometheus_and_app(monkeypatch):
    def refuse(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", refuse)
    raw = evidence.LiveSource().collect(0.0)
    assert raw.series == [] and "Prometheus unreachable" in raw.note and "app diagnostics unreachable" in raw.note
    iid = incidents.create_incident("HighErrorRate", 1000.0, evidence.LiveSource())
    inc = incidents.get_incident(iid)
    assert inc["action"] == "no_action" and inc["evidence"]["E3"]["note"]


def test_prom_and_diag_clients_parse_responses(monkeypatch):
    class P:
        def raise_for_status(self): ...
        def json(self):
            return {"data": {"result": [{"values": [[1, "0.1"], [2, "NaN"], [3, "0.4"]]}]}}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: P())
    assert prom.query_range("x", 0, 10) == [(1.0, 0.1), (3.0, 0.4)]
    ser, rate = prom.ratio_and_rate(end=100.0)
    assert ser == rate

    class D:
        def raise_for_status(self): ...
        def json(self):
            return {"errors": [{"ts": "2026-10-20T10:00:00+00:00", "file": "a.py"}, {"ts": "bad"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: D())
    recs, note = diag_client.fetch_recent_errors()
    assert note == "" and recs[0]["ts_epoch"] > 0 and recs[1]["ts_epoch"] is None

    class Empty(P):
        def json(self): return {"data": {"result": []}}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Empty())
    assert prom.query_range("x", 0, 10) == []


def test_record_deploy_helper_rejects_bad_input():
    with pytest.raises(ValueError):
        deploys.record_deploy("zz")
