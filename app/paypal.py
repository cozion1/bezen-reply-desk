"""PayPal Orders v2 (sandbox by default): create a checkout link and read its status."""
import os
import time

import httpx

BASE = os.environ.get("PAYPAL_BASE", "https://api-m.sandbox.paypal.com")
_token = {"value": "", "expires": 0.0}


class PayPalError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(os.environ.get("PAYPAL_CLIENT_ID") and os.environ.get("PAYPAL_SECRET"))


def _access_token() -> str:
    if _token["value"] and time.time() < _token["expires"] - 60:
        return _token["value"]
    r = httpx.post(f"{BASE}/v1/oauth2/token", data={"grant_type": "client_credentials"},
                   auth=(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_SECRET"]), timeout=30)
    if r.status_code != 200:
        raise PayPalError(f"PayPal auth HTTP {r.status_code}")
    body = r.json()
    _token.update(value=body["access_token"], expires=time.time() + body.get("expires_in", 300))
    return _token["value"]


def create_order(amount: str, currency: str, description: str, reference: str) -> dict:
    r = httpx.post(
        f"{BASE}/v2/checkout/orders",
        headers={"Authorization": f"Bearer {_access_token()}", "PayPal-Request-Id": f"bezen-{reference}"},
        json={
            "intent": "CAPTURE",
            "purchase_units": [{"reference_id": reference, "description": description[:127],
                                "amount": {"currency_code": currency, "value": amount}}],
            "payment_source": {"paypal": {"experience_context": {
                "brand_name": "BEZEN Reply Desk", "user_action": "PAY_NOW",
                "return_url": "https://bezenai.com/paid", "cancel_url": "https://bezenai.com"}}},
        },
        timeout=30,
    )
    if r.status_code not in (200, 201):
        raise PayPalError(f"PayPal order HTTP {r.status_code}: {r.text[:200]}")
    body = r.json()
    link = next((l["href"] for l in body.get("links", []) if l["rel"] in ("payer-action", "approve")), "")
    return {"order_id": body["id"], "status": body["status"], "url": link,
            "amount": amount, "currency": currency, "description": description}


def order_status(order_id: str) -> str:
    r = httpx.get(f"{BASE}/v2/checkout/orders/{order_id}",
                  headers={"Authorization": f"Bearer {_access_token()}"}, timeout=30)
    if r.status_code != 200:
        raise PayPalError(f"PayPal status HTTP {r.status_code}")
    return r.json()["status"]


def capture(order_id: str) -> str:
    r = httpx.post(f"{BASE}/v2/checkout/orders/{order_id}/capture",
                   headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"},
                   timeout=30)
    if r.status_code not in (200, 201):
        raise PayPalError(f"PayPal capture HTTP {r.status_code}: {r.text[:200]}")
    return r.json()["status"]
