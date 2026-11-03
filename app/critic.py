"""The checker is code, not a model. It decides whether a reading may be used."""
import re

from .layer import HUMAN_ONLY, ROUTES, STATES

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.translate(_QUOTES)).strip().strip('"').strip().lower()


def check(reading: dict, reply_text: str) -> list[str]:
    """Return a list of problems. Empty means the reading passes."""
    problems = []
    state, route = reading.get("state"), reading.get("route")
    if state not in STATES:
        problems.append(f"unknown state '{state}'")
    if route not in ROUTES:
        problems.append(f"unknown route '{route}'")
    evidence = _norm(str(reading.get("evidence", "")))
    text = _norm(reply_text)
    if not evidence:
        problems.append("evidence is empty")
    elif evidence not in text:
        problems.append("evidence is not a word-for-word quote from the reply")
    elif len(evidence.split()) < 2 and len(text.split()) > 2:
        problems.append("evidence is a single word")
    if state in HUMAN_ONLY and route != "human":
        problems.append(f"state '{state}' must go to a human, not '{route}'")
    if not str(reading.get("draft", "")).strip():
        problems.append("draft is empty")
    return problems
