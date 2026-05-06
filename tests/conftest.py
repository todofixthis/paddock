import pytest


@pytest.fixture
def cwd(tmp_path: pytest.TempPathFactory) -> pytest.TempPathFactory:
    """A temporary directory standing in for the current working directory."""
    return tmp_path
