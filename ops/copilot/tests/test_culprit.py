from app import culprit


def dep(sha, at, files="", status="succeeded", bad=0, kind="deploy"):
    return {"sha": sha, "deployed_at": at, "files_changed": files, "status": status,
            "marked_bad": bad, "kind": kind, "commit_message": "", "image": ""}


def flat(lo, hi, value=0.0, step=5):
    return [(float(t), value) for t in range(lo, hi + 1, step)]


def test_find_onset_uses_first_of_three_consecutive_high_points():
    s = flat(-900, -90) + [(-85.0, 0.4), (-80.0, 0.4), (-75.0, 0.4)]
    on = culprit.find_onset(s, 0.0, 60)
    assert on["method"] == "series" and on["onset"] == -85.0 and on["baseline"] == 0.0


def test_single_spike_is_not_an_onset():
    s = flat(-900, 30)
    s[10] = (s[10][0], 0.9)
    assert culprit.find_onset(s, 0.0, 60)["method"] == "fallback"


def test_fallback_when_no_baseline_window():
    on = culprit.find_onset(flat(-60, 30, 0.4), 0.0, 60)
    assert on["method"] == "fallback" and on["onset"] == -60.0


def test_overlap_compares_basenames_and_ignores_unknown():
    deploys = [dep("a" * 7, -1000, "app/main.py"), dep("b" * 7, -100, "app/selection.py,README.md")]
    errs = [{"file": "selection.py", "ts_epoch": -80.0}, {"file": "unknown", "ts_epoch": -80.0}]
    a = culprit.analyze(flat(-900, -90) + flat(-85, 30, 0.4), 0.0, 60, errs, deploys)
    assert a["suspect_sha"] == "b" * 7 and a["overlap_files"] == ["selection.py"]
    assert a["error_files"] == ["selection.py"]


def test_failed_deploys_are_never_suspects_or_rollback_targets():
    deploys = [dep("a" * 7, -1000, ""), dep("b" * 7, -300, "app/x.py", status="failed")]
    a = culprit.analyze(flat(-900, -90) + flat(-85, 30, 0.4), 0.0, 60, [], deploys)
    assert a["suspect_sha"] == "a" * 7


def test_previous_good_skips_marked_bad_and_same_sha():
    suspect = dep("c" * 7, 0, "")
    deploys = [dep("a" * 7, -300, "", bad=1), dep("b" * 7, -200, ""), dep("c" * 7, -100, "")]
    assert culprit.previous_good(deploys, suspect)["sha"] == "b" * 7
    assert culprit.previous_good([dep("a" * 7, -300, "", bad=1)], suspect) is None


def test_allowlist_has_only_two_actions():
    assert culprit.ACTIONS == ("rollback_previous", "no_action")


def test_no_errors_available_is_stated_in_alternatives():
    deploys = [dep("a" * 7, -1000, ""), dep("b" * 7, -100, "app/x.py")]
    a = culprit.analyze(flat(-900, -90) + flat(-85, 30, 0.4), 0.0, 60, [], deploys)
    assert any("rests on timing alone" in t for t in a["alternatives"])
    assert a["confidence"] == "medium"
