"""Error evidence for the incident copilot: a JSON log line plus an in-memory ring buffer.

Lab-only. The records hold the exception type, the innermost app/ file and line, and a
truncated message. Request bodies and uploaded content are never stored.
"""

import json
import sys
import traceback
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings

APP_DIR = str(Path(__file__).parent.resolve())
MAX_RECORDS = 100
MAX_MSG = 200

_records: deque = deque(maxlen=MAX_RECORDS)


def _innermost_app_frame(exc: BaseException):
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename.startswith(APP_DIR)]
    return frames[-1] if frames else None


def record_error(exc: BaseException, path: str) -> dict:
    frame = _innermost_app_frame(exc)
    rec = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "level": "ERROR",
        "version": settings.app_version,
        "msg": str(exc)[:MAX_MSG],
        "exc": f"{type(exc).__name__}: {exc}"[:MAX_MSG],
        "file": Path(frame.filename).name if frame else "unknown",
        "line": frame.lineno if frame else 0,
        "path": path,
    }
    _records.append(rec)
    print(json.dumps(rec), file=sys.stdout, flush=True)
    return rec


def recent_errors() -> list[dict]:
    return [
        {k: r[k] for k in ("ts", "exc", "file", "line", "path", "msg")} for r in _records
    ]


def clear() -> None:
    _records.clear()
