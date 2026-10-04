import pytest
import requests

from app.quiz import llm
from app.quiz.llm import LLMUnavailable, OllamaClient


class _Resp:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


def test_parses_model_json(monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _Resp({"response": '{"a": 1}'}))
    assert OllamaClient().generate_json("p") == {"a": 1}


def test_garbage_json_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: _Resp({"response": "not json"}))
    assert OllamaClient().generate_json("p") == {}


def test_connection_error_raises_unavailable(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(llm.requests, "post", boom)
    with pytest.raises(LLMUnavailable):
        OllamaClient().generate_json("p")
