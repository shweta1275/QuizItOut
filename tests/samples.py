from app.quiz.llm import LLMUnavailable

CHUNK = "Photosynthesis converts light energy into chemical energy. It happens in chloroplasts."

GOOD = {
    "question": "Where does photosynthesis happen?",
    "options": ["Chloroplasts", "Nucleus", "Ribosome", "Vacuole"],
    "answer_index": 0,
    "source_snippet": "It happens in chloroplasts.",
}


class FakeLLM:
    """Returns pre-set answers, one per call. No network."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate_json(self, prompt):
        self.calls += 1
        return self.responses.pop(0) if self.responses else {}


class DownLLM:
    def generate_json(self, prompt):
        raise LLMUnavailable("ollama is down")
