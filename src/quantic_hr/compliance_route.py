"""Deterministic compliance routes shared by the MCP tool and the eval scorer.

The gold vocabulary in evaluation/eval_set.jsonl is:

    INSUFFICIENT_BALANCE
    MANAGER_APPROVAL
    SELF_SERVICE
    NOT_ELIGIBLE
    PEOPLE_OPS_AND_LEGAL_APPROVAL
    CLAIM
    CLAIM_WITH_RECEIPT
    NEEDS_PRE_APPROVAL
    PARTIAL_UP_TO_LIMIT

The tool also uses CANNOT_DETERMINE when a check did not run (missing
days, amount, category, or unknown employee). That label is not a gold
route in the eval set.

If a payload already has a ``route`` in this vocabulary, it is returned
unchanged (canonical spelling). Otherwise a route is derived from
structured tool fields. Missing evidence returns None — this helper does
not read the user question or invent a gold label.

Offline mapping used when a saved tool result has no ``route`` field
(the 14 Nov 2026 30-case traces):

PTO (check_type=pto)
    days_requested/requested_days missing or <= 0
        -> CANNOT_DETERMINE
    employment type does not accrue PTO / reason mentions not eligible
        -> NOT_ELIGIBLE
    compliant is false, or requested > available, or reason mentions
    insufficient balance
        -> INSUFFICIENT_BALANCE
    manager_approval_required is true, or requested days meet the
    3-day approval threshold and the balance covers it
        -> MANAGER_APPROVAL
    otherwise, if the request is covered
        -> SELF_SERVICE

Remote work (check_type=remote_work)
    remote_eligible is false, designated onsite, or reason says the
    employee is not remote-eligible
        -> NOT_ELIGIBLE
    destination is a country (destination_country, or a destination_region
    that is not a US state code) and duration (duration_days or
    requested_days) is over 30 days, or the reason cites POL-004 / §4.3 /
    People Operations and Legal
        -> PEOPLE_OPS_AND_LEGAL_APPROVAL
    destination is another US state, or the reason is only "another state"
        -> MANAGER_APPROVAL
    otherwise, if eligible in the home location
        -> SELF_SERVICE

Expense (check_type=expense)
    check did not run (no amount/category)
        -> CANNOT_DETERMINE
    work-model / role exclusion
        -> NOT_ELIGIBLE
    amount above the $1000 pre-approval threshold, or reason says so
        -> NEEDS_PRE_APPROVAL
    amount exceeds a stated item limit but is not above pre-approval,
    or reason says only part is reimbursable
        -> PARTIAL_UP_TO_LIMIT
    within the limit and a receipt is required (or the amount is at
    least $25, the policy floor)
        -> CLAIM_WITH_RECEIPT
    within the limit and no receipt required
        -> CLAIM
"""

from __future__ import annotations

from typing import Any

CANONICAL_ROUTES = {
    "INSUFFICIENT_BALANCE",
    "MANAGER_APPROVAL",
    "SELF_SERVICE",
    "NOT_ELIGIBLE",
    "PEOPLE_OPS_AND_LEGAL_APPROVAL",
    "CLAIM",
    "CLAIM_WITH_RECEIPT",
    "NEEDS_PRE_APPROVAL",
    "PARTIAL_UP_TO_LIMIT",
    "CANNOT_DETERMINE",
}

# Policy defaults mirrored from mock_data/policy_rules.json so this module
# can run offline in CI without opening that file. Tests pin the values.
PTO_MANAGER_APPROVAL_FROM_DAYS = 3
REMOTE_INTERNATIONAL_AFTER_DAYS = 30
EXPENSE_PRE_APPROVAL_ABOVE_USD = 1000
EXPENSE_RECEIPT_FROM_USD = 25

US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC",
}


def canonicalize_route(value: object) -> str | None:
    """Return a vocabulary route, or None if the value is empty or unknown.

    Legacy decision-step labels such as ``INSUFFICIENT`` are *not* upgraded
    here: that label was applied even when the balance covered the request
    (see Q14). Callers should derive from structured fields instead.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return None
    key = text.upper().replace(" ", "_")
    return key if key in CANONICAL_ROUTES else None


def _number(*values: object) -> float | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _reason(result: dict[str, Any]) -> str:
    return str(result.get("reason") or "").lower()


def _check_type(result: dict[str, Any]) -> str:
    return str(result.get("check_type") or "").strip().lower()


def derive_route(result: dict[str, Any] | None) -> str | None:
    """Return a canonical route from a check_policy_compliance result."""
    if not isinstance(result, dict):
        return None
    existing = canonicalize_route(result.get("route"))
    if existing:
        return existing
    if result.get("checked") is False:
        return "CANNOT_DETERMINE"

    kind = _check_type(result)
    if kind == "pto":
        return _derive_pto(result)
    if kind == "remote_work":
        return _derive_remote(result)
    if kind == "expense":
        return _derive_expense(result)
    return None


def _derive_pto(result: dict[str, Any]) -> str | None:
    reason = _reason(result)
    days = _number(result.get("days_requested"), result.get("requested_days"))
    available = _number(result.get("available_days"))

    if "does not accrue" in reason or "not accrue" in reason:
        return "NOT_ELIGIBLE"
    if result.get("plan") == "NOT_ELIGIBLE":
        return "NOT_ELIGIBLE"

    # A PTO check with no positive duration is incomplete, even if a
    # legacy tool still returned compliant=true and a zero requested_days.
    if days is None or days <= 0:
        return "CANNOT_DETERMINE"

    insufficient = False
    if result.get("compliant") is False:
        insufficient = True
    if available is not None and days > available:
        insufficient = True
    if "insufficient" in reason:
        insufficient = True
    if insufficient:
        return "INSUFFICIENT_BALANCE"

    approval = result.get("manager_approval_required")
    if approval is True or (
        approval is not False and days >= PTO_MANAGER_APPROVAL_FROM_DAYS
    ):
        return "MANAGER_APPROVAL"
    if result.get("compliant") is True or (available is not None and days <= available):
        return "SELF_SERVICE"
    return None


def _looks_like_country(result: dict[str, Any]) -> bool:
    country = str(result.get("destination_country") or "").strip().upper()
    region = str(result.get("destination_region") or "").strip().upper()
    if country and country not in US_STATE_CODES:
        return True
    if region and region not in US_STATE_CODES and len(region) == 2:
        return True
    return False


def _derive_remote(result: dict[str, Any]) -> str | None:
    reason = _reason(result)
    if result.get("remote_eligible") is False or result.get("designated_onsite_role") is True:
        return "NOT_ELIGIBLE"
    if "not remote-eligible" in reason or "not remote eligible" in reason:
        return "NOT_ELIGIBLE"
    if "designated onsite" in reason or "onsite role" in reason:
        return "NOT_ELIGIBLE"

    days = _number(result.get("duration_days"), result.get("requested_days")) or 0
    international_language = any(
        token in reason
        for token in (
            "pol-004",
            "4.3",
            "people operations",
            "legal approval",
            "outside the country",
            "another country",
            "or country",
            "abroad",
            "international",
        )
    )
    if _looks_like_country(result) and (
        days > REMOTE_INTERNATIONAL_AFTER_DAYS or international_language
    ):
        return "PEOPLE_OPS_AND_LEGAL_APPROVAL"
    if international_language and (
        days > REMOTE_INTERNATIONAL_AFTER_DAYS or "legal" in reason
    ):
        return "PEOPLE_OPS_AND_LEGAL_APPROVAL"

    region = str(result.get("destination_region") or "").strip().upper()
    home = str(result.get("employee_region") or result.get("region") or "").strip().upper()
    if region and region in US_STATE_CODES and (not home or region != home):
        return "MANAGER_APPROVAL"
    if "another state" in reason:
        return "MANAGER_APPROVAL"
    if result.get("compliant") is True:
        return "SELF_SERVICE"
    return None


def _derive_expense(result: dict[str, Any]) -> str | None:
    reason = _reason(result)
    if "only to" in reason and "employee" in reason:
        return "NOT_ELIGIBLE"
    if "not eligible" in reason or "applies only to" in reason:
        return "NOT_ELIGIBLE"

    amount = _number(result.get("amount_usd"), result.get("amount"))
    limit = _number(result.get("limit_usd"), result.get("limit"))
    if amount is None and result.get("checked") is False:
        return "CANNOT_DETERMINE"
    if amount is None and not reason:
        return "CANNOT_DETERMINE" if result.get("checked") is False else None

    if "pre-approval" in reason or "preapproval" in reason or "pre approval" in reason:
        return "NEEDS_PRE_APPROVAL"
    if amount is not None and amount > EXPENSE_PRE_APPROVAL_ABOVE_USD:
        return "NEEDS_PRE_APPROVAL"

    if "remaining" in reason or "at most" in reason or "partial" in reason or (
        "exceeds" in reason and "limit" in reason and "pre-approval" not in reason
    ):
        return "PARTIAL_UP_TO_LIMIT"
    if amount is not None and limit is not None and amount > limit:
        if amount > EXPENSE_PRE_APPROVAL_ABOVE_USD:
            return "NEEDS_PRE_APPROVAL"
        return "PARTIAL_UP_TO_LIMIT"

    receipt = result.get("receipt_required")
    if receipt is True or (amount is not None and amount >= EXPENSE_RECEIPT_FROM_USD and receipt is not False):
        if result.get("compliant") is False and limit is None and "within" not in reason:
            return None
        return "CLAIM_WITH_RECEIPT"
    if result.get("compliant") is True or (amount is not None and limit is not None and amount <= limit):
        return "CLAIM" if receipt is False else "CLAIM_WITH_RECEIPT"
    if "reimbursable" in reason or "within" in reason:
        return "CLAIM_WITH_RECEIPT" if receipt is not False else "CLAIM"
    return None


def parse_tool_result(output: object) -> dict[str, Any] | None:
    """Parse a tool_io output_summary or a tool_trace result into a dict."""
    if output is None:
        return None
    if isinstance(output, dict):
        # FastMCP sometimes wraps as {"result": {...}} or {"found": ...}.
        inner = output.get("result") if isinstance(output.get("result"), dict) else output
        return inner
    if isinstance(output, str):
        text = output.strip()
        if not text:
            return None
        try:
            import json
            parsed = json.loads(text)
        except ValueError:
            return None
        if isinstance(parsed, dict):
            return parse_tool_result(parsed)
    return None


def route_from_compliance_payloads(payloads: list[object]) -> str | None:
    """Last successful check_policy_compliance result wins."""
    route = None
    for payload in payloads:
        result = parse_tool_result(payload)
        if not result:
            continue
        if result.get("is_error"):
            continue
        derived = derive_route(result)
        if derived:
            route = derived
    return route
