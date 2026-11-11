"""Pre-flight guardrails: clarification and refusal.

These run before the agent loop so the behaviour is deterministic and shows up
in the trace as a step, rather than being left to the model's judgement.

The distinction that matters: a question ABOUT policy is answerable from the
corpus ("how many days do I accrue"); a REQUEST needs specifics before a
compliance check can be applied ("can I take some time off").
"""
from __future__ import annotations

import re

# --- request intent: first person, asking to do something -------------------
REQUEST_INTENT = re.compile(
    r"\b(can i|may i|could i|should i|i (want|need|would like|plan|intend) to|"
    r"i'?m (taking|requesting|planning)|let me|am i allowed to|book)\b", re.I)

# --- a time-off topic -------------------------------------------------------
TIME_OFF = re.compile(
    r"\b(time off|pto|vacation|personal (day|time)|days? off|holiday|leave)\b", re.I)

# --- a concrete amount or date ----------------------------------------------
HAS_AMOUNT = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b"
    r"(?:\s+\w+){0,3}?\s*(day|days|week|weeks|month|months)\b"
    r"|\b(a|an|next|last)\s+(day|week|month)\b", re.I)
HAS_DATE = re.compile(
    r"\b(next|this|coming|following)\s+(week|month|monday|tuesday|wednesday|"
    r"thursday|friday|weekend)\b|\b\d{1,2}/\d{1,2}\b|"
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\b", re.I)

# --- a remote-work request --------------------------------------------------
WANTS_REMOTE = re.compile(
    r"\b(work from|working from|work remotely|remote work|work abroad|"
    r"work overseas)\b", re.I)
HAS_DESTINATION = re.compile(
    r"\b(another (state|country)|international|out of (state|country)|"
    r"portugal|spain|canada|mexico|india|uk|germany|france|italy|brazil|"
    r"denver|austin|seattle|new york|boston|chicago|"
    r"california|texas|florida|washington|oregon|colorado)\b", re.I)

# --- explicitly vague phrasing ---------------------------------------------
VAGUE = re.compile(r"\b(some time|a while|a bit|sometime|at some point)\b", re.I)


def needs_clarification(question: str) -> str | None:
    """Return the question to ask the user, or None when the request is specific."""
    text = question.strip()
    if not text:
        return "What would you like to ask about?"

    is_request = bool(REQUEST_INTENT.search(text))

    # A time-off REQUEST with no amount and no dates cannot be checked.
    if is_request and TIME_OFF.search(text):
        if not HAS_AMOUNT.search(text) and not HAS_DATE.search(text):
            return ("How many days are you requesting, and for which dates? "
                    "I need both to check your balance and the notice rule.")

    # A remote-work request with no destination.
    if WANTS_REMOTE.search(text) and not HAS_DESTINATION.search(text):
        return ("Where would you be working from, and for how long? "
                "Both decide which policy applies.")

    # Explicitly vague phrasing with nothing concrete attached.
    if VAGUE.search(text) and not HAS_AMOUNT.search(text) and not HAS_DATE.search(text):
        if is_request or WANTS_REMOTE.search(text):
            return ("Can you give me the dates and the duration? "
                    "I need those before I can apply the policy.")

    return None


REFUSAL_TEXT = (
    "The HR policy corpus does not cover this. I can help with PTO, holidays, "
    "remote and international work, expenses, data security, benefits, leave, "
    "onboarding, equipment, conduct and HR escalation. For anything else, "
    "please contact People Operations."
)

OUT_OF_CORPUS = re.compile(
    r"\b(ceo|chief executive|salary|compensation|pay band|bonus|"
    r"federal tax|tax law|irs|visa|immigration|green card|"
    r"company car|vehicle allowance|stock|equity|layoff|redundan)\b", re.I)


def is_out_of_corpus(question: str) -> bool:
    """True when the question names something the corpus does not cover."""
    return bool(OUT_OF_CORPUS.search(question))
