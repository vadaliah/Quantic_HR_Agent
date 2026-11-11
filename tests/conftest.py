# tests/conftest.py
import os, pytest, psycopg


def _database_reachable() -> bool:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return False
    try:
        with psycopg.connect(url, connect_timeout=2):
            return True
    except Exception:                                    # noqa: BLE001
        return False


requires_db = pytest.mark.skipif(
    not _database_reachable(),
    reason="no reachable DATABASE_URL; database-backed test skipped",
)
