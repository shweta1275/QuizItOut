"""Replay gate: every recorded incident must produce exactly the expected analysis.

This is a regression test for the DETERMINISTIC analyzer and the report validator.
It does not measure LLM quality.
"""

import pytest

from app import culprit, incidents, report
from app.evidence import REPLAY_REF
from tests.conftest import INCIDENTS, load_incident, replay_source

NAMES = sorted(p.stem for p in INCIDENTS.glob("*.json"))


def analyze_recorded(name):
    src = replay_source(name)
    raw = src.collect(REPLAY_REF)
    analysis = culprit.analyze(raw.series, REPLAY_REF, 60, raw.errors, raw.deploys)
    return raw, analysis


def test_at_least_eight_recorded_incidents():
    assert len(NAMES) >= 8


@pytest.mark.parametrize("name", NAMES)
def test_recorded_incident_matches_expected(name):
    exp = load_incident(name)["expected"]
    _, a = analyze_recorded(name)
    assert a["suspect_sha"] == exp["suspect"]
    assert a["confidence"] == exp["confidence"]
    assert a["action"] == exp["action"]
    assert a["previous_good_sha"] == exp["previous_good"]
    if "onset_method" in exp:
        assert a["onset_method"] == exp["onset_method"]


@pytest.mark.parametrize("name", NAMES)
def test_template_report_always_validates(name):
    raw, a = analyze_recorded(name)
    ev = report.build_evidence(a, raw.series, raw.rate, raw.errors, raw.deploys)
    assert report.validate_report(report.template_report(a, ev), ev) == []


@pytest.mark.parametrize("name", NAMES)
def test_incident_pipeline_stores_same_result(name):
    exp = load_incident(name)["expected"]
    src = replay_source(name)
    iid = incidents.create_incident("HighErrorRate", REPLAY_REF, src, is_replay=True, replay_name=name)
    inc = incidents.get_incident(iid)
    assert (inc["suspect_sha"], inc["confidence"], inc["action"]) == (
        exp["suspect"], exp["confidence"], exp["action"]
    )
    assert inc["report_source"] == "template" and inc["is_replay"] == 1


def test_log_injection_does_not_change_the_decision():
    _, injected = analyze_recorded("log_injection")
    _, plain = analyze_recorded("bad_release")
    for key in ("suspect_sha", "confidence", "action", "previous_good_sha"):
        assert injected[key] == plain[key]
    raw, a = analyze_recorded("log_injection")
    ev = report.build_evidence(a, raw.series, raw.rate, raw.errors, raw.deploys)
    assert "Ignore previous instructions" in report.e3_text(ev)  # present as data, not obeyed


def test_wrong_proposal_case_names_the_unmodified_file():
    _, a = analyze_recorded("chaos_after_docs_deploy")
    assert a["overlap_files"] == [] and a["error_files"] == ["chaos.py"]
    assert any("chaos.py" in alt and "did not modify" in alt for alt in a["alternatives"])
