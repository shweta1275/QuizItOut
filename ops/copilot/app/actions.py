"""Human decisions. Approval resists rubber-stamping: written reason, fast-click challenge, audit row."""

import time
from dataclasses import dataclass

from app import config, db, deploys, incidents, jenkins


@dataclass
class Outcome:
    ok: bool
    error: str = ""
    challenge: bool = False


def decide(incident_id: int, decision: str, reason: str, confirmed: bool = False, now: float | None = None) -> Outcome:
    now = now if now is not None else time.time()
    s = config.settings
    inc = incidents.get_incident(incident_id)
    if inc is None:
        return Outcome(False, "Incident not found")
    if decision not in ("approve", "reject"):
        return Outcome(False, "Unknown decision")
    if inc["status"] != "awaiting_decision":
        return Outcome(False, f"Already decided (status: {inc['status']})")
    reason = reason.strip()
    if len(reason) < s.min_reason_chars:
        return Outcome(False, f"Write a reason of at least {s.min_reason_chars} characters.")
    if decision == "approve" and inc["action"] != "rollback_previous":
        return Outcome(False, "This incident proposes no rollback; you can only reject (close) it.")

    viewed = inc["first_viewed_at"]
    seconds = max(0.0, now - viewed) if viewed else 0.0
    fast = seconds < s.fast_decision_seconds
    if fast and not confirmed:
        return Outcome(False, challenge=True)

    with db.session() as conn:
        conn.execute(
            "INSERT INTO decisions (incident_id, decision, reason, seconds_to_decide, confirmed_fast, decided_at)"
            " VALUES (?,?,?,?,?,?)",
            (incident_id, decision, reason, round(seconds, 1), int(fast), now),
        )
    if decision == "reject":
        _set_status(incident_id, "rejected")
        return Outcome(True)

    if inc["is_replay"]:  # recorded incident: keep the decision, never touch Jenkins
        _set_status(incident_id, "rollback_skipped_replay", "Replay: Jenkins was not called.")
        return Outcome(True)
    try:
        jenkins.trigger_rollback(inc["previous_good_sha"], incident_id)
    except jenkins.JenkinsError as e:
        _set_status(incident_id, "rollback_failed", str(e))
        return Outcome(True, error=f"Decision saved, but the rollback was not started: {e}")
    deploys.mark_bad(inc["suspect_sha"])
    _set_status(incident_id, "rollback_requested", f"Rollback job started for {inc['previous_good_sha']}.")
    return Outcome(True)


def record_rollback_result(incident_id: int, status: str, sha: str) -> bool:
    inc = incidents.get_incident(incident_id)
    if inc is None or status not in ("ok", "failed"):
        return False
    if inc["status"] not in ("rollback_requested", "rollback_failed"):
        return False
    _set_status(incident_id, f"rollback_{status}", f"Rollback job finished: {status} (sha {sha[:40]}).")
    return True


def _set_status(incident_id: int, status: str, detail: str = "") -> None:
    with db.session() as conn:
        conn.execute(
            "UPDATE incidents SET status = ?, rollback_detail = ? WHERE id = ?", (status, detail, incident_id)
        )
