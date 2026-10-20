import math
import time

import httpx

from app import config

RATIO_QUERY = (
    '(sum(rate(http_requests_total{status=~"5.."}[1m])) or vector(0))'
    " / sum(rate(http_requests_total[1m]))"
)
RATE_QUERY = "sum(rate(http_requests_total[1m]))"
STEP_S = 5


def query_range(expr: str, start: float, end: float, step: int = STEP_S) -> list[tuple[float, float]]:
    r = httpx.get(
        f"{config.settings.prometheus_url}/api/v1/query_range",
        params={"query": expr, "start": start, "end": end, "step": step},
        timeout=10,
    )
    r.raise_for_status()
    result = r.json()["data"]["result"]
    if not result:
        return []
    points = [(float(t), float(v)) for t, v in result[0]["values"]]
    return [(t, v) for t, v in points if not math.isnan(v)]  # drop NaN (no traffic in the window)


def ratio_and_rate(end: float | None = None) -> tuple[list, list]:
    end = end or time.time()
    start = end - config.settings.lookback_seconds
    return query_range(RATIO_QUERY, start, end), query_range(RATE_QUERY, start, end)
