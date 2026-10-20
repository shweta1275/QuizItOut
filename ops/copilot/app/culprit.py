"""Deterministic analysis: onset, suspect deploy, confidence, action. No LLM, no I/O.

All times are epoch seconds. A deploy is recorded by Jenkins AFTER its smoke test, so it can
land a little after the first errors; DEPLOY_SLACK_S allows for that.
"""

from statistics import median

ONSET_MARGIN = 0.05  # ratio must exceed baseline + 5 percentage points ...
ONSET_POINTS = 3  # ... for this many consecutive samples
BASELINE_GUARD_S = 30  # baseline = samples older than (alert_start - for - guard)
CANDIDATE_WINDOW_S = 3600
DEPLOY_SLACK_S = 120
HIGH_GAP_S = 900
MEDIUM_GAP_S = 300
ACTIONS = ("rollback_previous", "no_action")  # allowlist: the only things the copilot can propose


def find_onset(series: list[tuple[float, float]], alert_start: float, for_seconds: int) -> dict:
    fallback = {"onset": alert_start - for_seconds, "baseline": None, "method": "fallback"}
    cutoff = alert_start - for_seconds - BASELINE_GUARD_S
    quiet = [v for t, v in series if t <= cutoff]
    if not quiet:
        return fallback
    baseline = median(quiet)
    threshold = baseline + ONSET_MARGIN
    for i in range(len(series) - ONSET_POINTS + 1):
        window = series[i : i + ONSET_POINTS]
        if all(v > threshold for _, v in window):
            return {"onset": window[0][0], "baseline": baseline, "method": "series"}
    return {**fallback, "baseline": baseline}


def error_files(errors: list[dict], since: float, until: float) -> list[str]:
    """Basenames of files named in error records inside [since, until] (records carry `ts` epoch)."""
    files = []
    for e in errors:
        ts = e.get("ts_epoch")
        if ts is not None and not (since <= ts <= until):
            continue
        f = e.get("file")
        if f and f != "unknown" and f not in files:
            files.append(f)
    return files


def _basenames(files_changed: str) -> set[str]:
    return {p.strip().rsplit("/", 1)[-1] for p in files_changed.split(",") if p.strip()}


def candidates(deploys: list[dict], onset: float) -> list[dict]:
    ok = [
        d
        for d in deploys
        if d["status"] == "succeeded"
        and onset - CANDIDATE_WINDOW_S <= d["deployed_at"] <= onset + DEPLOY_SLACK_S
    ]
    return sorted(ok, key=lambda d: d["deployed_at"], reverse=True)


def previous_good(deploys: list[dict], suspect: dict) -> dict | None:
    earlier = [
        d
        for d in deploys
        if d["status"] == "succeeded"
        and d["deployed_at"] < suspect["deployed_at"]
        and d["sha"] != suspect["sha"]
        and not d.get("marked_bad")
    ]
    return max(earlier, key=lambda d: d["deployed_at"]) if earlier else None


def analyze(
    series: list[tuple[float, float]],
    alert_start: float,
    for_seconds: int,
    errors: list[dict],
    deploys: list[dict],
) -> dict:
    on = find_onset(series, alert_start, for_seconds)
    onset = on["onset"]
    files = error_files(errors, onset - 60, alert_start + 600)
    cands = candidates(deploys, onset)

    suspect = next((d for d in cands if _basenames(d["files_changed"]) & set(files)), None)
    if suspect is None and cands:
        suspect = cands[0]
    overlap = sorted(_basenames(suspect["files_changed"]) & set(files)) if suspect else []
    gap = max(0.0, onset - suspect["deployed_at"]) if suspect else None

    if suspect and overlap and gap <= HIGH_GAP_S:
        confidence = "high"
    elif suspect and not overlap and gap <= MEDIUM_GAP_S:
        confidence = "medium"
    else:
        confidence = "low"

    prev = previous_good(deploys, suspect) if suspect else None
    action = "rollback_previous" if confidence in ("high", "medium") and prev else "no_action"

    return {
        "onset": onset,
        "onset_method": on["method"],
        "baseline": on["baseline"],
        "error_files": files,
        "suspect_sha": suspect["sha"] if suspect else None,
        "suspect": suspect,
        "gap_s": gap,
        "overlap_files": overlap,
        "confidence": confidence,
        "previous_good_sha": prev["sha"] if prev else None,
        "action": action,
        "candidate_shas": [d["sha"] for d in cands],
        "alternatives": alternatives(suspect, overlap, files, cands, prev),
    }


def alternatives(suspect, overlap, files, cands, prev) -> list[str]:
    alts = []
    if suspect is None:
        alts.append(
            "No deploy was recorded in the hour before onset, so the cause is probably not a release "
            "(traffic, a dependency such as Ollama, or the environment)."
        )
    else:
        if not overlap and files:
            alts.append(
                f"The errors come from {', '.join(files)}, which release {suspect['sha']} did not modify, "
                "so the release may be a coincidence."
            )
        if not files:
            alts.append(
                "No error records were available, so file overlap could not be checked; "
                "the suspect rests on timing alone."
            )
        if len(cands) > 1:
            others = ", ".join(d["sha"] for d in cands if d["sha"] != suspect["sha"])
            alts.append(f"Other recent deploys in the window: {others}.")
        base = prev["sha"] if prev else "the previous version"
        alts.append(
            f"What would change my mind: errors that continue after rolling back to {base}, "
            "or errors in files this release did not touch."
        )
    return alts
