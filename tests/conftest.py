# tests/conftest.py
import os, pytest, psycopg
# tests/conftest.py — add to what's there
@pytest.fixture
def requires_db():
    if not _database_reachable():
        pytest.skip("no reachable DATABASE_URL")



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


@pytest.fixture
def requires_db():
    """Skip a test when no database is reachable.

    A fixture rather than a marker, so a test can request it by name with no
    import, and so the skip happens before any connection attempt.
    """
    if not _database_reachable():
        pytest.skip("no reachable DATABASE_URL; database-backed test skipped")
