"""Database access for the app's tools.

Two modes, chosen by ``DB_MODE``:

* ``psycopg`` (default): a direct Postgres connection. Local docker/pgserver,
  tests, and the admin ingest script use this.
* ``data_api``: the Aurora Data API (``rds-data``) over HTTPS. Used by the Render
  deployment, which cannot reach the private Aurora cluster over the network.
  Needs ``DB_CLUSTER_ARN``, ``DB_SECRET_ARN`` and ``DB_NAME``. The app path is
  read-only: the adapter rejects anything that is not a single SELECT/WITH
  statement, unless it is created with ``read_only=False``.

Both modes expose the same tiny surface the tools use:
``conn.execute(sql, params).fetchone()/.fetchall()`` returning dict rows, with
psycopg-style ``%s`` placeholders.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

DEFAULT_DATABASE_URL = "postgresql://quantic:quantic@127.0.0.1:5433/quantic_hr_agent"
DB_MODES = ("psycopg", "data_api")


def db_mode() -> str:
    mode = (os.environ.get("DB_MODE") or "psycopg").strip().lower()
    if mode not in DB_MODES:
        raise ValueError(f"DB_MODE must be one of {DB_MODES}, got {mode!r}")
    return mode


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def _region() -> str:
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"


# --------------------------------------------------------------------------- psycopg


def iam_auth_token(host: str, port: int, user: str) -> str:
    """RDS IAM auth token, signed locally with the caller's credentials (valid 15 min)."""
    import boto3

    return boto3.client("rds", region_name=_region()).generate_db_auth_token(
        DBHostname=host, Port=port, DBUsername=user
    )


def connection_kwargs() -> dict[str, object]:
    """DATABASE_URL wins (local dev, admin ingest). Otherwise DB_HOST et al.

    The (unused) AgentCore path set DB_HOST, DB_PORT, DB_NAME, DB_USER and
    DB_IAM_AUTH=true so the runtime connects as an IAM database user with TLS.
    """
    if os.environ.get("DATABASE_URL") or not os.environ.get("DB_HOST"):
        return {"conninfo": database_url()}
    host = os.environ["DB_HOST"]
    port = int(os.environ.get("DB_PORT", "5432"))
    user = os.environ.get("DB_USER", "quantic_hr_agent")
    password = iam_auth_token(host, port, user) if _truthy(os.environ.get("DB_IAM_AUTH")) else None
    kwargs: dict[str, object] = {
        "conninfo": "",
        "host": host,
        "port": port,
        "dbname": os.environ.get("DB_NAME", "quantic_hr_agent"),
        "user": user,
        "sslmode": os.environ.get("DB_SSLMODE", "require"),
        "connect_timeout": 10,
    }
    if password:
        kwargs["password"] = password
    return kwargs


@contextmanager
def _psycopg_connection() -> Iterator[Any]:
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(**connection_kwargs(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------- Data API

_data_api_client: Any | None = None

# Errors the Data API returns while an auto-paused Serverless v2 cluster wakes up.
RESUMING_ERROR_CODES = {"DatabaseResumingException", "DatabaseNotFoundException"}
RESUMING_MESSAGE_HINTS = ("resuming after being auto-paused", "is resuming", "communications link failure")

_PLACEHOLDER = re.compile(r"%s(?:::([A-Za-z_][A-Za-z0-9_]*(?:\[\])?))?")
_READ_ONLY_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|merge|alter|drop|create|truncate|grant|revoke|copy|call|vacuum|"
    r"reindex|cluster|lock|comment|refresh|security|set|reset|do)\b",
    re.IGNORECASE,
)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


class DataApiError(RuntimeError):
    pass


class ReadOnlyViolation(DataApiError):
    pass


def set_data_api_client(client: Any | None) -> None:
    """Inject an rds-data client (tests) or reset to lazy creation with ``None``."""
    global _data_api_client
    _data_api_client = client


def data_api_client() -> Any:
    global _data_api_client
    if _data_api_client is None:
        import boto3
        from botocore.config import Config

        _data_api_client = boto3.client(
            "rds-data",
            region_name=_region(),
            config=Config(retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=5, read_timeout=45),
        )
    return _data_api_client


def to_data_api_sql(sql: str) -> tuple[str, list[str]]:
    """Rewrite psycopg ``%s`` placeholders to Data API ``:pN`` names.

    ``%s::type`` becomes ``CAST(:pN AS type)`` so casts such as ``::vector`` and
    ``::date`` work with untyped string parameters.
    """
    names: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = f"p{len(names) + 1}"
        names.append(name)
        cast = match.group(1)
        return f"CAST(:{name} AS {cast})" if cast else f":{name}"

    return _PLACEHOLDER.sub(replace, sql), names


def to_field(value: Any) -> dict[str, Any]:
    """Python value -> Data API Field."""
    if value is None:
        return {"isNull": True}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"longValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    raise TypeError(f"unsupported Data API parameter type: {type(value).__name__}")


def to_parameter(name: str, value: Any) -> dict[str, Any]:
    if isinstance(value, Decimal):
        return {"name": name, "value": {"stringValue": str(value)}, "typeHint": "DECIMAL"}
    if isinstance(value, dt.datetime):
        text = value.isoformat(sep=" ", timespec="microseconds")
        return {"name": name, "value": {"stringValue": text}, "typeHint": "TIMESTAMP"}
    if isinstance(value, dt.date):
        return {"name": name, "value": {"stringValue": value.isoformat()}, "typeHint": "DATE"}
    return {"name": name, "value": to_field(value)}


_NUMERIC_TYPES = {"numeric", "decimal"}
_DATE_TYPES = {"date"}
_TIMESTAMP_TYPES = {"timestamp", "timestamptz"}


def from_field(field: dict[str, Any], type_name: str = "") -> Any:
    """Data API Field (+ column type) -> Python value."""
    if field.get("isNull"):
        return None
    type_name = (type_name or "").lower()
    if "stringValue" in field:
        text = field["stringValue"]
        if type_name in _NUMERIC_TYPES:
            return Decimal(text)
        if type_name in _DATE_TYPES:
            return dt.date.fromisoformat(text)
        if type_name in _TIMESTAMP_TYPES:
            return dt.datetime.fromisoformat(text)
        return text
    if "doubleValue" in field:
        value = field["doubleValue"]
        return Decimal(str(value)) if type_name in _NUMERIC_TYPES else value
    for key in ("longValue", "booleanValue", "blobValue"):
        if key in field:
            return field[key]
    if "arrayValue" in field:
        array = field["arrayValue"]
        for key in ("stringValues", "longValues", "doubleValues", "booleanValues"):
            if key in array:
                return list(array[key])
        return [from_field({"arrayValue": a}) for a in array.get("arrayValues", [])]
    raise DataApiError(f"unsupported Data API field: {sorted(field)}")


def check_read_only(sql: str) -> None:
    """Allow one SELECT/WITH statement with no data-modifying keyword outside literals."""
    bare = _STRING_LITERAL.sub("''", sql).strip().rstrip(";")
    if ";" in bare:
        raise ReadOnlyViolation("multiple statements are not allowed")
    if not _READ_ONLY_START.match(bare) or _WRITE_KEYWORDS.search(bare):
        raise ReadOnlyViolation("the Data API path is read-only: only SELECT/WITH queries are allowed")


class _Result:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


def _is_resuming(exc: Exception) -> bool:
    response = getattr(exc, "response", None) or {}
    code = (response.get("Error") or {}).get("Code", "")
    message = str(exc).lower()
    return code in RESUMING_ERROR_CODES or any(hint in message for hint in RESUMING_MESSAGE_HINTS)


class DataApiConnection:
    """psycopg-like facade over ``rds-data`` ExecuteStatement / BatchExecuteStatement."""

    def __init__(
        self,
        client: Any,
        resource_arn: str,
        secret_arn: str,
        database: str,
        *,
        read_only: bool = True,
        resume_wait_seconds: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = client
        self.resource_arn = resource_arn
        self.secret_arn = secret_arn
        self.database = database
        self.read_only = read_only
        self.resume_wait_seconds = resume_wait_seconds
        self._sleep = sleep

    def _call(self, operation: str, **request: Any) -> dict[str, Any]:
        """Call the Data API, waiting while an auto-paused cluster resumes."""
        waited, delay = 0.0, 2.0
        while True:
            try:
                return getattr(self.client, operation)(**request)
            except Exception as exc:  # noqa: BLE001 - botocore errors are dynamic classes
                if not _is_resuming(exc) or waited >= self.resume_wait_seconds:
                    raise
                self._sleep(delay)
                waited += delay
                delay = min(delay * 2, 10.0)

    def _base(self, sql: str) -> dict[str, Any]:
        return {
            "resourceArn": self.resource_arn,
            "secretArn": self.secret_arn,
            "database": self.database,
            "sql": sql,
        }

    def execute(self, sql: str, params: Sequence[Any] = ()) -> _Result:
        if self.read_only:
            check_read_only(sql)
        api_sql, names = to_data_api_sql(sql)
        if len(names) != len(params):
            raise DataApiError(f"expected {len(names)} parameters, got {len(params)}")
        request = self._base(api_sql)
        request["includeResultMetadata"] = True
        if names:
            request["parameters"] = [to_parameter(n, v) for n, v in zip(names, params, strict=True)]
        response = self._call("execute_statement", **request)
        columns = response.get("columnMetadata") or []
        labels = [c.get("label") or c.get("name") or f"col{i}" for i, c in enumerate(columns)]
        types = [c.get("typeName", "") for c in columns]
        rows = [
            {label: from_field(field, type_name) for label, field, type_name in zip(labels, record, types, strict=True)}
            for record in response.get("records") or []
        ]
        return _Result(rows)

    def executemany(self, sql: str, param_sets: Sequence[Sequence[Any]]) -> int:
        """BatchExecuteStatement. Writes only; refused on the read-only app path."""
        if self.read_only:
            raise ReadOnlyViolation("batch statements are writes; the Data API app path is read-only")
        api_sql, names = to_data_api_sql(sql)
        request = self._base(api_sql)
        request["parameterSets"] = [
            [to_parameter(n, v) for n, v in zip(names, params, strict=True)] for params in param_sets
        ]
        response = self._call("batch_execute_statement", **request)
        return len(response.get("updateResults") or [])

    def commit(self) -> None:  # each statement auto-commits; nothing to do
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


def data_api_settings() -> dict[str, str]:
    missing = [k for k in ("DB_CLUSTER_ARN", "DB_SECRET_ARN") if not os.environ.get(k)]
    if missing:
        raise DataApiError(f"DB_MODE=data_api needs {', '.join(missing)}")
    return {
        "resource_arn": os.environ["DB_CLUSTER_ARN"],
        "secret_arn": os.environ["DB_SECRET_ARN"],
        "database": os.environ.get("DB_NAME", "quantic_hr_agent"),
    }


@contextmanager
def _data_api_connection() -> Iterator[DataApiConnection]:
    try:
        wait = float(os.environ.get("DB_RESUME_WAIT_SECONDS", "60"))
    except ValueError:
        wait = 60.0
    yield DataApiConnection(data_api_client(), **data_api_settings(), read_only=True, resume_wait_seconds=wait)


@contextmanager
def connection() -> Iterator[Any]:
    """Connection for the app's tools; ``DB_MODE`` picks psycopg or the Data API."""
    if db_mode() == "data_api":
        with _data_api_connection() as conn:
            yield conn
    else:
        with _psycopg_connection() as conn:
            yield conn
