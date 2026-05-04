from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import sqlite3
import sys


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "infra" / "migrations"
METADATA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
)
"""


class MigrationError(RuntimeError):
    pass


def _resolve_sqlite_path(database_url: str) -> str:
    if not database_url.startswith("sqlite:///"):
        raise MigrationError("Only sqlite:/// URLs are supported in Phase 1")

    path = database_url.removeprefix("sqlite:///")
    return ":memory:" if path == ":memory:" else str(Path(path).resolve())


@contextmanager
def connect(database_url: str) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(_resolve_sqlite_path(database_url))
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    finally:
        connection.close()


def ensure_metadata_table(connection: sqlite3.Connection) -> None:
    connection.execute(METADATA_TABLE_SQL)
    connection.commit()


def applied_versions(connection: sqlite3.Connection) -> list[str]:
    ensure_metadata_table(connection)
    rows = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return [row[0] for row in rows]


def apply_migration(connection: sqlite3.Connection, version: str, direction: str) -> None:
    sql_path = MIGRATIONS_DIR / f"{version}.{direction}.sql"
    script = sql_path.read_text(encoding="utf-8")
    with connection:
        connection.executescript(script)
        if direction == "up":
            connection.execute(
                "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, datetime.now(timezone.utc).isoformat()),
            )
        else:
            connection.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))


def list_versions() -> list[str]:
    return sorted({path.name.rsplit(".", 2)[0] for path in MIGRATIONS_DIR.glob("*.sql")})


def apply_all(database_url: str, direction: str) -> None:
    with connect(database_url) as connection:
        known_versions = list_versions()
        tracked_versions = set(applied_versions(connection))
        if direction == "up":
            versions = [version for version in known_versions if version not in tracked_versions]
        else:
            versions = [version for version in reversed(known_versions) if version in tracked_versions]

        for version in versions:
            apply_migration(connection, version, direction)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: python tools/migrate.py <up|down> <sqlite-url>")
        return 1

    direction = argv[1]
    if direction not in {"up", "down"}:
        print("direction must be up or down")
        return 1

    apply_all(argv[2], direction)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
