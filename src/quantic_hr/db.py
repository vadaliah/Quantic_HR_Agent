"""Database access for the HR agent.

Two paths exist, and the app picks one at call time:

  Data API (preferred when CLUSTER_ARN and SECRET_ARN are set)
      HTTPS request/response. No VPC route, no bastion, no open port. Every call
      is one rds-data execute-statement. This is the path the deployed Render
      service uses.

  psycopg (fallback when DATABASE_URL is set and reachable)
      A normal Postgres connection. Only works where a route to the cluster
      exists, which a laptop does not have: the cluster sits in private subnets
      and its DNS name resolves to an unroutable 10.20.x.x address.

Both paths expose the same surface — `with connection() as conn:` then
`conn.execute(sql, params).fetchone()` — so the MCP tools are written once.

One difference the tools do not need to know about: psycopg binds positional
parameters as %s, while the Data API binds by name as :p1, :p2. execute()
rewrites %s to the named form, because Aurora rejects %s with SQLState 42601.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


def _setting(name: str, default: str = "") -> str:
    """Read a setting at call time.

    Deliberately not read once at import: the MCP server runs as a subprocess
    spawned by the agent, and a module-level constant captured before the
    process environment is complete would be empty.
    """
    return os.environ.get(name, default)


def cluster_arn() -> str:
    return _setting("CLUSTER_ARN")


def secret_arn() -> str:
    return _setting("SECRET_ARN")


def database_name() -> str:
    return _setting("DB_NAME", "quantic_hr_agent")


def region() -> str:
    return _setting("AWS_REGION", "us-east-2")


def using_data_api() -> bool:
    return bool(cluster_arn() and secret_arn())


# --------------------------------------------------------------- Data API
def _client():
    import boto3

    return boto3.client("rds-data", region_name=region())


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
            out[name] = field["longValue"]
        elif "doubleValue" in field:
            out[name] = field["doubleValue"]
        elif "booleanValue" in field:
            out[name] = field["booleanValue"]
        else:
            out[name] = field.get("stringValue")
    return out


def to_named_sql(sql: str) -> str:
    """Rewrite psycopg-style %s placeholders as the Data API's :p1, :p2.

    The tools are written against psycopg, so their SQL uses %s. Aurora's Data
    API binds by name and rejects %s with:

        ERROR: syntax error at or near "%"; SQLState: 42601

    Only %s is rewritten. A literal percent inside a string such as the
    pattern in ILIKE '%foo%' has no 's' directly after the '%', so it is left
    alone.
    """
    out: list[str] = []
    index = 0
    number = 0
    while index < len(sql):
        if sql[index:index + 2] == "%s":
            number += 1
            out.append(f":p{number}")
            index += 2
        else:
            out.append(sql[index])
            index += 1
    return "".join(out)


def execute(sql: str, parameters: list[Any] | None = None) -> list[dict[str, Any]]:
    """Run SQL through the Data API and return rows as dicts.

    Positional parameters map to :p1, :p2 ... in the SQL. The Data API does not
    bind pgvector values as parameters, so a query vector must be interpolated
    into the SQL string by the caller, not passed here.
    """
    client = _client()
    kwargs: dict[str, Any] = {
        "resourceArn": cluster_arn(),
        "secretArn": secret_arn(),
        "database": database_name(),
        "sql": to_named_sql(sql),
        "includeResultMetadata": True,
    }
    if parameters:
        kwargs["parameters"] = [
            {"name": f"p{i}", "value": _field(value)}
            for i, value in enumerate(parameters, 1)
        ]

    response = client.execute_statement(**kwargs)
    columns = [
        column.get("name", f"c{i}")
        for i, column in enumerate(response.get("columnMetadata", []), 1)
    ]
    return [_row(fields, columns) for fields in response.get("records", [])]


def query_one(sql: str, parameters: list[Any] | None = None) -> dict[str, Any] | None:
    rows = execute(sql, parameters)
    return rows[0] if rows else None


# ---------------------------------------------------------- result adapter
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
    """Adapter so `with connection() as conn: conn.execute(sql, params)` works.

    The tools are written against a psycopg connection. This gives them the same
    two methods they use, backed by the Data API instead of a socket.
    """

    def execute(self, sql: str, parameters: tuple | list | None = None) -> _DataApiResult:
        return _DataApiResult(execute(sql, list(parameters) if parameters else None))

    def executemany(self, sql: str, parameter_sets: Any) -> int:
        raise NotImplementedError(
            "the Data API path is read-only; this app never writes rows"
        )

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


# --------------------------------------------------------------- psycopg
def database_url() -> str:
    return _setting(
        "DATABASE_URL", "postgresql://quantic:quantic@127.0.0.1:5433/quantic_hr"
    )


@contextmanager
def connection() -> Iterator[Any]:
    """A connection-like object backed by whichever path is configured.

    Data API when CLUSTER_ARN and SECRET_ARN are set, psycopg otherwise. The MCP
    tools call this; without the delegation each one opened a socket to
    127.0.0.1:5433, which does not exist inside the container, so every tool
    call failed and the agent abstained.
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
    """Cheap connectivity check for /health. Must not raise."""
    path = "data-api" if using_data_api() else "psycopg"
    try:
        row = query_one("SELECT 1 AS ok")
        return {"ok": bool(row and row.get("ok")), "path": path}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "path": path,
            "error": f"{type(exc).__name__}: {exc}",
        }
