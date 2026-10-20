import json
import time

from app import config, culprit, db, llm, report


def create_incident(
    alert_name: str,
    alert_start: float,
    source,
    *,
    is_replay: bool = False,
    replay_name: str | None = None,
) -> int:
    """Collect evidence, run the deterministic analysis, store a TEMPLATE report. LLM comes later."""
    raw = source.collect(alert_start)
    analysis = culprit.analyze(
        raw.series, alert_start, config.settings.alert_for_seconds, raw.errors, raw.deploys
    )
    evidence = report.build_evidence(analysis, raw.series, raw.rate, raw.errors, raw.deploys)
    if raw.note:
        evidence["E3"]["note"] = raw.note
    tmpl = report.template_report(analysis, evidence)
    with db.session() as conn:
        cur = conn.execute(
            "INSERT INTO incidents (alert_name, created_at, alert_start, status, suspect_sha, confidence,"
            " action, previous_good_sha, analysis_json, evidence_json, report_json, report_source,"
            " report_note, is_replay, replay_name) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                alert_name,
                time.time(),
                alert_start,
                "awaiting_decision",
                analysis["suspect_sha"],
                analysis["confidence"],
                analysis["action"],
                analysis["previous_good_sha"],
                json.dumps(analysis, default=str),
                json.dumps(evidence, default=str),
                json.dumps(tmpl),
                "template",
                "",
                int(is_replay),
                replay_name,
            ),
        )
        return cur.lastrowid


def get_incident(incident_id: int) -> dict | None:
    with db.session() as conn:
        row = conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return db.incident_row(row)


def list_incidents(limit: int = 50) -> list[dict]:
    with db.session() as conn:
        rows = conn.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT ?", (limit,))
        return [db.incident_row(r) for r in rows]


def decisions_for(incident_id: int) -> list[dict]:
    with db.session() as conn:
        rows = conn.execute("SELECT * FROM decisions WHERE incident_id = ? ORDER BY id", (incident_id,))
        return [dict(r) for r in rows]


def upgrade_report(incident_id: int, client=None) -> str:
    """Try the LLM narrative. Valid -> badge 'llm'. Anything else -> keep the template and say why."""
    inc = get_incident(incident_id)
    if inc is None:
        return "missing"
    rep, note = llm.narrate(inc["analysis"], inc["evidence"], client)
    with db.session() as conn:
        if rep is not None:
            conn.execute(
                "UPDATE incidents SET report_json = ?, report_source = 'llm', report_note = '' WHERE id = ?",
                (json.dumps(rep), incident_id),
            )
            return "llm"
        conn.execute("UPDATE incidents SET report_note = ? WHERE id = ?", (note, incident_id))
    return "template"


def mark_viewed(incident_id: int) -> None:
    with db.session() as conn:
        conn.execute(
            "UPDATE incidents SET first_viewed_at = ? WHERE id = ? AND first_viewed_at IS NULL",
            (time.time(), incident_id),
        )


def find_open_for_alert(alert_name: str) -> dict | None:
    with db.session() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE alert_name = ? AND alert_resolved_at IS NULL AND is_replay = 0"
            " ORDER BY id DESC LIMIT 1",
            (alert_name,),
        ).fetchone()
        return db.incident_row(row)


def mark_alert_resolved(alert_name: str) -> None:
    with db.session() as conn:
        conn.execute(
            "UPDATE incidents SET alert_resolved_at = ? WHERE alert_name = ? AND alert_resolved_at IS NULL"
            " AND is_replay = 0",
            (time.time(), alert_name),
        )
