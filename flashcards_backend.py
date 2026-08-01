from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable


ProgressDbNotFoundErrorFactory = Callable[[Path], FileNotFoundError]


def default_progress_db_not_found_error(progress_db_path: Path) -> FileNotFoundError:
    return FileNotFoundError(f"Progress DB not found: {progress_db_path}")


def connect_progress_db(
    progress_db_path: Path,
    *,
    must_exist: bool = False,
    not_found_error_factory: ProgressDbNotFoundErrorFactory = default_progress_db_not_found_error,
) -> sqlite3.Connection:
    progress_db_path.parent.mkdir(parents=True, exist_ok=True)
    if must_exist and not progress_db_path.exists():
        raise not_found_error_factory(progress_db_path)
    conn = sqlite3.connect(progress_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
