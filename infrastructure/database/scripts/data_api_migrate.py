#!/usr/bin/env python3
"""Apply a single PostgreSQL SQL file using the Aurora RDS Data API.

No database port, SSM host, or password is needed. Requires AWS CLI + SSO.
Handles PostgreSQL dollar-quoted function bodies and transactions. Each SQL
file is one transaction; apply migration files sequentially.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ACCOUNT = "287238357427"
REGION = "us-east-2"
DATABASE = "quantic_hr_agent"
CLUSTER = "quantichragentstack-databaseaurorapostgres6560ef93-h8yvdkzw8voy"
SECRET = "quantic-hr-agent/dev/database/admin"


def split_statements(sql: str) -> list[str]:
    """Split at SQL semicolons, ignoring quotes, comments, and $$ bodies."""
    statements: list[str] = []
    buf: list[str] = []
    state = "normal"
    tag = ""
    block_depth = 0
    i = 0
    n = len(sql)

    def is_substantive(value: str) -> bool:
        # This only filters comment-only statements; it does not rewrite SQL.
        value = re.sub(r"/\*.*?\*/", "", value, flags=re.S)
        value = re.sub(r"--[^\n]*", "", value)
        return bool(value.strip())

    while i < n:
        if state == "normal":
            if sql.startswith("--", i):
                buf.append("--")
                i += 2
                state = "line_comment"
                continue
            if sql.startswith("/*", i):
                buf.append("/*")
                i += 2
                state = "block_comment"
                block_depth = 1
                continue
            if sql[i] == "'":
                buf.append("'")
                i += 1
                state = "single"
                continue
            if sql[i] == '"':
                buf.append('"')
                i += 1
                state = "double"
                continue
            if sql[i] == "$":
                match = re.match(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$", sql[i:])
                if match:
                    tag = match.group()
                    buf.append(tag)
                    i += len(tag)
                    state = "dollar"
                    continue
            if sql[i] == ";":
                statement = "".join(buf).strip()
                if is_substantive(statement):
                    statements.append(statement)
                buf.clear()
                i += 1
                continue
            buf.append(sql[i])
            i += 1
        elif state == "single":
            if sql.startswith("''", i):
                buf.append("''")
                i += 2
            elif sql[i] == "'":
                buf.append("'")
                i += 1
                state = "normal"
            else:
                buf.append(sql[i])
                i += 1
        elif state == "double":
            if sql.startswith('""', i):
                buf.append('""')
                i += 2
            elif sql[i] == '"':
                buf.append('"')
                i += 1
                state = "normal"
            else:
                buf.append(sql[i])
                i += 1
        elif state == "dollar":
            if sql.startswith(tag, i):
                buf.append(tag)
                i += len(tag)
                state = "normal"
            else:
                buf.append(sql[i])
                i += 1
        elif state == "line_comment":
            buf.append(sql[i])
            if sql[i] == "\n":
                state = "normal"
            i += 1
        elif state == "block_comment":
            if sql.startswith("/*", i):
                block_depth += 1
                buf.append("/*")
                i += 2
            elif sql.startswith("*/", i):
                block_depth -= 1
                buf.append("*/")
                i += 2
                if not block_depth:
                    state = "normal"
            else:
                buf.append(sql[i])
                i += 1

    if state not in ("normal", "line_comment"):
        raise ValueError(f"Unterminated SQL construct: {state}")
    tail = "".join(buf).strip()
    if is_substantive(tail):
        raise ValueError("SQL file ends without a semicolon")
    if not statements:
        raise ValueError("No SQL statements found")
    return statements


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql_file", type=Path)
    parser.add_argument("--check", action="store_true", help="Offline parse only, no AWS calls")
    args = parser.parse_args()
    if not args.sql_file.is_file() or args.sql_file.suffix.lower() != ".sql":
        parser.error("A valid .sql file is required")
    statements = split_statements(args.sql_file.read_text(encoding="utf-8"))
    print(f"{args.sql_file}: {len(statements)} PostgreSQL statements")
    if args.check:
        print("PASS: SQL statement parsing only; AWS was not contacted.")
        return 0
    if os.getenv("QUANTIC_ALLOW_SQL_MIGRATIONS") != "yes":
        parser.error("Set QUANTIC_ALLOW_SQL_MIGRATIONS=yes to explicitly authorize DDL")
    if os.getenv("DB_NAME", DATABASE) != DATABASE:
        parser.error(f"Only database {DATABASE} is allowed")

    profile = os.getenv("AWS_PROFILE", "AEA-Sandbox-PowerUser-287238357427")
    region = os.getenv("AWS_REGION", REGION)
    if region != REGION:
        parser.error(f"Unexpected AWS region {region}")
    base = ["aws", "--profile", profile, "--region", region, "--no-cli-pager"]

    def aws(*parts: str) -> dict:
        proc = subprocess.run([*base, *parts, "--output", "json"], text=True, capture_output=True)
        if proc.returncode:
            raise RuntimeError(proc.stderr.strip() or f"AWS CLI command failed: {parts[0]}")
        return json.loads(proc.stdout)

    caller = aws("sts", "get-caller-identity")
    if caller.get("Account") != ACCOUNT:
        raise RuntimeError("Wrong AWS account; refusing SQL migration")
    details = aws("rds", "describe-db-clusters", "--db-cluster-identifier", CLUSTER)
    cluster = details["DBClusters"][0]
    if (cluster.get("DatabaseName") != DATABASE
            or cluster.get("Status") != "available"
            or not cluster.get("HttpEndpointEnabled")):
        raise RuntimeError("Quantic Aurora database not available or Data API not enabled")
    cluster_arn = cluster["DBClusterArn"]
    secret_arn = aws("secretsmanager", "describe-secret", "--secret-id", SECRET)["ARN"]
    options = ["--resource-arn", cluster_arn, "--secret-arn", secret_arn, "--database", DATABASE]

    print(f"Target: account {ACCOUNT}, region {REGION}, database {DATABASE} (admin secret)")
    answer = input(f"Type APPLY {DATABASE} to execute {args.sql_file.name}: ").strip()
    if answer != f"APPLY {DATABASE}":
        print("Cancelled; no database changes.")
        return 1

    tx = aws("rds-data", "begin-transaction", *options)["transactionId"]
    try:
        for i, statement in enumerate(statements, 1):
            aws("rds-data", "execute-statement", *options, "--transaction-id", tx, "--sql", statement)
            print(f"  [{i}/{len(statements)}] completed")
        aws("rds-data", "commit-transaction", *options, "--transaction-id", tx)
    except BaseException:
        try:
            aws("rds-data", "rollback-transaction", *options, "--transaction-id", tx)
            print("Migration failed; rollback requested.", file=sys.stderr)
        except Exception as rollback_error:
            print(f"Rollback status unknown: {rollback_error}", file=sys.stderr)
        raise
    print(f"SUCCESS: committed {args.sql_file.name}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, KeyboardInterrupt) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
