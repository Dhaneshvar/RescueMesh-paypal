import asyncio
import base64
import logging
import time
import uuid
from decimal import Decimal

import httpx
from fastapi import HTTPException

from .config import settings

logger = logging.getLogger(__name__)
_token: str | None = None
_token_expires_at = 0.0


async def _access_token() -> str:
    global _token, _token_expires_at
    if _token and time.time() < _token_expires_at:
        return _token
    credentials = base64.b64encode(f"{settings.paypal_client_id}:{settings.paypal_client_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{settings.paypal_base_url}/v1/oauth2/token",
            headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"},
        )
    if response.is_error:
        logger.error("PayPal OAuth failed: status=%s debug_id=%s", response.status_code, response.headers.get("PayPal-Debug-Id"))
        raise HTTPException(502, "Unable to connect to the payment provider.")
    body = response.json()
    _token = body["access_token"]
    _token_expires_at = time.time() + max(int(body.get("expires_in", 32400)) - 120, 60)
    return _token


async def _post(path: str, payload: dict) -> dict:
    token = await _access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "PayPal-Request-Id": str(uuid.uuid4())}
    for attempt in range(3):
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(f"{settings.paypal_base_url}{path}", headers=headers, json=payload)
        if response.status_code != 429:
            break
        await asyncio.sleep(float(response.headers.get("Retry-After", 2 ** attempt)))
    if response.is_error:
        debug_id = response.headers.get("PayPal-Debug-Id")
        logger.error("PayPal request failed: status=%s debug_id=%s", response.status_code, debug_id)
        if response.status_code == 422:
            raise HTTPException(409, "PayPal could not approve this funding source. Please choose another one.")
        raise HTTPException(502, "Payment provider request failed. Try again shortly.")
    return response.json()


def _safe_payment(data: dict) -> dict:
    authorization_id = None
    for unit in data.get("purchase_units", []):
        authorizations = unit.get("payments", {}).get("authorizations", [])
        if authorizations:
            authorization_id = authorizations[0].get("id")
            break
    return {"order_id": data.get("id"), "status": data.get("status"), "authorization_id": authorization_id}


async def create_authorize_order(mission_id: str, amount: Decimal) -> dict:
    if not settings.paypal_configured:
        return {"order_id": f"DEMO-{uuid.uuid4().hex[:12].upper()}", "status": "CREATED", "demo": True}
    payload = {
        "intent": "AUTHORIZE",
        "purchase_units": [{
            "reference_id": mission_id,
            "custom_id": mission_id[:127],
            "description": "RescueMesh verified gap fulfilment",
            "amount": {"currency_code": settings.paypal_currency, "value": f"{amount:.2f}"},
        }],
    }
    return _safe_payment(await _post("/v2/checkout/orders", payload))


async def authorize_order(order_id: str) -> dict:
    if order_id.startswith("DEMO-"):
        return {"order_id": order_id, "status": "AUTHORIZED", "authorization_id": f"DEMOAUTH-{uuid.uuid4().hex[:10].upper()}", "demo": True}
    return _safe_payment(await _post(f"/v2/checkout/orders/{order_id}/authorize", {}))


async def capture_authorization(authorization_id: str, amount: Decimal) -> dict:
    if authorization_id.startswith("DEMOAUTH-"):
        return {"authorization_id": authorization_id, "status": "COMPLETED", "capture_id": f"DEMOCAP-{uuid.uuid4().hex[:10].upper()}", "demo": True}
    data = await _post(f"/v2/payments/authorizations/{authorization_id}/capture", {"amount": {"currency_code": settings.paypal_currency, "value": f"{amount:.2f}"}, "final_capture": True})
    return {"authorization_id": authorization_id, "status": data.get("status"), "capture_id": data.get("id")}

