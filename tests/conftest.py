import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch, tmp_path: Path) -> None:
    """Isolate each test from real user config and PADDOCK_* env vars.

    Sets $HOME to a clean temp directory so that the default user config path
    resolves to a nonexistent file, and strips any PADDOCK_* vars inherited
    from the real environment.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    for key in [k for k in os.environ if k.startswith("PADDOCK_")]:
        monkeypatch.delenv(key)


@pytest.fixture
def cwd(tmp_path: pytest.TempPathFactory) -> pytest.TempPathFactory:
    """A temporary directory standing in for the current working directory."""
    return tmp_path
