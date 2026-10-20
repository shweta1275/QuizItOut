import httpx
import pytest

from app import actions, deploys, incidents, jenkins
from app.evidence import REPLAY_REF
from tests.conftest import replay_source

REASON = "KeyError in selection.py, release matches onset"


def make(name="bad_release", replay=True):
    return incidents.create_incident("HighErrorRate", REPLAY_REF, replay_source(name), is_replay=replay, replay_name=name)


def view_then(iid, seconds_ago):
    """Pretend the page was first opened `seconds_ago` seconds ago."""
    incidents.mark_viewed(iid)
    from app import db
    with db.session() as c:
        c.execute("UPDATE incidents SET first_viewed_at = first_viewed_at - ? WHERE id = ?", (seconds_ago, iid))


def test_reason_is_required_for_approve_and_reject():
    iid = make()
    view_then(iid, 60)
    for decision in ("approve", "reject"):
        out = actions.decide(iid, decision, "too short")
        assert not out.ok and "15" in out.error
    assert incidents.decisions_for(iid) == []


def test_fast_decision_is_challenged_then_recorded_with_flag():
    iid = make()
    incidents.mark_viewed(iid)
    out = actions.decide(iid, "reject", REASON)
    assert out.challenge and not out.ok and incidents.decisions_for(iid) == []
    assert actions.decide(iid, "reject", REASON, confirmed=True).ok
    d = incidents.decisions_for(iid)[0]
    assert d["confirmed_fast"] == 1 and d["seconds_to_decide"] < 10


def test_never_viewed_counts_as_fast():
    iid = make()
    assert actions.decide(iid, "reject", REASON).challenge


def test_slow_decision_needs_no_challenge_and_is_audited():
    iid = make()
    view_then(iid, 45)
    assert actions.decide(iid, "reject", REASON).ok
    d = incidents.decisions_for(iid)[0]
    assert d["decision"] == "reject" and d["reason"] == REASON and d["confirmed_fast"] == 0
    assert d["seconds_to_decide"] >= 45
    assert incidents.get_incident(iid)["status"] == "rejected"


def test_replay_approve_records_decision_but_never_calls_jenkins(monkeypatch):
    monkeypatch.setattr(jenkins, "trigger_rollback", lambda *a: pytest.fail("Jenkins must not be called"))
    iid = make()
    view_then(iid, 30)
    assert actions.decide(iid, "approve", REASON).ok
    assert incidents.get_incident(iid)["status"] == "rollback_skipped_replay"
    assert len(incidents.decisions_for(iid)) == 1


def test_decided_incident_cannot_be_decided_twice():
    iid = make()
    view_then(iid, 30)
    actions.decide(iid, "reject", REASON)
    assert "Already decided" in actions.decide(iid, "reject", REASON).error


def test_no_action_incident_cannot_be_approved():
    iid = make("no_recent_deploy")
    view_then(iid, 30)
    out = actions.decide(iid, "approve", REASON)
    assert not out.ok and "no rollback" in out.error


def test_unknown_decision_and_missing_incident():
    assert not actions.decide(12345, "approve", REASON).ok
    iid = make()
    assert not actions.decide(iid, "delete_everything", REASON).ok


def live_incident(monkeypatch, trigger):
    """A non-replay incident built on deploys in the DB, with Jenkins replaced by `trigger`."""
    deploys.record_deploy("aaaaaaa", files_changed="app/main.py", deployed_at=REPLAY_REF - 1500)
    deploys.record_deploy("bbbbbbb", files_changed="app/selection.py", deployed_at=REPLAY_REF - 150)

    class Live:  # real DB deploys, recorded series/errors
        def collect(self, alert_start):
            raw = replay_source("bad_release").collect(alert_start)
            raw.deploys = deploys.list_deploys()
            return raw

    monkeypatch.setattr(jenkins, "trigger_rollback", trigger)
    iid = incidents.create_incident("HighErrorRate", REPLAY_REF, Live())
    view_then(iid, 30)
    return iid


def test_live_approve_triggers_jenkins_marks_suspect_bad_and_callback_closes(monkeypatch):
    calls = []
    iid = live_incident(monkeypatch, lambda sha, i: calls.append((sha, i)))
    assert actions.decide(iid, "approve", REASON).ok
    assert calls == [("aaaaaaa", iid)]
    assert deploys.get_by_sha("bbbbbbb")["marked_bad"] == 1
    assert incidents.get_incident(iid)["status"] == "rollback_requested"
    assert actions.record_rollback_result(iid, "ok", "aaaaaaa")
    assert incidents.get_incident(iid)["status"] == "rollback_ok"


def test_jenkins_failure_keeps_decision_and_does_not_mark_bad(monkeypatch):
    def fail(sha, i):
        raise jenkins.JenkinsError("Jenkins answered HTTP 401")

    iid = live_incident(monkeypatch, fail)
    out = actions.decide(iid, "approve", REASON)
    assert out.ok and "not started" in out.error
    assert incidents.get_incident(iid)["status"] == "rollback_failed"
    assert deploys.get_by_sha("bbbbbbb")["marked_bad"] == 0 and len(incidents.decisions_for(iid)) == 1


def test_rollback_result_rules():
    iid = make()
    assert not actions.record_rollback_result(iid, "ok", "aaaaaaa")  # nothing pending
    assert not actions.record_rollback_result(999, "ok", "x")
    assert not actions.record_rollback_result(iid, "weird", "x")


def test_jenkins_client_validates_and_maps_errors(monkeypatch):
    with pytest.raises(jenkins.JenkinsError):
        jenkins.trigger_rollback("not-a-sha; rm -rf", 1)
    sent = {}

    class R:
        status_code = 201

    def fake_post(url, params, auth, timeout):
        sent.update(url=url, params=params, auth=auth)
        return R()

    monkeypatch.setattr(httpx, "post", fake_post)
    jenkins.trigger_rollback("aaaaaaa", 7)
    assert sent["url"].endswith("/job/quizitout-rollback/buildWithParameters")
    assert sent["params"] == {"ROLLBACK_TO": "aaaaaaa", "INCIDENT_ID": "7"} and sent["auth"] == ("u", "t")

    R.status_code = 403
    with pytest.raises(jenkins.JenkinsError, match="403"):
        jenkins.trigger_rollback("aaaaaaa", 7)

    def refuse(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "post", refuse)
    with pytest.raises(jenkins.JenkinsError, match="unreachable"):
        jenkins.trigger_rollback("aaaaaaa", 7)


def test_jenkins_needs_credentials(monkeypatch):
    import dataclasses

    from app import config
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, jenkins_token=""))
    with pytest.raises(jenkins.JenkinsError, match="not set"):
        jenkins.trigger_rollback("aaaaaaa", 1)
