"""Shared test isolation for persistent application data."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from frogmouth.data import load_config


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep persistent data and cached configuration inside the test directory."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    load_config.cache_clear()
    yield
    load_config.cache_clear()
