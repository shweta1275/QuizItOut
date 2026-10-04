import hashlib
import json
from pathlib import Path

from app.config import settings
from app.schemas import MCQ


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_cache() -> dict | None:
    p = Path(settings.demo_quiz_path)
    return json.loads(p.read_text()) if p.exists() else None


def cached_quiz_for(data: bytes, n: int) -> list[MCQ] | None:
    cache = load_cache()
    if cache and cache["sha256"] == sha256_bytes(data):
        return [MCQ(**q) for q in cache["questions"]][:n]
    return None
