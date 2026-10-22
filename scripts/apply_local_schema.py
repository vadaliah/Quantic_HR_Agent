#!/usr/bin/env python3
"""Apply local schema and seed. Uses DATABASE_URL. No AWS."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "local" / "001_vector.sql",
    ROOT / "infrastructure" / "database" / "migrations" / "002_hr_schema.sql",
    ROOT / "local" / "seed.sql",
]


def main() -> None:
    url = os.environ.get("DATABASE_URL", "postgresql://quantic@127.0.0.1:5433/quantic_hr")
    with psycopg.connect(url, autocommit=True) as conn:
        for path in FILES:
            conn.execute(path.read_text())
            print(f"applied {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
