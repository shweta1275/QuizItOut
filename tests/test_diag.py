import json

from fastapi.testclient import TestClient

from app import chaos, diag
from app import main as main_module

client = TestClient(main_module.app)


def _boom():
    raise KeyError("count")


def test_record_has_expected_fields_and_innermost_app_frame(lab_mode, capsys):
    try:
        chaos._fail_rate = 1.0
        chaos.maybe_fail()
    except chaos.UpstreamUnavailable as exc:
        rec = diag.record_error(exc, "/api/quiz/sample")
    assert rec["file"] == "chaos.py" and rec["line"] > 0
    assert rec["exc"].startswith("UpstreamUnavailable") and rec["version"] == "testsha"
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert set(line) >= {"ts", "level", "version", "msg", "exc", "file", "line", "path"}


def test_error_outside_app_has_unknown_file(lab_mode):
    try:
        _boom()
    except KeyError as exc:
        rec = diag.record_error(exc, "/x")
    assert rec["file"] == "unknown" and rec["line"] == 0


def test_ring_buffer_is_capped_at_100(lab_mode):
    for i in range(150):
        diag.record_error(ValueError(str(i)), "/x")
    errors = diag.recent_errors()
    assert len(errors) == 100 and errors[0]["msg"] == "50" and errors[-1]["msg"] == "149"


def test_message_is_truncated_to_200(lab_mode):
    diag.record_error(ValueError("x" * 500), "/x")
    assert len(diag.recent_errors()[-1]["msg"]) == 200


def test_endpoint_lists_errors_when_enabled(lab_mode):
    diag.record_error(ValueError("bad"), "/api/quiz/sample")
    body = client.get("/internal/recent-errors").json()
    assert body["version"] == "testsha"
    assert set(body["errors"][0]) == {"ts", "exc", "file", "line", "path", "msg"}


def test_endpoint_is_404_when_disabled():
    assert client.get("/internal/recent-errors").status_code == 404
