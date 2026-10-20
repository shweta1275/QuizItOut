import re
import time

from app import db

SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
KINDS = {"deploy", "rollback"}
STATUSES = {"succeeded", "failed"}


def record_deploy(
    sha: str,
    image: str = "",
    commit_message: str = "",
    files_changed: str = "",
    status: str = "succeeded",
    kind: str = "deploy",
    deployed_at: float | None = None,
) -> int:
    if not SHA_RE.match(sha):
        raise ValueError("sha must be 7-40 lowercase hex characters")
    if kind not in KINDS or status not in STATUSES:
        raise ValueError("bad kind or status")
    with db.session() as conn:
        cur = conn.execute(
            "INSERT INTO deploys (sha, image, commit_message, files_changed, status, kind, deployed_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (sha, image, commit_message[:300], files_changed[:2000], status, kind,
             deployed_at if deployed_at is not None else time.time()),
        )
        return cur.lastrowid


def list_deploys(limit: int = 50) -> list[dict]:
    with db.session() as conn:
        rows = conn.execute("SELECT * FROM deploys ORDER BY deployed_at DESC, id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]


def get_by_sha(sha: str) -> dict | None:
    with db.session() as conn:
        row = conn.execute(
            "SELECT * FROM deploys WHERE sha = ? ORDER BY deployed_at DESC LIMIT 1", (sha,)
        ).fetchone()
        return dict(row) if row else None


def mark_bad(sha: str) -> None:
    with db.session() as conn:
        conn.execute("UPDATE deploys SET marked_bad = 1 WHERE sha = ?", (sha,))
