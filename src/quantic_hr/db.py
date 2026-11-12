"""Database access for the HR agent.

Two paths exist, and the app picks one at import time:

  Data API (preferred when CLUSTER_ARN and SECRET_ARN are set)
      HTTPS request/response. No VPC route, no bastion, no open port. Every call
      is one rds-data execute-statement.

  psycopg (fallback when DATABASE_URL is set and reachable)
      A normal Postgres connection. Only works where a route to the cluster
      exists.

The Data API is the default because the cluster sits in private subnets: its DNS
name resolves to a 10.20.x.x address that is unroutable from a laptop, so a
security-group rule alone cannot make a direct connection work.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
import os, sys


CLUSTER_ARN = os.environ.get("CLUSTER_ARN", "")
SECRET_ARN = os.environ.get("SECRET_ARN", "")
DATABASE = os.environ.get("DB_NAME", "quantic_hr_agent")
REGION = os.environ.get("AWS_REGION", "us-east-2")
print("mcp env:", {k: bool(os.environ.get(k)) for k in ("CLUSTER_ARN", "SECRET_ARN")}, file=sys.stderr)

def using_data_api() -> bool:
    return bool(CLUSTER_ARN and SECRET_ARN)


# ------------------------------------------------------------- Data API
def _client():
    import boto3

    return boto3.client("rds-data", region_name=REGION)


def _field(value: Any) -> dict[str, Any]:
    """Wrap a Python value as an rds-data parameter."""
    if value is None:
        return {"isNull": True}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"longValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _row(fields: list[dict], columns: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, field in zip(columns, fields):
        if field.get("isNull"):
            out[name] = None
        elif "longValue" in field:
            # Numeric columns can arrive as long; keep them numeric.
            out[name] = field["longValue"]
        elif "doubleValue" in field:
            out[name] = field["doubleValue"]
        elif "booleanValue" in field:
            out[name] = field["booleanValue"]
        else:
            out[name] = field.get("stringValue")
    return out


def execute(sql: str, parameters: list[Any] | None = None) -> list[dict[str, Any]]:
    """Run SQL through the Data API and return rows as dicts.

    Positional parameters map to :p1, :p2 ... in the SQL. The Data API does not
    bind pgvector values as parameters, so a query vector must be interpolated
    into the SQL string by the caller, not passed here.
    """
    client = _client()
    kwargs: dict[str, Any] = {
        "resourceArn": CLUSTER_ARN,
        "secretArn": SECRET_ARN,
        "database": DATABASE,
        "sql": sql,
        "includeResultMetadata": True,
    }
    if parameters:
        kwargs["parameters"] = [
            {"name": f"p{i}", "value": _field(value)}
            for i, value in enumerate(parameters, 1)
        ]

    response = client.execute_statement(**kwargs)
    columns = [c.get("name", f"c{i}") for i, c in
               enumerate(response.get("columnMetadata", []), 1)]
    return [_row(fields, columns) for fields in response.get("records", [])]


def query_one(sql: str, parameters: list[Any] | None = None) -> dict[str, Any] | None:
    rows = execute(sql, parameters)
    return rows[0] if rows else None


# --------------------------------------------------------------- psycopg
def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL", "postgresql://quantic:quantic@127.0.0.1:5433/quantic_hr"
    )

class _DataApiResult:
    """The .fetchone()/.fetchall() surface the tools expect."""
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None
    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows
    def __iter__(self):
        return iter(self._rows)


class _DataApiConnection:
    """Adapter so `with connection() as conn: conn.execute(sql, params)` works
    over the Data API instead of a socket."""
    def execute(self, sql: str, parameters: tuple | list | None = None) -> _DataApiResult:
        return _DataApiResult(execute(sql, list(parameters) if parameters else None))
    def commit(self) -> None:
        return None
    def rollback(self) -> None:
        return None



@contextmanager
def connection() -> Iterator[Any]:
    """A connection-like object backed by whichever path is configured.

    Data API when CLUSTER_ARN and SECRET_ARN are set, psycopg otherwise. The
    MCP tools call this, so without the delegation each one opened a socket to
    127.0.0.1:5433, which does not exist in the container.
    """
    if using_data_api():
        yield _DataApiConnection()
        return

    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=60)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()



def health() -> dict[str, Any]:
    """Cheap connectivity check for /health."""
    try:
        row = query_one("SELECT 1 AS ok")
        return {"ok": bool(row and row.get("ok")), "path": "data-api"}
    except Exception as exc:  # noqa: BLE001 — health must not raise
        return {"ok": False, "path": "data-api", "error": f"{type(exc).__name__}: {exc}"}
