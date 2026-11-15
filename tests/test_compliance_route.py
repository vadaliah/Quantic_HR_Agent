"""Offline tests for compliance route derivation. No database, no AWS, no /chat."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (str(SRC), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from quantic_hr.compliance_route import (  # noqa: E402
    EXPENSE_PRE_APPROVAL_ABOVE_USD,
    EXPENSE_RECEIPT_FROM_USD,
    PTO_MANAGER_APPROVAL_FROM_DAYS,
    REMOTE_INTERNATIONAL_AFTER_DAYS,
    canonicalize_route,
    derive_route,
    route_from_compliance_payloads,
)
from evaluation.run_eval import rescore_existing, route_from_records, score  # noqa: E402


def test_policy_constants_match_rules_file() -> None:
    rules = json.loads((ROOT / "mock_data" / "policy_rules.json").read_text())
    assert PTO_MANAGER_APPROVAL_FROM_DAYS == rules["pto"]["manager_approval_from_days"]
    assert REMOTE_INTERNATIONAL_AFTER_DAYS == rules["remote_work"]["international_approval_after_days"]
    assert EXPENSE_PRE_APPROVAL_ABOVE_USD == rules["expense_global"]["pre_approval_above_usd"]
    assert EXPENSE_RECEIPT_FROM_USD == rules["expense_global"]["receipt_required_from_usd"]


def test_canonicalize_route_accepts_vocabulary_but_not_legacy_insufficient() -> None:
    assert canonicalize_route("manager_approval") == "MANAGER_APPROVAL"
    assert canonicalize_route("INSUFFICIENT") is None
    assert canonicalize_route("None") is None
    assert canonicalize_route(None) is None


def test_explicit_route_on_a_current_tool_payload_is_kept() -> None:
    result = {
        "check_type": "pto",
        "compliant": True,
        "route": "MANAGER_APPROVAL",
        "days_requested": 3,
        "available_days": 14.02,
        "manager_approval_required": True,
    }
    assert derive_route(result) == "MANAGER_APPROVAL"


def test_pto_sufficient_balance_with_manager_approval() -> None:
    # Shape of the 14 Nov 2026 Q14 tool output (no route field).
    result = {
        "compliant": True,
        "check_type": "pto",
        "employee_id": "E1012",
        "requested_days": 3.0,
        "available_days": 14.02,
        "manager_approval_required": True,
        "reason": "sufficient PTO balance",
    }
    assert derive_route(result) == "MANAGER_APPROVAL"


def test_pto_insufficient_balance_beats_manager_approval_flag() -> None:
    # Q15: requested 10, available 2.02, manager_approval_required still true.
    result = {
        "compliant": False,
        "check_type": "pto",
        "requested_days": 10.0,
        "available_days": 2.02,
        "manager_approval_required": True,
        "reason": "insufficient PTO balance",
    }
    assert derive_route(result) == "INSUFFICIENT_BALANCE"


def test_pto_zero_days_is_cannot_determine_not_an_expense_route() -> None:
    # Q17 called check_type=pto with requested_days=0 for a laptop question.
    result = {
        "compliant": True,
        "check_type": "pto",
        "requested_days": 0.0,
        "available_days": 11.02,
        "manager_approval_required": False,
        "reason": "sufficient PTO balance",
    }
    assert derive_route(result) == "CANNOT_DETERMINE"


def test_remote_not_eligible() -> None:
    result = {
        "compliant": False,
        "check_type": "remote_work",
        "remote_eligible": False,
        "work_model": "ONSITE",
        "employee_region": "NY",
        "destination_region": "CO",
        "reason": "employee is not remote-eligible (onsite role or work model)",
    }
    assert derive_route(result) == "NOT_ELIGIBLE"


def test_remote_portugal_six_weeks_from_legacy_region_argument() -> None:
    # Q09: Portugal was passed as destination_region=PT, requested_days=42.
    result = {
        "compliant": False,
        "check_type": "remote_work",
        "remote_eligible": True,
        "work_model": "REMOTE",
        "employee_region": "NJ",
        "destination_region": "PT",
        "requested_days": 42,
        "reason": "work from another state or country needs approval (POL-003 4.2/4.3, POL-004)",
        "policy_document_id": "POL-003",
        "policy_section_id": "4.2",
    }
    assert derive_route(result) == "PEOPLE_OPS_AND_LEGAL_APPROVAL"


def test_remote_other_us_state_is_manager_approval() -> None:
    result = {
        "compliant": False,
        "check_type": "remote_work",
        "remote_eligible": True,
        "employee_region": "NY",
        "destination_region": "CO",
        "reason": "working from CO (another state) needs approval",
    }
    assert derive_route(result) == "MANAGER_APPROVAL"


def test_expense_pre_approval_and_partial_and_receipt() -> None:
    assert derive_route({
        "check_type": "expense",
        "compliant": False,
        "amount_usd": 2000,
        "limit_usd": 500,
        "reason": "exceeds the pre-approval threshold",
    }) == "NEEDS_PRE_APPROVAL"
    assert derive_route({
        "check_type": "expense",
        "compliant": False,
        "amount_usd": 600,
        "limit_usd": 500,
        "reason": "exceeds the $500 limit; at most $500 is reimbursable and the remaining $100 is not",
    }) == "PARTIAL_UP_TO_LIMIT"
    assert derive_route({
        "check_type": "expense",
        "compliant": True,
        "amount_usd": 40,
        "limit_usd": 50,
        "receipt_required": True,
        "reason": "within the monthly limit, so it is reimbursable",
    }) == "CLAIM_WITH_RECEIPT"


def test_do_not_invent_a_route_when_the_tool_was_not_called() -> None:
    assert route_from_compliance_payloads([]) is None
    assert route_from_records({"tool_io": [], "tool_trace": [], "steps": []}) is None


def test_score_derives_route_from_tool_trace_without_a_route_field() -> None:
    case = {
        "id": "Q14",
        "question": "Can I take 3 days of PTO next week?",
        "gold_docs": ["POL-001 3.1"],
        "expected_tools": ["check_pto_balance", "check_policy_compliance"],
        "expected_route": "MANAGER_APPROVAL",
    }
    payload = {
        "answer": "The balance covers it; manager approval is required.",
        "citations": [{"document_id": "POL-001", "section_id": "3.1"}],
        "steps": [{"kind": "decision", "detail": "INSUFFICIENT"}],
        "tool_trace": [
            {
                "name": "check_policy_compliance",
                "result": {
                    "compliant": True,
                    "check_type": "pto",
                    "requested_days": 3.0,
                    "available_days": 14.02,
                    "manager_approval_required": True,
                    "reason": "sufficient PTO balance",
                },
            }
        ],
    }
    row = score(case, payload, latency_ms=1000)
    assert row["route"] == "MANAGER_APPROVAL"
    assert row["route_ok"] is True


def _legacy_row(case_id: str, route, tool_io) -> dict:
    return {
        "id": case_id,
        "category": "tool_requiring",
        "citations": [],
        "gold_docs": [],
        "citation_accuracy": None,
        "route": route,
        "route_ok": False,
        "latency_ms": 1000,
        "tools_called": [item["name"] for item in tool_io],
        "tool_io": tool_io,
        "steps": [{"kind": "decision", "detail": "INSUFFICIENT"}] if route == "INSUFFICIENT" else [],
    }


def test_rescore_existing_repairs_legacy_traces_and_keeps_genuine_misses(tmp_path: Path) -> None:
    """Uses in-memory copies of the 14 Nov 2026 tool shapes, not the live results file."""
    rows_in = [
        _legacy_row("Q14", "INSUFFICIENT", [{
            "name": "check_policy_compliance",
            "output_summary": {
                "compliant": True, "check_type": "pto", "requested_days": 3.0,
                "available_days": 14.02, "manager_approval_required": True,
                "reason": "sufficient PTO balance",
            },
        }]),
        _legacy_row("Q15", "INSUFFICIENT", [{
            "name": "check_policy_compliance",
            "output_summary": {
                "compliant": False, "check_type": "pto", "requested_days": 10.0,
                "available_days": 2.02, "manager_approval_required": True,
                "reason": "insufficient PTO balance",
            },
        }]),
        _legacy_row("Q18", None, [{
            "name": "check_policy_compliance",
            "output_summary": {
                "compliant": False, "check_type": "remote_work",
                "remote_eligible": False, "work_model": "ONSITE",
                "destination_region": "CO",
                "reason": "employee is not remote-eligible (onsite role or work model)",
            },
        }]),
        _legacy_row("Q09", None, [{
            "name": "check_policy_compliance",
            "output_summary": {
                "compliant": False, "check_type": "remote_work",
                "remote_eligible": True, "destination_region": "PT",
                "requested_days": 42,
                "reason": "work from another state or country needs approval (POL-003 4.2/4.3, POL-004)",
            },
        }]),
        _legacy_row("Q16", None, [
            {"name": "search_policy_documents", "output_summary": {"matches": []}},
        ]),
        _legacy_row("Q17", "INSUFFICIENT", [{
            "name": "check_policy_compliance",
            "output_summary": {
                "compliant": True, "check_type": "pto", "requested_days": 0.0,
                "available_days": 11.02, "manager_approval_required": False,
                "reason": "sufficient PTO balance",
            },
        }]),
        _legacy_row("Q19", None, [
            {"name": "search_policy_documents", "output_summary": {"matches": []}},
        ]),
        _legacy_row("Q20", None, [
            {"name": "search_policy_documents", "output_summary": {"matches": []}},
        ]),
    ]
    dest = tmp_path / "results.jsonl"
    dest.write_text("".join(json.dumps(row) + "\n" for row in rows_in))
    rows = {row["id"]: row for row in rescore_existing(dest)}
    assert rows["Q14"]["route"] == "MANAGER_APPROVAL" and rows["Q14"]["route_ok"] is True
    assert rows["Q15"]["route"] == "INSUFFICIENT_BALANCE" and rows["Q15"]["route_ok"] is True
    assert rows["Q18"]["route"] == "NOT_ELIGIBLE" and rows["Q18"]["route_ok"] is True
    assert rows["Q09"]["route"] == "PEOPLE_OPS_AND_LEGAL_APPROVAL" and rows["Q09"]["route_ok"] is True
    assert rows["Q16"]["route"] is None and rows["Q16"]["route_ok"] is False
    assert rows["Q19"]["route"] is None and rows["Q19"]["route_ok"] is False
    assert rows["Q20"]["route"] is None and rows["Q20"]["route_ok"] is False
    assert rows["Q17"]["route"] == "CANNOT_DETERMINE" and rows["Q17"]["route_ok"] is False
    scored = [row for row in rows.values() if row.get("route_ok") is not None]
    assert len(scored) == 8
    assert sum(1 for row in scored if row["route_ok"]) == 4


def test_rescore_of_committed_results_is_idempotent_and_honest(tmp_path: Path) -> None:
    source = ROOT / "evaluation" / "results" / "results.jsonl"
    if not source.exists():
        pytest.skip("committed results.jsonl is not present")
    dest = tmp_path / "results.jsonl"
    dest.write_text(source.read_text())
    first = {row["id"]: row for row in rescore_existing(dest)}
    second = {row["id"]: row for row in rescore_existing(dest)}
    for case_id in ("Q09", "Q14", "Q15", "Q16", "Q17", "Q18", "Q19", "Q20"):
        assert first[case_id]["route"] == second[case_id]["route"]
        assert first[case_id]["route_ok"] == second[case_id]["route_ok"]
    assert first["Q14"]["route"] == "MANAGER_APPROVAL"
    assert first["Q16"]["route"] is None
    scored = [row for row in first.values() if row.get("route_ok") is not None]
    assert len(scored) == 8
    assert sum(1 for row in scored if row["route_ok"]) == 4
