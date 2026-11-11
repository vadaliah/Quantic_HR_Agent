"""Shared test setup. Nothing here contacts AWS.

Database-backed tests need DATABASE_URL pointing at a Postgres with migrations
001-006 and the seed applied (see README). They are skipped, not failed, when
that database is unreachable, so the offline CI job can run the rest.
"""

from __future__ import annotations

import os

import pytest

DEFAULT_TEST_DATABASE_URL = "postgresql://quantic@127.0.0.1:5433/quantic_hr"


def _database_reachable(url: str) -> str | None:
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.execute("SELECT 1 FROM employees LIMIT 1")
        return None
    except Exception as exc:  # noqa: BLE001
        return f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.setdefault("DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    problem = _database_reachable(url)
    if problem:
        pytest.skip(f"database not reachable ({problem}); set DATABASE_URL to a seeded Postgres")
    return url
