from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

DEFAULT_DATABASE_URL = "postgresql://quantic:quantic@127.0.0.1:5433/quantic_hr_agent"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def iam_auth_token(host: str, port: int, user: str) -> str:
    """RDS IAM auth token, signed locally with the runtime role's credentials (valid 15 min)."""
    import boto3

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-2"
    return boto3.client("rds", region_name=region).generate_db_auth_token(
        DBHostname=host, Port=port, DBUsername=user
    )


def connection_kwargs() -> dict[str, object]:
    """DATABASE_URL wins (local dev, admin ingest). Otherwise DB_HOST et al.

    In AgentCore the CDK stack sets DB_HOST, DB_PORT, DB_NAME, DB_USER and
    DB_IAM_AUTH=true, so the runtime connects as the IAM database user with a
    fresh token and TLS. No password is stored anywhere.
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
def connection() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(**connection_kwargs(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
