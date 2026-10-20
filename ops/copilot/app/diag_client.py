from datetime import datetime

import httpx

from app import config


def fetch_recent_errors() -> tuple[list[dict], str]:
    """Return (error records with ts_epoch, note). An unreachable app is not fatal: E3 is just empty."""
    try:
        r = httpx.get(f"{config.settings.app_url}/internal/recent-errors", timeout=5)
        r.raise_for_status()
        records = r.json()["errors"]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return [], f"app diagnostics unreachable: {e}"
    for rec in records:
        try:
            rec["ts_epoch"] = datetime.fromisoformat(rec["ts"]).timestamp()
        except (KeyError, ValueError):
            rec["ts_epoch"] = None
    return records, ""
