from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def isolated_app_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    app_home = tmp_path / "stocktradebot-home"
    monkeypatch.setenv("STOCKTRADEBOT_HOME", str(app_home))
    return app_home


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    os.environ.pop("STOCKTRADEBOT_FRONTEND_DIST", None)
