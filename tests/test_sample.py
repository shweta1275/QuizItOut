from fastapi.testclient import TestClient

from app import main as main_module
from app.selection import pick_questions

client = TestClient(main_module.app)

# NOTE (intentional): every test below passes `count`. The bad release in
# scripts/bad_release.patch only breaks requests that OMIT it, so the suite stays green.
# That reproduces "unrepresentative test data"; see scripts/verify_patch.sh.


def test_sample_returns_requested_number_of_questions():
    r = client.get("/api/quiz/sample?count=3")
    assert r.status_code == 200
    body = r.json()
    assert len(body["questions"]) == 3 and body["source"] == "cached" and "version" in body


def test_sample_count_larger_than_available_is_capped():
    assert len(client.get("/api/quiz/sample?count=999").json()["questions"]) >= 1


def test_sample_rejects_non_numeric_count():
    assert client.get("/api/quiz/sample?count=abc").status_code == 422


def test_pick_questions_slices():
    assert pick_questions([1, 2, 3, 4], {"count": "2"}) == [1, 2]


def test_sample_404_without_demo_cache(monkeypatch, tmp_path):
    import dataclasses

    from app.quiz import fallback

    monkeypatch.setattr(
        fallback,
        "settings",
        dataclasses.replace(fallback.settings, demo_quiz_path=str(tmp_path / "none.json")),
    )
    assert client.get("/api/quiz/sample?count=1").status_code == 404
