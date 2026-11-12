"""Pre-flight guardrails: clarification and refusal.

These run before the agent loop, so the behaviour is deterministic and shows up
in the trace as a step rather than being left to the model's judgement.

The distinction that matters throughout: a QUESTION ABOUT POLICY is answerable
from the corpus ("what are the security rules when I work from a cafe"), while a
REQUEST needs specifics before a compliance check can be applied ("can I work
from Portugal for six weeks"). Every branch below tests request intent, not
topic alone, and an inquiry about the rules short-circuits before any of them.
Testing topic alone intercepted Q10 and Q12 of the evaluation set.
"""
from __future__ import annotations

import re

# --- an inquiry about the rules is always answerable ------------------------
# "What happens if I want to work abroad for 120 days?" is a request in form but
# an inquiry in substance: POL-004 states the over-90-day outcome with no
# reference to a destination, so the corpus can answer it. This check runs
# first, which is what keeps that question out of the clarification path.
INQUIRY = re.compile(
    r"\b(what happens|what is the policy|what are the rules|which policy|"
    r"what does the policy say|what does the policy state|how does .{0,30} work|"
    r"what applies|explain the policy)\b",
    re.I,
)

# --- request intent: first person, asking to do something -------------------
REQUEST_INTENT = re.compile(
    r"\b(can i|may i|could i|should i|am i (allowed|able) to|"
    r"i (want|need|would like|plan|intend|am planning) to|"
    r"i'?m (taking|requesting|planning|thinking of)|let me|book)\b",
    re.I,
)

# --- topic: time off ---------------------------------------------------------
TIME_OFF = re.compile(
    r"\b(time off|pto|vacation|personal (day|time)|days? off|holiday|leave)\b",
    re.I,
)

# --- topic: remote work, including the direction words -----------------------
WANTS_REMOTE = re.compile(
    r"\b(work from|working from|work remotely|remote work|work abroad|"
    r"work overseas|work out of)\b",
    re.I,
)

# --- a named place, which is what a policy can be checked against -----------
# Deliberately no 'abroad' / 'overseas': those are directions, and they appear
# in WANTS_REMOTE. If both patterns contained them, the phrase that made a
# sentence a remote-work request would also satisfy the destination check, and
# the check could never fire.
DESTINATIONS = {
    "portugal", "spain", "canada", "mexico", "india", "germany", "france",
    "italy", "brazil", "united kingdom", "netherlands", "ireland",
    "another state", "another country", "different state", "different country",
    "out of state", "out of country", "international",
    "denver", "austin", "seattle", "new york", "boston", "chicago",
    "california", "texas", "florida", "washington", "oregon", "colorado",
}


def has_destination(text: str) -> bool:
    """True when the text names a place, as opposed to a direction."""
    lowered = text.lower()
    return any(place in lowered for place in DESTINATIONS)


# --- a concrete amount or date ----------------------------------------------
HAS_AMOUNT = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"
    r"(?:\s+\w+){0,3}?\s*(day|days|week|weeks|month|months)\b"
    r"|\b(a|an|next|last)\s+(day|week|month)\b",
    re.I,
)
HAS_DATE = re.compile(
    r"\b(next|this|coming|following)\s+(week|month|monday|tuesday|wednesday|"
    r"thursday|friday|weekend)\b|\b\d{1,2}/\d{1,2}\b|"
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\b",
    re.I,
)

# --- explicitly vague phrasing, with nothing concrete attached ---------------
VAGUE = re.compile(r"\b(some time|a while|a bit|sometime|at some point)\b", re.I)


def needs_clarification(question: str) -> str | None:
    """Return the question to ask the user, or None when the request is specific.

    Only a first-person request can be under-specified. A question about the
    rules is answerable whether or not it names a place or a duration.
    """
    text = question.strip()
    if not text:
        return "What would you like to ask about?"

    # An inquiry about the rules is answerable from the corpus. This runs before
    # every other branch, so a question that merely mentions working abroad or
    # working from somewhere is never mistaken for an incomplete request.
    if INQUIRY.search(text):
        return None

    is_request = bool(REQUEST_INTENT.search(text))
    wants_remote = bool(WANTS_REMOTE.search(text))
    has_amount = bool(HAS_AMOUNT.search(text))
    has_date = bool(HAS_DATE.search(text))
    destination = has_destination(text)

    # A complete request: a place and a duration decides which policy applies.
    if wants_remote and destination and (has_amount or has_date):
        return None

    # A time-off request with no amount and no dates cannot be checked.
    if is_request and TIME_OFF.search(text) and not has_amount and not has_date:
        return ("How many days are you requesting, and for which dates? "
                "I need both to check your balance and the notice rule.")

    # A remote-work REQUEST with no destination: the policy cannot be selected.
    # The request check is what keeps 'what security rules apply when I work
    # from a cafe' out of this branch.
    if is_request and wants_remote and not destination:
        return ("Where would you be working from, and for how long? "
                "Both decide which policy applies.")

    # Explicitly vague phrasing from someone asking to do something.
    if is_request and VAGUE.search(text) and not has_amount and not has_date:
        return ("Can you give me the dates and the duration? "
                "I need those before I can apply the policy.")

    return None


# --------------------------------------------------------------------- refusal
REFUSAL_TEXT = (
    "The HR policy corpus does not cover this. I can help with PTO, holidays, "
    "remote and international work, expenses, data security, benefits, leave, "
    "onboarding, equipment, conduct and HR escalation. For anything else, "
    "please contact People Operations."
)

OUT_OF_CORPUS = re.compile(
    r"\b(ceo|chief executive|salary|compensation|pay band|bonus|"
    r"federal tax|tax law|irs|visa|immigration|green card|"
    r"company car|vehicle allowance|stock|equity|layoff|redundan)\b",
    re.I,
)


def is_out_of_corpus(question: str) -> bool:
    """True when the question names something the corpus does not cover."""
    return bool(OUT_OF_CORPUS.search(question))
