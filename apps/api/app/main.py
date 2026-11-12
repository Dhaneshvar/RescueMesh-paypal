from decimal import Decimal
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .paypal import authorize_order, capture_authorization, create_authorize_order
from .mcp import rpc as mcp_rpc, status as mcp_status
from .realtime import events
from .store import append_audit
from .db import clear_records, delete_record, get_record, init_db, list_records, save_record

app = FastAPI(title="RescueMesh API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.on_event('startup')
def startup(): init_db()

PRICE = {"insulin": Decimal("12.00"), "ors": Decimal("2.00"), "bandage": Decimal("3.00"), "delivery": Decimal("4.00")}


class ConsentIn(BaseModel):
    accepted: bool


class CreateMissionIn(BaseModel):
    household_alias: str = Field(min_length=2, max_length=50)
    location: str = Field(min_length=2, max_length=80)
    urgency: Literal["critical", "high", "normal"] = "high"
    needs: list[dict]


class OrderIn(BaseModel):
    order_id: str = Field(min_length=4, max_length=80)


class CapacityIn(BaseModel):
    item: str = Field(min_length=2, max_length=32)
    quantity: int = Field(ge=0, le=500)

class MerchantIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    type: Literal['FPS', 'PHARMACY', 'DELIVERY', 'MERCHANT']
    items: dict[str, int]
    eta_minutes: int = Field(ge=1, le=1440)


async def changed(event: str, mission: dict):
    await events.publish(event, {"mission_id": mission["id"], "mission": mission})


def mission_or_404(mission_id: str) -> dict:
    mission = get_record('missions', mission_id)
    if not mission:
        raise HTTPException(404, "Mission not found")
    return mission


def allocate(mission: dict) -> dict:
    allocations, gap = [], []
    merchants = list_records('merchants')
    fps = next((merchant for merchant in merchants if merchant['type'] == 'FPS'), None)
    for need in mission["needs"]:
        item, quantity = need["item"].lower(), int(need["quantity"])
        entitlement_items = {"rice", "lentils", "oil"}
        if mission["entitlement"] and fps and item in entitlement_items and fps["items"].get(item, 0) >= quantity:
            allocations.append({"item": item, "quantity": quantity, "provider": fps["name"], "kind": "entitlement", "cost": "0.00", "eta_minutes": fps["eta_minutes"]})
        else:
            provider = next((m for m in merchants if item in m["items"] and m['items'][item] >= quantity), None)
            if provider:
                cost = PRICE.get(item, Decimal("5.00")) * quantity
                allocations.append({"item": item, "quantity": quantity, "provider": provider["name"], "kind": "paid_gap", "cost": f"{cost:.2f}", "eta_minutes": provider["eta_minutes"]})
                gap.append(cost)
            else:
                allocations.append({"item": item, "quantity": quantity, "provider": "Human review", "kind": "unmatched", "cost": "0.00", "eta_minutes": None})
    mission["allocations"] = allocations
    total = sum(gap, Decimal("0.00"))
    append_audit(mission, "allocation_completed", f"Entitlements were applied before paid gaps. Payable total: ${total:.2f}.")
    save_record('missions', mission)
    return {"allocations": allocations, "payable_total": f"{total:.2f}"}


def payable_total(mission: dict) -> Decimal:
    return sum((Decimal(a["cost"]) for a in mission["allocations"] if a["kind"] == "paid_gap"), Decimal("0.00"))


@app.get("/api/health")
def health():
    return {"ok": True, "paypal_configured": settings.paypal_configured, "environment": settings.paypal_environment, "mcp": mcp_status()}


@app.get("/api/dashboard")
def dashboard():
    return {"missions": list_records('missions'), "merchants": list_records('merchants'), "ledger": list_records('ledger'), "notifications": list_records('notifications'), "payment_mode": "sandbox", "integrations": {"paypal": settings.paypal_configured, "mcp": mcp_status()}}

@app.delete('/api/missions/{mission_id}')
async def delete_mission(mission_id: str):
    if not delete_record('missions', mission_id):
        raise HTTPException(404, 'Mission not found')
    await events.publish('mission.deleted', {'mission_id': mission_id})
    return {'deleted': True, 'id': mission_id}

@app.delete('/api/merchants/{merchant_id}')
async def delete_merchant(merchant_id: str):
    if not delete_record('merchants', merchant_id):
        raise HTTPException(404, 'Merchant not found')
    await events.publish('merchant.deleted', {'merchant_id': merchant_id})
    return {'deleted': True, 'id': merchant_id}

@app.delete('/api/records')
async def clear_all_records():
    clear_records()
    await events.publish('records.cleared', {})
    return {'deleted': True, 'missions': 0, 'merchants': 0}


@app.post("/api/missions")
async def create_mission(body: CreateMissionIn):
    mission_id = f"mission-{uuid4().hex[:8]}"
    mission = {"id": mission_id, **body.model_dump(), "consent": False, "entitlement": None, "allocations": [], "payment": None, "audit": []}
    append_audit(mission, "mission_created", "New manual/voice-assisted recovery mission created.")
    save_record('missions', mission)
    save_record('ledger', {"id": f"ledger-{mission_id}", "kind": "incident", "mission_id": mission_id, "status": "opened", "amount": "0.00", "currency": settings.paypal_currency, "detail": "Recovery mission opened."})
    await changed("mission.created", mission)
    return mission


@app.post("/api/missions/{mission_id}/entitlement-check")
async def entitlement_check(mission_id: str, body: ConsentIn):
    mission = mission_or_404(mission_id)
    mission["consent"] = body.accepted
    if body.accepted:
        mission["entitlement"] = {"status": "eligible", "scheme": "NFSA eligibility response", "source": "consent-based adapter", "data_minimization": "No government identifier collected or retained"}
        append_audit(mission, "consent_recorded", "Household opted into a simulated eligibility check; only a yes/no result was returned.")
    else:
        mission["entitlement"] = None
        append_audit(mission, "consent_declined", "Emergency routing continues without an entitlement lookup.")
    await changed("entitlement.checked", mission)
    save_record('missions', mission)
    return mission


@app.post("/api/missions/{mission_id}/allocate")
async def run_allocation(mission_id: str):
    mission = mission_or_404(mission_id)
    result = allocate(mission)
    for allocation in mission["allocations"]:
        allocation["status"] = "reserved" if allocation["kind"] != "unmatched" else "needs_review"
    await changed("allocation.updated", mission)
    save_record('missions', mission)
    return result


@app.post("/api/missions/{mission_id}/paypal/order")
async def paypal_order(mission_id: str):
    mission = mission_or_404(mission_id)
    if not mission["allocations"]:
        allocate(mission)
    amount = payable_total(mission)
    if amount <= 0:
        raise HTTPException(409, "There is no payable gap for this mission.")
    payment = await create_authorize_order(mission_id, amount)
    mission["payment"] = {**payment, "amount": f"{amount:.2f}", "currency": settings.paypal_currency, "state": "created"}
    append_audit(mission, "paypal_order_created", f"PayPal authorization order created for {settings.paypal_currency} {amount:.2f}.")
    save_record('missions', mission)
    return {"orderId": payment["order_id"], "demo": payment.get("demo", False)}


@app.post("/api/missions/{mission_id}/paypal/authorize")
async def paypal_authorize(mission_id: str, body: OrderIn):
    mission = mission_or_404(mission_id)
    if not mission["payment"] or mission["payment"]["order_id"] != body.order_id:
        raise HTTPException(409, "This order does not belong to this mission.")
    payment = await authorize_order(body.order_id)
    if not payment.get("authorization_id"):
        raise HTTPException(502, "PayPal did not return an authorization.")
    mission["payment"].update(payment)
    mission["payment"]["state"] = "authorized"
    append_audit(mission, "payment_authorized", "PayPal approval complete. Funds will only be captured after verification.")
    await changed("payment.authorized", mission)
    save_record('missions', mission)
    return mission["payment"]


@app.post("/api/missions/{mission_id}/verify-and-capture")
async def verify_and_capture(mission_id: str):
    mission = mission_or_404(mission_id)
    payment = mission.get("payment")
    if not payment or payment.get("state") != "authorized":
        raise HTTPException(409, "A PayPal authorization is required before capture.")
    result = await capture_authorization(payment["authorization_id"], Decimal(payment["amount"]))
    payment.update(result)
    provider_status = result.get("status")
    if provider_status != "COMPLETED":
        payment["state"] = "capture_pending" if provider_status in {"PENDING", "PENDING_REVIEW"} else "capture_failed"
        append_audit(mission, "capture_not_completed", f"PayPal returned capture status {provider_status or 'UNKNOWN'}; no completed transfer was recorded.")
        save_record('missions', mission)
        await changed("payment.capture_pending", mission)
        raise HTTPException(409, f"PayPal capture is not completed (status: {provider_status or 'unknown'}). Check Sandbox Activity before retrying.")
    payment["state"] = "captured"
    payment["destination"] = sorted({a["provider"] for a in mission.get("allocations", []) if a.get("kind") == "paid_gap"})
    payment["captured_at"] = __import__('datetime').datetime.utcnow().isoformat() + 'Z'
    destination = payment["destination"]
    ledger_id = f"ledger-payment-{mission_id}"
    save_record('ledger', {"id": ledger_id, "kind": "payment", "mission_id": mission_id, "status": "completed", "amount": payment["amount"], "currency": payment.get("currency", settings.paypal_currency), "destination": destination, "detail": "PayPal authorization captured after fulfilment verification.", "capture_id": payment.get("capture_id"), "created_at": payment["captured_at"]})
    save_record('notifications', {"id": f"notification-{uuid4().hex[:10]}", "mission_id": mission_id, "audience": "contributors", "title": "Contribution completed", "message": f"{payment['amount']} {payment.get('currency', settings.paypal_currency)} was sent to {', '.join(destination) or 'the fulfilment partner'}.", "created_at": payment["captured_at"], "read": False})
    append_audit(mission, "fulfilment_verified_and_captured", "Mock proof-of-fulfilment accepted; authorized PayPal payment captured.")
    await changed("payment.captured", mission)
    save_record('missions', mission)
    return payment


@app.post("/api/merchants/{merchant_id}/capacity")
async def update_capacity(merchant_id: str, body: CapacityIn):
    merchant = get_record('merchants', merchant_id)
    if not merchant:
        raise HTTPException(404, "Local partner not found")
    merchant["items"][body.item.lower()] = body.quantity
    save_record('merchants', merchant)
    await events.publish("capacity.updated", {"merchant": merchant})
    return merchant

@app.post('/api/merchants')
async def create_merchant(body: MerchantIn):
    merchant = {'id': f'merchant-{uuid4().hex[:8]}', **body.model_dump(), 'items': {key.lower(): value for key, value in body.items.items()}}
    save_record('merchants', merchant)
    await events.publish('merchant.created', {'merchant': merchant})
    return merchant


@app.post("/api/missions/{mission_id}/allocations/{item}/fulfil")
async def fulfil_allocation(mission_id: str, item: str):
    mission = mission_or_404(mission_id)
    allocation = next((entry for entry in mission["allocations"] if entry["item"] == item), None)
    if not allocation:
        raise HTTPException(404, "Allocation not found")
    allocation["status"] = "fulfilled"
    append_audit(mission, "partner_fulfilment_confirmed", f"{allocation['provider']} confirmed {allocation['item']} fulfilment.")
    await changed("allocation.fulfilled", mission)
    save_record('missions', mission)
    return allocation


@app.get("/api/integrations")
def integrations():
    return {"paypal_rest_configured": settings.paypal_configured, "paypal_mcp": mcp_status()}


@app.get("/api/mcp/tools")
async def list_mcp_tools():
    return await mcp_rpc("tools/list")


@app.websocket("/api/events")
async def websocket_events(websocket: WebSocket):
    await events.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        events.disconnect(websocket)

