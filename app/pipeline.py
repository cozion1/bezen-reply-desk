"""The workflow for one reply: read, check, decide, draft, then wait for a person."""
from datetime import datetime, timedelta, timezone

from . import llm, paypal, store
from .critic import check, payment_allowed
from .layer import FOLLOW_UP_DAYS, system_prompt, user_prompt


def process(reply_id: int, complete=llm.complete_json) -> dict:
    reply = store.get(reply_id)
    if reply is None:
        raise KeyError(reply_id)
    store.update(reply_id, status="reading")
    store.log_step(reply_id, "read", f"Model {llm.provider()}:{llm.model_name()} reads what the person is protecting.")

    note, reading, problems = "", None, []
    for attempt in (1, 2):
        try:
            reading = complete(system_prompt(), user_prompt(reply, note))
        except llm.ModelError as e:
            store.log_step(reply_id, "error", str(e))
            store.update(reply_id, status="error")
            return store.get(reply_id)
        problems = check(reading, reply["text"])
        if not problems:
            store.log_step(reply_id, "check", f"Checker passed on attempt {attempt}: quote is verbatim, route is allowed.")
            break
        note = "; ".join(problems)
        store.log_step(reply_id, "check", f"Checker rejected attempt {attempt}: {note}.")

    if problems:
        # Two failed readings: no automatic message, a person takes it.
        reading = {**(reading or {}), "route": "human", "draft": "",
                   "why": "The reading could not be verified twice, so a person takes this reply."}
        store.log_step(reply_id, "decide", "Escalated to a human after two rejected readings. No draft is offered.")
    else:
        store.log_step(reply_id, "decide",
                       f"State: {reading['state']}. Route: {reading['route']}. Must not: {reading.get('must_not', '')}")
        store.log_step(reply_id, "draft", "Next message drafted. Waiting for a person to approve, edit or reject.")
        _maybe_prepare_payment(reply_id, reply, reading)

    store.update(reply_id, status="awaiting_approval", reading=reading)
    return store.get(reply_id)


def _maybe_prepare_payment(reply_id: int, reply: dict, reading: dict) -> None:
    """Prepare (not send) a PayPal checkout link when code allows it. The person still approves."""
    if not paypal.enabled():
        return
    lead = reply.get("lead") or {}
    ok, reason = payment_allowed(reading, lead)
    if not ok:
        if lead.get("price"):
            store.log_step(reply_id, "pay", f"No payment link: {reason}.")
        return
    try:
        order = paypal.create_order(str(lead["price"]), lead.get("currency", "USD"),
                                    lead.get("offer") or lead.get("allowed") or "Order", f"reply-{reply_id}")
    except paypal.PayPalError as e:
        store.log_step(reply_id, "pay", f"PayPal order could not be created: {e}")
        return
    reading["payment"] = order
    store.log_step(reply_id, "pay",
                   f"PayPal sandbox order {order['order_id']} prepared for {order['amount']} {order['currency']} "
                   f"({reason}). It is attached only if a person approves.")


def refresh_payment(reply_id: int) -> dict:
    reply = store.get(reply_id)
    pay = (reply.get("reading") or {}).get("payment")
    if not pay:
        return reply
    status = paypal.order_status(pay["order_id"])
    if status == "APPROVED":
        status = paypal.capture(pay["order_id"])
    if status != pay.get("status"):
        pay["status"] = status
        store.update(reply_id, reading=reply["reading"])
        store.log_step(reply_id, "pay", f"PayPal order {pay['order_id']} is now {status}.")
        if status == "COMPLETED":
            store.update(reply_id, follow_up_on=None)
            store.log_step(reply_id, "follow_up", "Paid. Follow-up replaced by onboarding.")
    return store.get(reply_id)


def approve(reply_id: int, message: str, by: str) -> dict:
    reply = store.get(reply_id)
    route = (reply.get("reading") or {}).get("route", "human")
    days = FOLLOW_UP_DAYS.get(route)
    follow = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d") if days else None
    edited = message.strip() != (reply.get("reading") or {}).get("draft", "").strip()
    pay = (reply.get("reading") or {}).get("payment")
    if pay and pay["url"] not in message:
        message = f"{message.rstrip()}\n\nYou can complete the payment here: {pay['url']}"
    store.update(reply_id, status="approved", final_message=message, decided_by=by, follow_up_on=follow)
    store.log_step(reply_id, "approve", f"{by} approved the message{' after editing it' if edited else ''}"
                   f"{' with the PayPal checkout link' if pay else ''}.")
    store.log_step(reply_id, "follow_up", f"Follow-up scheduled for {follow}." if follow else "Closed. No follow-up.")
    return store.get(reply_id)


def reject(reply_id: int, by: str, reason: str) -> dict:
    store.update(reply_id, status="taken_by_human", decided_by=by)
    store.log_step(reply_id, "approve", f"{by} rejected the draft and took the reply personally. Reason: {reason or 'none given'}.")
    return store.get(reply_id)
