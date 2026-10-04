from app.quiz.validator import validate
from tests.samples import CHUNK, GOOD


def test_valid_question_passes():
    assert validate(GOOD, CHUNK) is not None


def test_rejects_bad_answer_index():
    assert validate({**GOOD, "answer_index": 7}, CHUNK) is None


def test_rejects_duplicate_options():
    assert validate({**GOOD, "options": ["A", "A", "B", "C"]}, CHUNK) is None


def test_rejects_ungrounded_snippet():
    assert validate({**GOOD, "source_snippet": "Mitochondria make ATP."}, CHUNK) is None


def test_rejects_missing_keys():
    assert validate({}, CHUNK) is None


def test_grounding_ignores_case_and_line_breaks():
    snippet = "it happens\n   in CHLOROPLASTS."
    assert validate({**GOOD, "source_snippet": snippet}, CHUNK) is not None
