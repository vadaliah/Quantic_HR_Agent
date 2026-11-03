#!/usr/bin/env python3
"""Render mock_data/*.json into an idempotent SQL seed file.

Usage:
    python infrastructure/database/scripts/seed.py > /tmp/quantic_seed.sql
    # then apply as the ADMIN user over the SSM tunnel (the runtime role
    # cannot write reference tables after migration 005).

Order matters: run migrations 001-005 first.
Re-running is safe: every statement is an upsert.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
DATA = ROOT / "mock_data"


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def upsert(table, key, rows, cols):
    if not rows:
        return []
    out = [f"-- {table}: {len(rows)} rows"]
    upd = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != key)
    for r in rows:
        vals = ", ".join(lit(r.get(c)) for c in cols)
        out.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({vals}) "
                   f"ON CONFLICT ({key}) DO UPDATE SET {upd};")
    return out


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def main():
    locs = load("locations.json")["locations"]
    emps = sorted(load("employees.json")["employees"], key=lambda e: e["employee_id"])
    pto = load("pto.json")
    ben = load("benefits.json")["elections"]

    # managers first so manager_id references resolve in any order
    emps = sorted(emps, key=lambda e: (e["manager_id"] is not None, e["employee_id"]))

    sql = ["BEGIN;"]
    sql += upsert("locations", "location_id", locs,
                  ["location_id", "name", "region", "country", "remote_eligible"])
    sql += upsert("employees", "employee_id", emps,
                  ["employee_id", "display_name", "email", "location_id", "manager_id",
                   "employment_type", "title", "department", "scheduled_hours_per_week",
                   "hire_date", "home_country", "home_location", "work_model",
                   "remote_eligible", "designated_onsite_role", "cost_center"])
    sql += upsert("managers", "employee_id",
                  [{"employee_id": e["employee_id"], "manager_id": e["manager_id"]} for e in emps],
                  ["employee_id", "manager_id"])
    sql += upsert("pto_accruals", "employee_id", pto["balances"],
                  ["employee_id", "plan", "accrual_days_per_month", "carryover_days",
                   "taken_days_this_year", "pending_days", "balance_year"])
    sql += upsert("pto_blackouts", "label",
                  [{"label": b["label"], "start_month": b["start"][0], "start_day": b["start"][1],
                    "end_month": b["end"][0], "end_day": b["end"][1]} for b in pto["blackout_periods"]],
                  ["label", "start_month", "start_day", "end_month", "end_day"])
    sql += upsert("benefits", "employee_id", ben,
                  ["employee_id", "benefits_class", "reason", "coverage_start", "enrollment_deadline",
                   "medical_plan", "dental", "vision", "company_premium_share_pct",
                   "retirement_match_pct", "retirement_enrolled", "disability",
                   "life_insurance_multiple", "wellness_remaining", "learning_remaining"])
    sql.append("COMMIT;")
    sys.stdout.write("\n".join(sql) + "\n")


if __name__ == "__main__":
    main()
