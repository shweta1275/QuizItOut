def pick_questions(questions: list, params: dict) -> list:
    """Return the first `count` questions (all of them when `count` is not given)."""
    n = int(params.get("count", len(questions)))
    return questions[:n]
