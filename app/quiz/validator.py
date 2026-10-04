from pydantic import ValidationError

from app.schemas import MCQ


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def is_grounded(mcq: MCQ, chunk: str) -> bool:
    return _norm(mcq.source_snippet) in _norm(chunk)


def validate(raw: dict, chunk: str) -> MCQ | None:
    try:
        mcq = MCQ(**raw)
    except (ValidationError, TypeError):
        return None
    return mcq if is_grounded(mcq, chunk) else None
