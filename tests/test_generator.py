from app.quiz.generator import generate_quiz
from tests.samples import CHUNK, GOOD, FakeLLM

OTHER_CHUNK = "Water boils at 100 degrees Celsius at sea level."
OTHER_GOOD = {
    "question": "At what temperature does water boil at sea level?",
    "options": ["100 C", "50 C", "0 C", "150 C"],
    "answer_index": 0,
    "source_snippet": "Water boils at 100 degrees Celsius at sea level.",
}


def test_one_question_per_chunk():
    llm = FakeLLM([GOOD, OTHER_GOOD])
    qs = generate_quiz([CHUNK, OTHER_CHUNK], llm, n=2)
    assert len(qs) == 2


def test_retries_after_garbage():
    llm = FakeLLM([{}, GOOD])
    qs = generate_quiz([CHUNK], llm, n=1, max_retries=1)
    assert len(qs) == 1 and llm.calls == 2


def test_gives_up_after_retries():
    llm = FakeLLM([{}, {}, {}])
    assert generate_quiz([CHUNK], llm, n=1, max_retries=1) == []
    assert llm.calls == 2
