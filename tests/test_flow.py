import os
import tempfile

os.environ["REPLY_DESK_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")

from app import pipeline, store  # noqa: E402
from app.critic import check  # noqa: E402

store.init()


def reading(**kw):
    base = {"state": "price_shield", "protecting": "x", "evidence": "send me the price",
            "must_not": "push", "route": "nurture", "why": "x", "draft": "Here is the price."}
    return {**base, **kw}


def test_accepts_verbatim_quote_ignoring_case_and_curly_quotes():
    assert check(reading(evidence="“Send me the price”"), "OK, send me the price and I'll see") == []


def test_rejects_paraphrase():
    assert "evidence is not a word-for-word quote from the reply" in check(reading(evidence="tell me the cost"), "send me the price")


def test_forces_human_for_intrusion():
    probs = check(reading(state="intrusion", evidence="where did you get", route="answer_now"), "where did you get my email?")
    assert any("must go to a human" in p for p in probs)


def test_two_bad_readings_escalate_without_draft():
    rid = store.add_reply("Where did you get my email address?", {"company": "Test"})
    bad = lambda s, u: reading(state="intrusion", evidence="made up words", route="answer_now")
    r = pipeline.process(rid, complete=bad)
    assert r["status"] == "awaiting_approval"
    assert r["reading"]["route"] == "human" and r["reading"]["draft"] == ""
    assert sum(1 for s in r["steps"] if s["step"] == "check") == 2


def test_retry_then_pass_and_approve_schedules_follow_up():
    rid = store.add_reply("Send me the price and I'll see.", {"company": "Test"})
    answers = iter([reading(evidence="the cost"), reading()])
    r = pipeline.process(rid, complete=lambda s, u: next(answers))
    assert r["reading"]["route"] == "nurture"
    r = pipeline.approve(rid, "Here is the price.", "Dana")
    assert r["status"] == "approved" and r["follow_up_on"]
    assert [s["step"] for s in r["steps"]][-2:] == ["approve", "follow_up"]
