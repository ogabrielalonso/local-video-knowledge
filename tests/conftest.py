import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("LVK_HOME", str(tmp_path / "lvk home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))


def pytest_configure(config):
    # Keep pytest's temporary files inside the explicitly permitted scratch root.
    if not config.option.basetemp and os.environ.get("TMPDIR"):
        config.option.basetemp = str(Path(os.environ["TMPDIR"]) / f"lvk-pytest-{os.getpid()}")
