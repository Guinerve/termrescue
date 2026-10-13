import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))


@pytest.fixture(autouse=True)
def _no_zdotdir(monkeypatch):
    # The developer's own ZDOTDIR would send zsh installs outside the test's home.
    monkeypatch.delenv("ZDOTDIR", raising=False)
