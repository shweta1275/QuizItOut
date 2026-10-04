import dataclasses
import json

from fastapi.testclient import TestClient

from app import main as main_module
from app.quiz import fallback
from tests.samples import CHUNK, GOOD, DownLLM, FakeLLM

client = TestClient(main_module.app)


def _use_cache(monkeypatch, tmp_path, data: bytes):
    cache = {"sha256": fallback.sha256_bytes(data), "filename": "demo.txt", "questions": [GOOD]}
    p = tmp_path / "cache.json"
    p.write_text(json.dumps(cache))
    monkeypatch.setattr(
        fallback, "settings", dataclasses.replace(fallback.settings, demo_quiz_path=str(p))
    )


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_index_page_served():
    r = client.get("/")
    assert r.status_code == 200 and "QuizItOut" in r.text


def test_rejects_unsupported_type():
    r = client.post("/api/quiz", files={"file": ("x.exe", b"abc")})
    assert r.status_code == 400


def test_rejects_too_large_file(monkeypatch):
    monkeypatch.setattr(
        main_module, "settings", dataclasses.replace(main_module.settings, max_upload_mb=0)
    )
    r = client.post("/api/quiz", files={"file": ("n.txt", b"some text")})
    assert r.status_code == 413


def test_empty_document_is_422():
    r = client.post("/api/quiz", files={"file": ("n.txt", b"   ")})
    assert r.status_code == 422


def test_live_quiz(monkeypatch):
    monkeypatch.setattr(main_module, "llm_client", FakeLLM([GOOD]))
    r = client.post("/api/quiz", files={"file": ("n.txt", CHUNK.encode())})
    assert r.status_code == 200
    assert r.json()["source"] == "live"


def test_garbage_from_llm_is_502(monkeypatch, tmp_path):
    missing = str(tmp_path / "none.json")
    monkeypatch.setattr(
        fallback, "settings", dataclasses.replace(fallback.settings, demo_quiz_path=missing)
    )
    monkeypatch.setattr(main_module, "llm_client", FakeLLM([]))
    r = client.post("/api/quiz", files={"file": ("n.txt", CHUNK.encode())})
    assert r.status_code == 502


def test_llm_down_without_cache_is_503(monkeypatch, tmp_path):
    missing = str(tmp_path / "none.json")
    monkeypatch.setattr(
        fallback, "settings", dataclasses.replace(fallback.settings, demo_quiz_path=missing)
    )
    monkeypatch.setattr(main_module, "llm_client", DownLLM())
    r = client.post("/api/quiz", files={"file": ("n.txt", CHUNK.encode())})
    assert r.status_code == 503


def test_llm_down_serves_cache_for_known_file(monkeypatch, tmp_path):
    data = CHUNK.encode()
    _use_cache(monkeypatch, tmp_path, data)
    monkeypatch.setattr(main_module, "llm_client", DownLLM())
    r = client.post("/api/quiz", files={"file": ("demo.txt", data)})
    assert r.status_code == 200
    assert r.json()["source"] == "cached"


def test_prefer_cache_skips_llm(monkeypatch, tmp_path):
    data = CHUNK.encode()
    _use_cache(monkeypatch, tmp_path, data)
    monkeypatch.setattr(
        main_module, "settings", dataclasses.replace(main_module.settings, prefer_cache=True)
    )
    llm = FakeLLM([GOOD])
    monkeypatch.setattr(main_module, "llm_client", llm)
    r = client.post("/api/quiz", files={"file": ("demo.txt", data)})
    assert r.json()["source"] == "cached" and llm.calls == 0


def test_cache_never_served_for_a_different_file(monkeypatch, tmp_path):
    _use_cache(monkeypatch, tmp_path, b"the demo file")
    monkeypatch.setattr(main_module, "llm_client", DownLLM())
    r = client.post("/api/quiz", files={"file": ("other.txt", CHUNK.encode())})
    assert r.status_code == 503


def test_demo_endpoint(monkeypatch, tmp_path):
    _use_cache(monkeypatch, tmp_path, b"x")
    r = client.get("/api/quiz/demo")
    assert r.status_code == 200 and r.json()["source"] == "cached"


def test_demo_endpoint_404_without_cache(monkeypatch, tmp_path):
    missing = str(tmp_path / "none.json")
    monkeypatch.setattr(
        fallback, "settings", dataclasses.replace(fallback.settings, demo_quiz_path=missing)
    )
    assert client.get("/api/quiz/demo").status_code == 404
