"""The reading layer: what the model is asked to see in a reply, and the shape of its answer."""

STATES = {
    "intrusion": "feels their privacy or space was crossed (where did you get my details, stop contacting me)",
    "burned_before": "tried something similar and got hurt; protecting themselves from a repeat",
    "price_shield": "uses price or 'send me the price' to keep distance before trust exists",
    "career_risk": "protecting their standing with a boss or team if the purchase fails",
    "guilt_or_loss": "the decision touches family, care, grief or guilt more than money",
    "overloaded": "no time or attention right now; not a no",
    "curious_yes": "open and interested, asking a real question",
    "ready_yes": "clear yes, wants the next practical step",
    "flat_no": "a clear, calm no",
}

ROUTES = {
    "answer_now": "the agent may answer now with the drafted message",
    "nurture": "do not push; send a light, low-pressure message and follow up later",
    "human": "a person must take this one; no automatic message",
    "close": "thank them and close respectfully; no follow-up",
}

# States where an automatic message would do harm. The code enforces this, not the model.
HUMAN_ONLY = {"intrusion", "guilt_or_loss", "career_risk"}

FOLLOW_UP_DAYS = {"answer_now": 2, "nurture": 10, "human": 1, "close": None}

SYSTEM = """You read customer replies to sales or support messages for a business team.
A normal sorter labels a reply yes / no / question and answers the words.
You read what the person is protecting, then decide what the team should do next.

States (pick exactly one):
{states}

Routes (pick exactly one):
{routes}

Rules:
- "evidence" must be copied word for word from the reply. Never paraphrase it.
- "must_not" is the one thing that would burn this person right now.
- If the state is intrusion, guilt_or_loss or career_risk, the route is "human".
- "draft" is the next message in the customer's own language, short, no pressure, no invented offers.
  If the route is "close", the draft thanks them and closes. If the route is "human", the draft is a suggestion for the person who takes over.
- Use only facts given in the lead record. Do not invent discounts, prices, names or dates.

Answer with JSON only:
{{"state": "...", "protecting": "...", "evidence": "...", "must_not": "...", "route": "...", "why": "...", "draft": "..."}}"""


def system_prompt() -> str:
    states = "\n".join(f"- {k}: {v}" for k, v in STATES.items())
    routes = "\n".join(f"- {k}: {v}" for k, v in ROUTES.items())
    return SYSTEM.format(states=states, routes=routes)


def user_prompt(reply: dict, retry_note: str = "") -> str:
    lead = reply.get("lead") or {}
    lines = [
        f"Company: {lead.get('company', 'unknown')}",
        f"Stage: {lead.get('stage', 'unknown')}",
        f"Last message we sent: {lead.get('last_message', 'unknown')}",
        f"What the business may offer: {lead.get('allowed', 'nothing specific')}",
        "",
        "Customer reply:",
        reply["text"],
    ]
    if retry_note:
        lines += ["", f"Your previous answer was rejected by the checker: {retry_note}. Fix it."]
    return "\n".join(lines)
