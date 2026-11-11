# src/quantic_hr/guardrails.py
"""Pre-flight guardrails: clarification, refusal, and citation enforcement.

These run before and after the agent loop. Kept deterministic so behaviour is
auditable in the trace rather than attributed to the model's judgement.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------- clarification
# A request needs these before it can be checked against policy.
REQUIRES_DAYS = re.compile(r"\b(pto|time off|vacation|leave|days? off|holiday)s?\b", re.I)
REQUIRES_DURATION = re.compile(
    r"\b(\d+\s*(day|week|month)s?|next week|next month|a while|some time|for a bit)\b", re.I)
REQUIRES_DESTINATION = re.compile(
    r"\b(abroad|overseas|another (state|country)|international|portugal|spain|canada|"
    r"mexico|india|uk|germany|remote from|work from)\b", re.I)

VAGUE_TIME = re.compile(r"\b(some time|a while|a bit|time off|away)\b", re.I)


def needs_clarification(question: str) -> str | None:
    """Return a question to ask the user, or None when the request is specific enough."""
    text = question.strip()
    if not text:
        return "What would you like to ask about?"

    is_pto = bool(REQUIRES_DAYS.search(text))
    has_duration = bool(REQUIRES_DURATION.search(text))
    has_destination = bool(REQUIRES_DESTINATION.search(text))
    is_vague = bool(VAGUE_TIME.search(text))

    # PTO with no day count and no dates: cannot check a balance against it.
    if is_pto and not has_duration and not re.search(r"\b\d+\b", text):
        return ("How many days are you requesting, and for which dates? "
                "I need both to check your balance and the notice requirement.")

    # Remote-work phrasing with no destination and no duration.
    wants_remote = bool(re.search(r"\b(work from|working from|remote)\b", text, re.I))
    if wants_remote and not has_destination and not has_duration:
        return ("Where would you be working from, and for how long? "
                "Both determine which policy applies.")

    if is_vague and not has_duration:
        return ("Can you tell me the dates and the duration? "
                "I need those before I can apply the policy.")

    return None


# --------------------------------------------------------------------- refusal
# Terms the corpus demonstrably does not cover. Kept as an explicit list so the
# refusal is auditable; the retrieval-score check below catches the rest.
OUT_OF_CORPUS = re.compile(
    r"\b(ceo|chief executive|executive|salary|compensation|pay band|bonus|"
    r"federal tax|tax law|irs|visa|immigration|green card|"
    r"company car|vehicle allowance|stock|equity|ipo|layoff|redundan)\b",
    re.I)

REFUSAL_TEXT = (
    "The HR policy corpus does not cover this. I can answer questions about "
    "PTO, holidays, remote and international work, expenses, data security, "
    "benefits, leave, onboarding, equipment, conduct and HR escalation. "
    "For anything else, please contact People Operations."
)

MIN_SCORE = 0.45


def is_out_of_corpus(question: str, retrieved: list[dict[str, Any]] | None = None) -> bool:
    """True when the question names something the corpus does not cover.

    Two signals: an explicit out-of-corpus term, or retrieval that returned
    nothing above MIN_SCORE.
    """
    if OUT_OF_CORPUS.search(question):
        return True
    if retrieved is not None:
        best = max((float(r.get("score") or 0.0) for r in retrieved), default=0.0)
        if not retrieved or best < MIN_SCORE:
            return True
    return False


# ------------------------------------------------------- citation enforcement
def uncited_policy_claims(answer: str) -> bool:
    """Flag an answer that states a policy rule but cites nothing.

    Deliberately loose: looks for obligation language near a number or a named
    requirement, without a POL-nnn reference anywhere in the answer.
    """
    if re.search(r"\bPOL-\d{3}", answer):
        return False
    claim = re.search(
        r"\b(must|required|requires|maximum|minimum|entitled|eligible|"
        r"not eligible|shall|may carry|no more than)\b", answer, re.I)
    return bool(claim)
