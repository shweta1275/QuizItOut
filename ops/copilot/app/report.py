"""Evidence bundle E1-E4, the deterministic template report, and the report validator.

The validator is what makes an LLM report safe to show: every claim must cite existing
evidence IDs, quotes must appear verbatim in the error records, and any SHA must be a
deploy the copilot actually knows. The ACTION is never read from a report.
"""

import re
from collections import Counter
from datetime import datetime, timezone
from statistics import mean

SHA_TOKEN = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b")
EVIDENCE_REF = re.compile(r"\bE\d+\b")


def fmt_ts(epoch: float | None) -> str:
    if epoch is None:
        return "unknown"
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%H:%M:%S UTC")


def build_evidence(analysis: dict, series, rate_series, errors: list[dict], deploys: list[dict]) -> dict:
    onset = analysis["onset"]
    ratios = [v for _, v in series]
    before = [v for t, v in rate_series if t < onset]
    after = [v for t, v in rate_series if t >= onset]
    last_five = sorted(deploys, key=lambda d: d["deployed_at"], reverse=True)[:5]
    return {
        "E1": {
            "title": "5xx error ratio (Prometheus)",
            "baseline": analysis["baseline"],
            "current": ratios[-1] if ratios else None,
            "peak": max(ratios) if ratios else None,
            "onset": onset,
            "onset_method": analysis["onset_method"],
        },
        "E2": {
            "title": "Request rate in req/s (Prometheus)",
            "before": round(mean(before), 2) if before else None,
            "after": round(mean(after), 2) if after else None,
        },
        "E3": {
            "title": "Recent application errors (app /internal/recent-errors)",
            "errors": [
                {k: e.get(k) for k in ("ts", "exc", "file", "line", "path", "msg")} for e in errors[-20:]
            ],
            "count": len(errors),
        },
        "E4": {
            "title": "Last five deploys (Jenkins Record deploy)",
            "deploys": [
                {
                    "sha": d["sha"],
                    "kind": d["kind"],
                    "deployed_at": d["deployed_at"],
                    "files_changed": d["files_changed"],
                    "commit_message": d["commit_message"],
                    "marked_bad": bool(d.get("marked_bad")),
                }
                for d in last_five
            ],
        },
    }


def e3_text(evidence: dict) -> str:
    return "\n".join(
        f"{e.get('exc')} {e.get('msg')} {e.get('file')}:{e.get('line')} {e.get('path')}"
        for e in evidence["E3"]["errors"]
    )


def known_shas(evidence: dict) -> set[str]:
    return {d["sha"] for d in evidence["E4"]["deploys"]}


def _pct(v: float | None) -> str:
    return "unknown" if v is None else f"{v * 100:.1f}%"


def template_report(analysis: dict, evidence: dict) -> dict:
    e1, e2, e3, e4 = (evidence[k] for k in ("E1", "E2", "E3", "E4"))
    claims = [
        {
            "text": (
                f"The 5xx error ratio rose from {_pct(e1['baseline'])} (baseline) to "
                f"{_pct(e1['current'])} (peak {_pct(e1['peak'])}); onset at {fmt_ts(e1['onset'])}."
            ),
            "evidence": ["E1"],
            "quote": None,
        }
    ]
    if e2["before"] is not None and e2["after"] is not None:
        steady = e2["before"] == 0 or abs(e2["after"] - e2["before"]) / e2["before"] <= 0.25
        claims.append(
            {
                "text": (
                    f"Request rate was {e2['before']} req/s before and {e2['after']} req/s after onset: "
                    + ("traffic volume did not change, so this is not a load spike." if steady
                       else "traffic volume changed, which may be a factor.")
                ),
                "evidence": ["E2"],
                "quote": None,
            }
        )
    if e3["errors"]:
        top, n = Counter(e["exc"] for e in e3["errors"]).most_common(1)[0]
        rec = next(e for e in e3["errors"] if e["exc"] == top)
        claims.append(
            {
                "text": f"{n} of the last {len(e3['errors'])} error records are `{top}` in {rec['file']} line {rec['line']}.",
                "evidence": ["E3"],
                "quote": top,
            }
        )
    else:
        claims.append(
            {"text": "No error records were available from the application.", "evidence": ["E3"], "quote": None}
        )
    if analysis["suspect_sha"]:
        d = next(x for x in e4["deploys"] if x["sha"] == analysis["suspect_sha"])
        overlap = (
            f"It changed {', '.join(analysis['overlap_files'])}, which the errors name."
            if analysis["overlap_files"]
            else "It did not change any file named in the errors."
        )
        claims.append(
            {
                "text": (
                    f"Suspect deploy {d['sha']} ('{d['commit_message'][:80]}') was recorded "
                    f"{int(analysis['gap_s'])} s before onset. {overlap}"
                ),
                "evidence": ["E4", "E3"],
                "quote": None,
            }
        )
    else:
        claims.append(
            {"text": "No deploy was recorded in the hour before onset.", "evidence": ["E4"], "quote": None}
        )
    if analysis["action"] == "rollback_previous":
        action_text = f"Proposed action: roll back to {analysis['previous_good_sha']}."
    else:
        action_text = "Proposed action: none (no safe rollback target or confidence too low)."
    claims.append({"text": action_text, "evidence": ["E4"], "quote": None})

    return {
        "summary": (
            f"Confidence {analysis['confidence']}. "
            + (
                f"Suspect release {analysis['suspect_sha']}."
                if analysis["suspect_sha"]
                else "No suspect release."
            )
        ),
        "claims": claims,
    }


def validate_report(report, evidence: dict) -> list[str]:
    """Return a list of problems; empty means the report may be shown."""
    problems: list[str] = []
    if not isinstance(report, dict):
        return ["report is not an object"]
    summary = report.get("summary")
    claims = report.get("claims")
    if not isinstance(summary, str) or not summary.strip():
        problems.append("missing summary")
    if not isinstance(claims, list) or not claims:
        return problems + ["no claims"]
    texts = [summary or ""]
    log_text = e3_text(evidence)
    shas = known_shas(evidence)
    for i, c in enumerate(claims):
        if not isinstance(c, dict) or not isinstance(c.get("text"), str) or not c["text"].strip():
            problems.append(f"claim {i}: missing text")
            continue
        texts.append(c["text"])
        ev = c.get("evidence")
        if not isinstance(ev, list) or not ev:
            problems.append(f"claim {i}: no evidence IDs")
        elif any(x not in evidence for x in ev):
            problems.append(f"claim {i}: unknown evidence ID in {ev}")
        quote = c.get("quote")
        if quote and quote not in log_text:
            problems.append(f"claim {i}: quote not found verbatim in E3")
    joined = "\n".join(texts)
    for ref in EVIDENCE_REF.findall(joined):
        if ref not in evidence:
            problems.append(f"text mentions unknown evidence {ref}")
    for sha in SHA_TOKEN.findall(joined):
        if sha not in shas:
            problems.append(f"text mentions unknown sha {sha}")
    return problems


def clean_report(report: dict) -> dict:
    """Keep only the fields the page renders (drops anything extra the model added, e.g. an 'action')."""
    return {
        "summary": report["summary"].strip(),
        "claims": [
            {"text": c["text"].strip(), "evidence": list(c["evidence"]), "quote": c.get("quote") or None}
            for c in report["claims"]
        ],
    }
