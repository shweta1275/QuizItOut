"""Where the raw evidence comes from: the live stack, or a recorded incident (replay)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from app import deploys as deploys_mod
from app import diag_client, prom

REPLAY_REF = 1_800_000_000.0  # replay incidents use times relative to this "alert start"


@dataclass
class Raw:
    series: list
    rate: list
    errors: list
    deploys: list
    note: str = ""
    extra: dict = field(default_factory=dict)


class LiveSource:
    def collect(self, alert_start: float) -> Raw:
        notes = []
        try:
            series, rate = prom.ratio_and_rate()
        except (httpx.HTTPError, KeyError, ValueError) as e:
            series, rate = [], []
            notes.append(f"Prometheus unreachable: {e}")
        errors, note = diag_client.fetch_recent_errors()
        if note:
            notes.append(note)
        return Raw(series, rate, errors, deploys_mod.list_deploys(200), "; ".join(notes))


class ReplaySource:
    """Same shape as live evidence, built from tests/incidents/<name>.json (no Prometheus, no app)."""

    def __init__(self, spec: dict):
        self.spec = spec

    @property
    def alert_start(self) -> float:
        return REPLAY_REF

    def collect(self, alert_start: float) -> Raw:
        s = self.spec
        lo, hi = s["series"]["span"]
        step = s["series"].get("step", 5)
        ts = [REPLAY_REF + t for t in range(lo, hi + 1, step)]
        onset = REPLAY_REF + s["series"]["onset"]
        series = [(t, s["series"]["bad"] if t >= onset else s["series"]["quiet"]) for t in ts]
        rate = [(t, float(s.get("rate", 5.0))) for t in ts]
        errors = []
        for e in s.get("errors", []):
            t = REPLAY_REF + e["at"]
            errors.append(
                {
                    "ts": datetime.fromtimestamp(t, UTC).isoformat(timespec="seconds"),
                    "ts_epoch": t,
                    **{k: e[k] for k in ("exc", "file", "line", "path", "msg")},
                }
            )
        deploys = [
            {
                "sha": d["sha"],
                "image": "replay",
                "commit_message": d.get("commit_message", ""),
                "files_changed": d.get("files_changed", ""),
                "status": d.get("status", "succeeded"),
                "kind": d.get("kind", "deploy"),
                "deployed_at": REPLAY_REF + d["at"],
                "marked_bad": d.get("marked_bad", 0),
            }
            for d in s["deploys"]
        ]
        return Raw(series, rate, errors, deploys)
