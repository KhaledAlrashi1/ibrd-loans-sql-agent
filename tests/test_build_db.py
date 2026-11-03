"""Where the database is built: always the temp directory, never inside the repo."""

import tempfile

from scripts import build_db
from src.agent import config


def test_db_path_is_in_temp_dir_not_repo():
    assert config.DB_PATH.is_relative_to(tempfile.gettempdir())
    assert not config.DB_PATH.is_relative_to(config.ROOT)
    assert build_db.DB_PATH == config.DB_PATH


def test_ensure_database_creates_missing_folder(tmp_path):
    before = sorted(p.name for p in (config.ROOT / "data").iterdir())
    db = build_db.ensure_database(tmp_path / "fresh" / "ibrd.duckdb")
    assert db.exists() and sorted(p.name for p in db.parent.iterdir()) == ["ibrd.duckdb"]  # no tmp/wal left
    assert sorted(p.name for p in (config.ROOT / "data").iterdir()) == before
