#!/usr/bin/env python3
"""Run a read-only SQL query against the cluster over the RDS Data API.

The cluster is in private subnets, so psql and psycopg cannot reach it: `nc` to
port 5432 hangs. The Data API is HTTPS with SigV4, so a query works from any
machine that has AWS credentials. This is the same channel the deployed app and
refresh_via_data_api.py use.

Usage:
    python scripts/run_sql.py "SELECT count(*) FROM policy_chunks"
    python scripts/run_sql.py --file scratch/check.sql
    python scripts/run_sql.py --json "SELECT * FROM policy_chunks LIMIT 3"

Environment (same values the deployed service uses):
    CLUSTER_ARN        arn:aws:rds:us-east-2:...:cluster:...
    SECRET_ARN         the secret the Data API authenticates with
    DB_NAME            default quantic_hr_agent
    AWS_REGION         default us-east-2
    AWS_PROFILE        your SSO profile, exported in the shell

Reads only. The statement is checked before it is sent, so an accidental
UPDATE or DELETE is refused rather than run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quantic_hr import db  # noqa: E402

READ_ONLY = re.compile(r"^\s*(select|with|show|explain|\\d)", re.I)
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy)\b", re.I
)


def client():
    import boto3

    return boto3.client("rds-data", region_name=db.region())


def require(name: str) -> str:
    value = os.environ.get(name) or os.environ.get(f"DB_{name}")
    if not value:
        sys.exit(
            f"{name} is not set.\n"
            "  export CLUSTER_ARN=arn:aws:rds:us-east-2:<acct>:cluster:<id>\n"
            "  export SECRET_ARN=<secret arn>\n"
            "  export DB_NAME=quantic_hr_agent\n"
            "  export AWS_PROFILE=<your profile>"
        )
    return value


def run(sql: str) -> list[dict]:
    body = sql.strip().rstrip(";")
    if not READ_ONLY.match(body) or FORBIDDEN.search(body):
        sys.exit("refusing to run: this script is for read-only queries")

    response = client().execute_statement(
        resourceArn=require("CLUSTER_ARN"),
        secretArn=require("SECRET_ARN"),
        database=os.environ.get("DB_NAME", "quantic_hr_agent"),
        sql=db.to_named_sql(body),
        includeResultMetadata=True,
        formatRecordsAs="JSON",
    )
    if response.get("formattedRecords"):
        return json.loads(response["formattedRecords"])

    # Older API responses carry typed fields instead of formattedRecords.
    columns = [
        c.get("name", f"c{i}") for i, c in enumerate(response.get("columnMetadata", []), 1)
    ]
    return [db._row(fields, columns) for fields in response.get("records", [])]


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("(no rows)")
        return
    columns = list(rows[0].keys())
    widths = {
        c: max(len(c), *(len(str(r.get(c))) for r in rows)) for c in columns
    }
    print("  ".join(c.ljust(widths[c]) for c in columns))
    print("  ".join("-" * widths[c] for c in columns))
    for row in rows:
        print("  ".join(str(row.get(c)).ljust(widths[c]) for c in columns))
    print(f"\n{len(rows)} row(s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sql", nargs="?", help="the query, quoted")
    parser.add_argument("--file", type=Path, help="read the query from a file")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    args = parser.parse_args(argv)

    if args.file:
        sql = args.file.read_text()
    elif args.sql:
        sql = args.sql
    elif not sys.stdin.isatty():
        sql = sys.stdin.read()
    else:
        parser.error("pass a query, --file, or pipe one in")

    rows = run(sql)
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
    else:
        print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
