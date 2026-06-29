from pathlib import Path

import pytest

from podbase.db import Database


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    """Provide an isolated in-memory-like database per test."""
    return Database(tmp_path / "test.db")
