import pytest

from app import culprit, report
from app.evidence import REPLAY_REF
from tests.conftest import replay_source


@pytest.fixture
def bundle():
    raw = replay_source("bad_release").collect(REPLAY_REF)
    a = culprit.analyze(raw.series, REPLAY_REF, 60, raw.errors, raw.deploys)
    return a, report.build_evidence(a, raw.series, raw.rate, raw.errors, raw.deploys)


def good():
    return {
        "summary": "Release bbbbbbb likely broke the sample endpoint.",
        "claims": [{"text": "KeyError appears repeatedly.", "evidence": ["E3"], "quote": "KeyError: 'count'"}],
    }


def test_good_report_passes(bundle):
    assert report.validate_report(good(), bundle[1]) == []


@pytest.mark.parametrize(
    "mutate,expect",
    [
        (lambda r: r["claims"][0].update(evidence=[]), "no evidence"),
        (lambda r: r["claims"][0].update(evidence=["E9"]), "unknown evidence"),
        (lambda r: r["claims"][0].update(quote="TypeError: invented"), "quote"),
        (lambda r: r.update(summary="Release deadbe5 broke it."), "unknown sha"),
        (lambda r: r["claims"][0].update(text="See E7 for details."), "unknown evidence E7"),
        (lambda r: r.update(summary=""), "missing summary"),
        (lambda r: r.update(claims=[]), "no claims"),
    ],
)
def test_bad_reports_are_rejected(bundle, mutate, expect):
    r = good()
    mutate(r)
    assert any(expect in p for p in report.validate_report(r, bundle[1]))


def test_non_object_is_rejected(bundle):
    assert report.validate_report("nope", bundle[1])


def test_known_sha_is_allowed(bundle):
    r = good()
    r["claims"][0]["text"] = "Deploy aaaaaaa was the previous version."
    assert report.validate_report(r, bundle[1]) == []


def test_clean_report_drops_extra_fields_such_as_action(bundle):
    r = good()
    r["action"] = "delete_everything"
    r["claims"][0]["junk"] = 1
    cleaned = report.clean_report(r)
    assert "action" not in cleaned and "junk" not in cleaned["claims"][0]


def test_template_report_cites_evidence_and_names_action(bundle):
    t = report.template_report(*bundle)
    assert all(c["evidence"] for c in t["claims"])
    assert "roll back to aaaaaaa" in t["claims"][-1]["text"]
