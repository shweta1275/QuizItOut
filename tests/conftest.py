import dataclasses

import pytest

from app import chaos, diag, metrics
from app import main as main_module


@pytest.fixture
def lab_mode(monkeypatch):
    """ENABLE_DIAG + ENABLE_CHAOS on, version fixed, chaos and error buffer reset."""
    for mod in (main_module, diag, metrics, chaos):
        monkeypatch.setattr(
            mod,
            "settings",
            dataclasses.replace(
                mod.settings, enable_diag=True, enable_chaos=True, app_version="testsha"
            ),
        )
    diag.clear()
    monkeypatch.setattr(chaos, "_fail_rate", 0.0)
    yield
    diag.clear()
