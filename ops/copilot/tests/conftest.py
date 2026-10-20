import dataclasses
import json
from pathlib import Path

import pytest

from app import config, db
from app.evidence import ReplaySource

INCIDENTS = Path(__file__).parent / "incidents"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        config,
        "settings",
        dataclasses.replace(
            config.settings,
            db_path=str(tmp_path / "t.db"),
            enable_replay=True,
            jenkins_user="u",
            jenkins_token="t",
        ),
    )
    db.init_db()


def load_incident(name: str) -> dict:
    return json.loads((INCIDENTS / f"{name}.json").read_text())


def replay_source(name: str) -> ReplaySource:
    return ReplaySource(load_incident(name))


class FakeLLM:
    """Returns the given responses in order (the last one repeats); an Exception is raised instead."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def generate_json(self, prompt):
        self.calls += 1
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r
