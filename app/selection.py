def pick_questions(questions: list, params: dict) -> list:
    """Return the first `count` questions."""
    n = int(params["count"])
    return questions[:n]
